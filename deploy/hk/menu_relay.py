"""Private worker relay for the closed-by-default MENU.1 menu explanation (#1583, contract MENU.1.md).

The worker owns the DashScope key and the HK cash journal: one entry 9 image recognition recorded in the
translation journal (50 images a day) and up to two `menu.1` flash calls (M4 entry 19: 10 menus a day, ¥100
sublimit). The API process forwards the caller's own bearer and the bounded body over the private socket.

The body carries a menu photo. It is held in memory for this request only: nothing here logs, stores or echoes
the request body, and a body that fails validation is answered with a fixed error code (no pydantic message,
which would quote the base64 input).
"""

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
from cj_api.lio_menu import ROUTE, DashScopeMenu, MemoryMenuCache, MenuRequest, MenuService
from cj_api.plugin_tools import BEARER, PluginError, _authorize
from cj_api.translation import DashScopeTranslation, TranslationError
from cj_strict_json import reject_duplicates
from cj_usage.authorization_budget import AuthorizationBudget, HK_JOURNAL_ROOT
from cj_usage.menu_budget import MenuBudget
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.translation_budget import TranslationBudget

from .configuration import MENU_INTERNAL_SUBJECTS
from .plugin_roster import generate_plugin_subjects
from .translation_relay import TOKEN_LIMIT, _token_valid


SOCKET = Path('/run/g2c-demo/menu.sock')
# The photo is at most 3 MB - 4 KB, about 4 MiB as base64 inside the JSON (contract); 6 MiB leaves room.
MAX_BODY = 6 * 1024 * 1024
MAX_RESPONSE = 256 * 1024      # at most 30 short bilingual dishes
# One recognition and up to two flash calls (40 s client timeout each) behind a 45 s service deadline that is
# checked before each call, so a request can run past 45 s; the API waits for it.
RELAY_TIMEOUT = 150
RESPONSE_STATUS = {200, 400, 401, 403, 409, 413, 429, 502, 503}


def menu_request(token, raw, *, path=SOCKET):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(RELAY_TIMEOUT)
        connection.connect(str(path))
        connection.sendall(b'M' + token.encode('ascii') + b'\n' + len(raw).to_bytes(4, 'big') + raw)
        with connection.makefile('rb') as incoming:
            size = int.from_bytes(incoming.read(4), 'big')
            if not 0 < size <= MAX_RESPONSE:
                raise ValueError('bounded menu response required')
            response = incoming.read(size)
            if len(response) != size:
                raise ValueError('incomplete menu response')
            status, body = json.loads(response)
            if status not in RESPONSE_STATUS or type(body) is not dict:
                raise ValueError('invalid menu reply')
            return status, body


async def _bounded_body(request):
    if request.headers.get('content-type', '').partition(';')[0].strip().lower() != 'application/json':
        raise PluginError(400, 'invalid_request')
    declared = request.headers.get('content-length')
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY:
        raise PluginError(413, 'request_too_large')
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_BODY:
            raise PluginError(413, 'request_too_large')
        data.extend(chunk)
    return data


def register_menu_routes(app, *, send=menu_request):
    @app.post(ROUTE)
    async def execute(request: Request):
        try:
            supplied = request.headers.getlist('authorization')
            match = BEARER.fullmatch(supplied[0]) if len(supplied) == 1 else None
            if match is None:
                raise PluginError(401, 'sign_in_required')
            raw = await _bounded_body(request)
            status, body = await run_in_threadpool(send, match[1], bytes(raw))
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
    size = int.from_bytes(incoming.read(4), 'big')
    if not 0 < size <= MAX_BODY:
        raise PluginError(413, 'request_too_large')
    raw = incoming.read(size)
    if len(raw) != size or action != b'M':
        raise PluginError(400, 'invalid_request')
    if service is None:
        if disabled:
            raise PluginError(403, 'not_enabled')
        raise PluginError(503, 'unavailable')
    token = supplied[:-1].decode('ascii')
    principal = _authorize(checker, token, roster)
    owner = (principal.issuer, principal.subject)

    def authorize():
        current = _authorize(checker, token, roster)
        if (current.issuer, current.subject) != owner:
            raise PluginError(401, 'sign_in_required')

    try:
        document = MenuRequest.model_validate(
            json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate menu field')))
    except (ValueError, RecursionError):
        # pydantic's message quotes the input (the photo): only the fixed code leaves this function.
        raise PluginError(400, 'invalid_request') from None
    finally:
        del raw
    return service.explain(scope_for(*owner), document, authorize)


@contextmanager
def menu_socket(service, checker, roster, *, path=SOCKET, disabled=False):
    root = path.parent.lstat()
    if not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid() or stat.S_IMODE(root.st_mode) != 0o700:
        raise ValueError('owned private menu socket directory required')
    slots = BoundedSemaphore(2)    # each request holds up to 6 MiB plus the decoded photo

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
                except TranslationError:
                    status, body = 502, {'error': 'supplier_unavailable'}
                except (BudgetUnknown, psycopg.Error, sqlite3.Error, OSError, ValueError):
                    status, body = 503, {'error': 'unavailable'}
                finally:
                    slots.release()
            try:
                encoded = json.dumps([status, body], ensure_ascii=False, separators=(',', ':')).encode()
            except (TypeError, ValueError, UnicodeError):
                encoded = b'[502,{"error":"supplier_unavailable"}]'
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
                raise ValueError('invalid previous menu socket')
            path.unlink()
        with Server(str(path), Handler) as server:
            path.chmod(0o600)
            thread = Thread(target=server.serve_forever, daemon=True, name='menu-relay')
            thread.start()
            try:
                yield
            finally:
                server.shutdown()
                thread.join()
                path.unlink()


@contextmanager
def active_menu(runtime, authorization_guard):
    raw = os.environ.get(MENU_INTERNAL_SUBJECTS)
    service = checker = None
    roster = frozenset()
    if raw is not None:
        try:
            values = json.loads(raw)
            if type(values) is not list or not values or any(type(item) is not str for item in values):
                raise ValueError('explicit menu roster required')
            selected = frozenset(values)
            # M4 entry 19 (JT 2026-11-25, #1581/#1587): a non-empty subset of the G2C@01-99 cohort.
            if len(selected) != len(values) or not selected.issubset(generate_plugin_subjects()):
                raise ValueError('invalid menu roster')
            reader = DashScopeTranslation(os.environ['CJ_MODEL_API_KEY'])
            model = DashScopeMenu(os.environ['CJ_MODEL_API_KEY'])
            journal = AuthorizationBudget(HK_JOURNAL_ROOT, authorization_guard=authorization_guard, demo=True)
            checker = account_checker_for(runtime.auth, runtime.database(), selected_subjects=selected)
            service = MenuService(reader, model, MenuBudget(journal), TranslationBudget(journal), MemoryMenuCache())
            roster = selected
        except (KeyError, BudgetUnknown, CompositionUnavailable, psycopg.Error, sqlite3.Error,
                ValueError, OSError, RecursionError):
            service = checker = None
            roster = frozenset()
            print('ALERT menu_relay_configuration_unavailable', file=sys.stderr, flush=True)
    with ExitStack() as stack:
        try:
            stack.enter_context(menu_socket(service, checker, roster, disabled=raw is None))
        except (OSError, ValueError):
            print('ALERT menu_relay_socket_unavailable', file=sys.stderr, flush=True)
        yield
