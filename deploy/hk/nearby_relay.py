"""Private worker relay for the closed-by-default Gaode plugin routes."""

from contextlib import contextmanager, ExitStack
import fcntl
import json
import os
from pathlib import Path
import socket
from socketserver import StreamRequestHandler, ThreadingUnixStreamServer
import sqlite3
import stat
import sys
from threading import BoundedSemaphore, Thread

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
import psycopg
from starlette.requests import ClientDisconnect

from cj_api.composition import CompositionUnavailable
from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.local_app import scope_for
from cj_api.nearby_tools import GaodeNearby, NearbyLocationRequest, NearbySearchRequest, NearbyService, REVERSE, SEARCH
from cj_api.plugin_tools import BEARER, MAX_BODY, PluginError, _authorize, _bounded_body
from cj_strict_json import reject_duplicates
from cj_usage.authorization_budget import AuthorizationBudget, HK_JOURNAL_ROOT
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.nearby_budget import NearbyBudget

from .configuration import NEARBY_INTERNAL_SUBJECTS
from .plugin_roster import generate_plugin_subjects
from .translation_relay import TOKEN_LIMIT, _token_valid


SOCKET = Path('/run/g2c-demo/nearby.sock')
MAX_RESPONSE = 128 * 1024
ROUTES = {SEARCH: b'S', REVERSE: b'R'}
RESPONSE_STATUS = {200, 400, 401, 403, 409, 413, 429, 502, 503, 504}


def nearby_request(action, token, raw, *, path=SOCKET):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(27)
        connection.connect(str(path))
        connection.sendall(action + token.encode('ascii') + b'\n' + len(raw).to_bytes(4, 'big') + raw)
        with connection.makefile('rb') as incoming:
            size = int.from_bytes(incoming.read(4), 'big')
            if not 0 < size <= MAX_RESPONSE:
                raise ValueError('bounded Nearby response required')
            response = incoming.read(size)
            if len(response) != size:
                raise ValueError('incomplete Nearby response')
            status, body = json.loads(response)
            if status not in RESPONSE_STATUS or type(body) is not dict:
                raise ValueError('invalid Nearby reply')
            return status, body


def register_nearby_routes(app, *, send=nearby_request):
    @app.post(SEARCH)
    @app.post(REVERSE)
    async def execute(request: Request):
        try:
            supplied = request.headers.getlist('authorization')
            match = BEARER.fullmatch(supplied[0]) if len(supplied) == 1 else None
            if match is None:
                raise PluginError(401, 'sign_in_required')
            raw = await _bounded_body(request)
            status, body = await run_in_threadpool(send, ROUTES[request.url.path], match[1], bytes(raw))
        except PluginError as error:
            status, body = error.status, {'error': error.code}
        except ClientDisconnect:
            status, body = 400, {'error': 'invalid_request'}
        except (OSError, ValueError):
            status, body = 503, {'error': 'unavailable'}
        return JSONResponse(body, status_code=status, headers={'Cache-Control': 'no-store'})


def _dispatch(incoming, service, checker, roster, disabled):
    action = incoming.read(1)
    supplied = incoming.readline(TOKEN_LIMIT + 2)
    if not supplied.endswith(b'\n') or not _token_valid(supplied[:-1]):
        raise PluginError(401, 'sign_in_required')
    token = supplied[:-1].decode('ascii')
    size = int.from_bytes(incoming.read(4), 'big')
    if not 0 < size <= MAX_BODY:
        raise PluginError(413, 'request_too_large')
    raw = incoming.read(size)
    if len(raw) != size or action not in {b'S', b'R'}:
        raise PluginError(400, 'invalid_request')
    if service is None:
        if disabled:
            raise PluginError(403, 'not_enabled')
        raise PluginError(503, 'unavailable')
    principal = _authorize(checker, token, roster)
    owner = (principal.issuer, principal.subject)

    def authorize():
        current = _authorize(checker, token, roster)
        if (current.issuer, current.subject) != owner:
            raise PluginError(401, 'sign_in_required')

    kind = NearbySearchRequest if action == b'S' else NearbyLocationRequest
    try:
        document = kind.model_validate(json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate Nearby field')))
    except (ValueError, RecursionError):
        raise PluginError(400, 'invalid_request') from None
    operation = service.search if action == b'S' else service.reverse
    return operation(scope_for(*owner), document, authorize)


@contextmanager
def nearby_socket(service, checker, roster, *, path=SOCKET, disabled=False):
    root = path.parent.lstat()
    if not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid() or stat.S_IMODE(root.st_mode) != 0o700:
        raise ValueError('owned private Nearby socket directory required')
    slots = BoundedSemaphore(4)

    class Handler(StreamRequestHandler):
        def handle(self):
            self.request.settimeout(5)
            if not slots.acquire(blocking=False):
                status, body = 503, {'error': 'unavailable'}
            else:
                try:
                    status, body = 200, _dispatch(self.rfile, service, checker, roster, disabled)
                except PluginError as error:
                    status, body = error.status, {'error': error.code}
                except (BudgetUnknown, psycopg.Error, sqlite3.Error, OSError, ValueError):
                    status, body = 503, {'error': 'unavailable'}
                finally:
                    slots.release()
            encoded = json.dumps([status, body], ensure_ascii=False, separators=(',', ':')).encode()
            if len(encoded) > MAX_RESPONSE:
                encoded = b'[502,{"error":"supplier_unavailable"}]'
            try:
                self.wfile.write(len(encoded).to_bytes(4, 'big') + encoded)
            except OSError:
                pass

    class Server(ThreadingUnixStreamServer):
        daemon_threads = True

    lock = os.open(path.with_suffix('.lock'), os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR, 0o600)
    with os.fdopen(lock, 'rb') as control:
        fcntl.flock(control, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError('invalid previous Nearby socket')
            path.unlink()
        with Server(str(path), Handler) as server:
            path.chmod(0o600)
            thread = Thread(target=server.serve_forever, daemon=True, name='nearby-relay')
            thread.start()
            try:
                yield
            finally:
                server.shutdown()
                thread.join()
                path.unlink()


@contextmanager
def active_nearby(runtime, authorization_guard):
    raw = os.environ.get(NEARBY_INTERNAL_SUBJECTS)
    service = checker = None
    roster = frozenset()
    if raw is not None:
        try:
            values = json.loads(raw)
            if type(values) is not list or not values or any(type(item) is not str for item in values):
                raise ValueError('explicit Nearby roster required')
            selected = frozenset(values)
            if len(selected) != len(values) or len(selected) > 10 or not selected.issubset(generate_plugin_subjects()):
                raise ValueError('invalid Nearby roster')
            provider = GaodeNearby(os.environ['CJ_AMAP_WEB_KEY'])
            journal = AuthorizationBudget(HK_JOURNAL_ROOT, authorization_guard=authorization_guard, demo=True)
            checker = account_checker_for(runtime.auth, runtime.database(), selected_subjects=selected)
            service = NearbyService(provider, NearbyBudget(journal))
            roster = selected
        except (KeyError, BudgetUnknown, CompositionUnavailable, psycopg.Error, sqlite3.Error,
                ValueError, OSError, RecursionError):
            print('ALERT nearby_relay_configuration_unavailable', file=sys.stderr, flush=True)
    with ExitStack() as stack:
        try:
            stack.enter_context(nearby_socket(service, checker, roster, disabled=raw is None))
        except (OSError, ValueError):
            print('ALERT nearby_relay_socket_unavailable', file=sys.stderr, flush=True)
        yield
