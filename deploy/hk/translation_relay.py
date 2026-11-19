"""A content-free HTTP relay into the existing HK worker's private socket."""

from contextlib import contextmanager, ExitStack
import fcntl
import json
import os
from pathlib import Path
import re
import socket
from socketserver import StreamRequestHandler, ThreadingUnixStreamServer
import sqlite3
import stat
import sys
from threading import BoundedSemaphore, Thread

from fastapi import Request
from fastapi.responses import JSONResponse
import httpx
import psycopg
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from cj_api.composition import CompositionUnavailable
from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.local_app import scope_for
from cj_api.translation import (
    DashScopeTranslation, MAX_BODY, ROUTE, TranslationError, TranslationInput, TranslationRelay, VERSION,
)
from cj_usage.authorization_budget import AuthorizationBudget, HK_JOURNAL_ROOT
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.translation_budget import TranslationBudget, TranslationDuplicate, TranslationLimit

from .configuration import TRANSLATION_INTERNAL_SUBJECTS



SOCKET = Path('/run/g2c-demo/translation.sock')
TOKEN_LIMIT = 4096
MAX_RESPONSE = 256 * 1024
REQUEST_TIMEOUT = 50
MAX_CONCURRENT = 4


def _error(code):
    return dict(version=VERSION, error=code)


def _token_valid(value):
    return 0 < len(value) <= TOKEN_LIMIT and all(0x21 <= c <= 0x7e for c in value)


def _response(channel):
    size = int.from_bytes(channel.read(4), 'big')
    if not 0 < size <= MAX_RESPONSE:
        raise ValueError('bounded translation response required')
    raw = channel.read(size)
    if len(raw) != size:
        raise ValueError('partial translation response')
    status, body = json.loads(raw)
    if status not in (200, 400, 401, 403, 409, 413, 422, 429, 502, 503) or type(body) is not dict:
        raise ValueError('invalid translation response')
    return status, body


def socket_request(token, raw, *, path=SOCKET):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(REQUEST_TIMEOUT)
        connection.connect(str(path))
        connection.sendall(token.encode('ascii') + b'\n' + len(raw).to_bytes(4, 'big') + raw)
        with connection.makefile('rb') as incoming:
            return _response(incoming)


def register_translation_route(app, *, send=socket_request):
    slots = BoundedSemaphore(MAX_CONCURRENT)

    @app.post(ROUTE)
    async def translate(request: Request):
        def render(status, body):
            return JSONResponse(body, status_code=status, headers={'Cache-Control': 'no-store'})

        provided = request.headers.getlist('authorization')
        if (len(provided) != 1 or not provided[0].startswith('Bearer ')
                or not _token_valid(provided[0][7:].encode('utf-8'))):
            return render(401, _error('sign_in_required'))
        if request.headers.get('content-type', '').partition(';')[0].strip().lower() != 'application/json':
            return render(400, _error('invalid_request'))
        if not slots.acquire(blocking=False):
            return render(503, _error('unavailable'))
        try:
            data = bytearray()
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_BODY:
                    return render(413, _error('request_too_large'))
                data.extend(chunk)
            status, body = await run_in_threadpool(send, provided[0][7:], bytes(data))
            return render(status, body)
        except (ClientDisconnect, OSError, ValueError):
            return render(503, _error('unavailable'))
        finally:
            slots.release()


def _dispatch(relay, incoming):
    token = incoming.readline(TOKEN_LIMIT + 2)
    if not token.endswith(b'\n') or not _token_valid(token[:-1]):
        raise TranslationError(401, 'sign_in_required')
    token = token[:-1].decode('ascii')
    owner = relay.authorize(token)
    size = int.from_bytes(incoming.read(4), 'big')
    if not 0 < size <= MAX_BODY:
        raise TranslationError(413, 'request_too_large')
    raw = incoming.read(size)
    if len(raw) != size:
        raise TranslationError(400, 'invalid_request')
    return relay.translate(token, TranslationInput.read(raw), owner)


@contextmanager
def translation_socket(relay, *, path=SOCKET):
    """Copy neither the supplier key nor the shared budget writer into the API."""
    root = path.parent
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('owned_private_translation_socket_directory_required')
    slots = BoundedSemaphore(MAX_CONCURRENT)

    class Handler(StreamRequestHandler):
        def handle(self):
            self.request.settimeout(5)
            if not slots.acquire(blocking=False):
                status, body = 503, _error('unavailable')
            else:
                try:
                    status, body = 200, _dispatch(relay, self.rfile)
                except TranslationError as error:
                    status, body = error.status, _error(error.code)
                except TranslationLimit:
                    status, body = 429, _error('quota_exceeded')
                except TranslationDuplicate:
                    status, body = 409, _error('request_already_used')
                except (BudgetUnknown, CompositionUnavailable, psycopg.Error, sqlite3.Error, OSError, ValueError):
                    status, body = 503, _error('unavailable')
                finally:
                    slots.release()
            raw = json.dumps([status, body], ensure_ascii=False, separators=(',', ':')).encode()
            if len(raw) > MAX_RESPONSE:
                raw = json.dumps([502, _error('provider_unavailable')], separators=(',', ':')).encode()
            try:
                self.wfile.write(len(raw).to_bytes(4, 'big') + raw)
            except OSError:
                pass

    class Server(ThreadingUnixStreamServer):
        daemon_threads = True

    lock = os.open(root / 'translation.lock', os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR, 0o600)
    with os.fdopen(lock, 'rb') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if path.exists() or path.is_symlink():
            meta = path.lstat()
            if not stat.S_ISSOCK(meta.st_mode) or meta.st_uid != os.getuid():
                raise ValueError('invalid_previous_translation_socket')
            path.unlink()
        with Server(str(path), Handler) as server:
            path.chmod(0o600)
            thread = Thread(target=server.serve_forever, daemon=True, name='translation-relay')
            thread.start()
            try:
                yield
            finally:
                server.shutdown()
                thread.join()
                path.unlink()


@contextmanager
def active_translation(runtime, authorization_guard):
    raw = os.environ.get(TRANSLATION_INTERNAL_SUBJECTS)
    if raw is None:
        yield
        return
    with ExitStack() as stack:
        try:
            subjects = json.loads(raw)
            if (type(subjects) is not list or not 0 < len(subjects) <= 100
                    or any(type(s) is not str or not re.fullmatch(r'[A-Za-z0-9_.:@-]{1,128}', s)
                           for s in subjects)
                    or len(set(subjects)) != len(subjects)):
                raise ValueError('explicit_internal_translation_roster_required')
            budget = AuthorizationBudget(HK_JOURNAL_ROOT, authorization_guard=authorization_guard, demo=True)
            checker = account_checker_for(runtime.auth, runtime.database(), selected_subjects=frozenset(subjects))
            client = stack.enter_context(httpx.Client(trust_env=False, follow_redirects=False))
            provider = DashScopeTranslation(os.environ['CJ_MODEL_API_KEY'], client)
            relay = TranslationRelay(checker, TranslationBudget(budget), provider, scope_for)
            stack.enter_context(translation_socket(relay))
        except (BudgetUnknown, CompositionUnavailable, psycopg.Error, sqlite3.Error,
                KeyError, OSError, TypeError, ValueError):
            stack.close()
            print('ALERT translation_relay_unavailable', file=sys.stderr, flush=True)
        yield
