"""Private worker relay for the closed-by-default HOTEL.2 hotel search and its Trip.com hand-off (#1511).

The worker owns the Gaode key, the HK cash journal (M4 entry 12 item 3, separately counted, at most 3000
calls) and the hand-off store. The API process only forwards the caller's bearer and body over the private
socket, and resolves hand-off handles to the two fixed Trip.com pages.
"""

from contextlib import contextmanager, ExitStack
import fcntl
import html
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
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import psycopg
from starlette.requests import ClientDisconnect

from cj_api.composition import CompositionUnavailable
from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.local_app import scope_for
from cj_api.lio_hotel_search import (
    HANDOFF_PATH, ROUTE, TRIP_HOME, TRIP_LIST, HandoffStore, HotelSearchRequest, HotelSearchService,
)
from cj_api.nearby_tools import GaodeNearby
from cj_api.plugin_tools import BEARER, MAX_BODY, PluginError, _authorize, _bounded_body
from cj_strict_json import reject_duplicates
from cj_usage import hotel_budget
from cj_usage.authorization_budget import AuthorizationBudget, HK_JOURNAL_ROOT
from cj_usage.hotel_budget import HotelBudget
from cj_usage.metered_exit import BudgetUnknown

from .configuration import HOTEL_INTERNAL_SUBJECTS
from .plugin_roster import generate_plugin_subjects
from .taxi_runtime import relay_translator
from .translation_relay import TOKEN_LIMIT, _token_valid


SOCKET = Path('/run/g2c-demo/hotel.sock')
PUBLIC_ORIGIN = 'https://api-beta.go2china.space'
MAX_RESPONSE = 256 * 1024
# Three Gaode calls (8 s each at most) plus one English-name translation (12 s) fit below this bound.
RELAY_TIMEOUT = 45
RESPONSE_STATUS = {200, 400, 401, 403, 404, 409, 413, 429, 502, 503, 504}
HANDLE = re.compile(r'[A-Za-z0-9_-]{22}')
NOT_FOUND = ('<!doctype html><meta charset="utf-8"><title>Link expired</title>'
             '<p>This booking link has expired. Please search again in the Go2China app.</p>'
             '<p>预订链接已过期，请回到 Go2China 重新搜索。</p>')


def _exchange(message, *, path, timeout):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(str(path))
        connection.sendall(message)
        with connection.makefile('rb') as incoming:
            size = int.from_bytes(incoming.read(4), 'big')
            if not 0 < size <= MAX_RESPONSE:
                raise ValueError('bounded hotel response required')
            response = incoming.read(size)
            if len(response) != size:
                raise ValueError('incomplete hotel response')
            status, body = json.loads(response)
            if status not in RESPONSE_STATUS or type(body) is not dict:
                raise ValueError('invalid hotel reply')
            return status, body


def hotel_search_request(token, raw, *, path=SOCKET):
    return _exchange(b'S' + token.encode('ascii') + b'\n' + len(raw).to_bytes(4, 'big') + raw,
                     path=path, timeout=RELAY_TIMEOUT)


def hotel_handoff_request(handle, *, path=SOCKET):
    return _exchange(b'O' + handle.encode('ascii') + b'\n', path=path, timeout=5)


def _fixed_target(url):
    return type(url) is str and (url == TRIP_HOME or url.startswith(TRIP_LIST + '?'))


def register_hotel_routes(app, *, search=hotel_search_request, handoff=hotel_handoff_request):
    @app.post(ROUTE)
    async def execute(request: Request):
        try:
            supplied = request.headers.getlist('authorization')
            match = BEARER.fullmatch(supplied[0]) if len(supplied) == 1 else None
            if match is None:
                raise PluginError(401, 'sign_in_required')
            raw = await _bounded_body(request)
            status, body = await run_in_threadpool(search, match[1], bytes(raw))
        except PluginError as error:
            status, body = error.status, {'error': error.code}
        except ClientDisconnect:
            status, body = 400, {'error': 'invalid_request'}
        except (OSError, ValueError):
            status, body = 503, {'error': 'unavailable'}
        return JSONResponse(body, status_code=status, headers={'Cache-Control': 'no-store'})

    @app.get(HANDOFF_PATH + '{handle}')
    async def out(handle: str):
        # Opened in the browser without a bearer: the unguessable handle is the only capability.
        headers = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'}
        target = None
        if HANDLE.fullmatch(handle):
            try:
                status, body = await run_in_threadpool(handoff, handle)
            except (OSError, ValueError):
                status, body = 503, {}
            if status == 200 and _fixed_target(body.get('url')):
                target = body['url']
            elif status not in (200, 404):
                return HTMLResponse(html.escape('Temporarily unavailable. 暂时无法打开，请稍后再试。'),
                                    status_code=503, headers=headers)
        if target is None:
            return HTMLResponse(NOT_FOUND, status_code=404, headers=headers)
        return RedirectResponse(target, status_code=302, headers=headers)


def _dispatch(action, incoming, service, handoffs, checker, roster, disabled):
    if action == b'O':
        supplied = incoming.readline(64)
        handle = supplied[:-1].decode('ascii', 'replace') if supplied.endswith(b'\n') else ''
        url = handoffs.get(handle) if handoffs is not None else None
        if url is None:
            raise PluginError(404, 'not_found')
        return dict(url=url)
    supplied = incoming.readline(TOKEN_LIMIT + 2)
    if not supplied.endswith(b'\n') or not _token_valid(supplied[:-1]):
        raise PluginError(401, 'sign_in_required')
    token = supplied[:-1].decode('ascii')
    size = int.from_bytes(incoming.read(4), 'big')
    if not 0 < size <= MAX_BODY:
        raise PluginError(413, 'request_too_large')
    raw = incoming.read(size)
    if len(raw) != size or action != b'S':
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

    try:
        document = HotelSearchRequest.model_validate(
            json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate hotel field')))
    except (ValueError, RecursionError):
        raise PluginError(400, 'invalid_request') from None
    return service.search(scope_for(*owner), document, authorize, token=token)


@contextmanager
def hotel_socket(service, handoffs, checker, roster, *, path=SOCKET, disabled=False):
    root = path.parent.lstat()
    if not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid() or stat.S_IMODE(root.st_mode) != 0o700:
        raise ValueError('owned private hotel socket directory required')
    # The bearer-less hand-off lookup must never starve signed-in searches, nor slow searches the hand-off.
    search_slots, handoff_slots = BoundedSemaphore(4), BoundedSemaphore(4)

    class Handler(StreamRequestHandler):
        def handle(self):
            self.request.settimeout(5)
            try:
                action = self.rfile.read(1)
            except OSError:
                return
            slots = handoff_slots if action == b'O' else search_slots
            if not slots.acquire(blocking=False):
                status, body = 503, {'error': 'unavailable'}
            else:
                try:
                    status, body = 200, _dispatch(action, self.rfile, service, handoffs, checker, roster, disabled)
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
                raise ValueError('invalid previous hotel socket')
            path.unlink()
        with Server(str(path), Handler) as server:
            path.chmod(0o600)
            thread = Thread(target=server.serve_forever, daemon=True, name='hotel-relay')
            thread.start()
            try:
                yield
            finally:
                server.shutdown()
                thread.join()
                path.unlink()


@contextmanager
def active_hotel(runtime, authorization_guard):
    raw = os.environ.get(HOTEL_INTERNAL_SUBJECTS)
    service = handoffs = checker = None
    roster = frozenset()
    if raw is not None:
        try:
            values = json.loads(raw)
            if type(values) is not list or not values or any(type(item) is not str for item in values):
                raise ValueError('explicit hotel roster required')
            selected = frozenset(values)
            # M4 entry 12 item 3 (JT 2026-11-25, #1534): a non-empty subset of the G2C@01-99 internal cohort.
            if len(selected) != len(values) or not selected.issubset(generate_plugin_subjects()):
                raise ValueError('invalid hotel roster')
            provider = GaodeNearby(os.environ['CJ_AMAP_WEB_KEY'], operations=hotel_budget.OPERATIONS)
            journal = AuthorizationBudget(HK_JOURNAL_ROOT, authorization_guard=authorization_guard, demo=True)
            checker = account_checker_for(runtime.auth, runtime.database(), selected_subjects=selected)
            handoffs = HandoffStore()
            service = HotelSearchService(provider, HotelBudget(journal), handoffs, public_origin=PUBLIC_ORIGIN,
                                         translator=relay_translator())
            roster = selected
        except (KeyError, BudgetUnknown, CompositionUnavailable, psycopg.Error, sqlite3.Error,
                ValueError, OSError, RecursionError):
            service = handoffs = checker = None
            roster = frozenset()
            print('ALERT hotel_relay_configuration_unavailable', file=sys.stderr, flush=True)
    with ExitStack() as stack:
        try:
            stack.enter_context(hotel_socket(service, handoffs, checker, roster, disabled=raw is None))
        except (OSError, ValueError):
            print('ALERT hotel_relay_socket_unavailable', file=sys.stderr, flush=True)
        yield
