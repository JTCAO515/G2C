"""Private worker relay for TRANSPORT.1 trains: one metered AMap cross-city transit call per search (#1520).

The worker owns the AMap key and the HK cash journal (M4 entry 12 item 4: `amap-transit.1`, route kind,
separately counted, 30 a day per account, 1500 in all). The API's TransportService reaches it through
`TransitRelayClient.trains(token, request_id, origin_id, destination_id, day)` with the caller's own bearer.
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

import psycopg

from cj_api.composition import CompositionUnavailable
from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.local_app import scope_for
from cj_api.lio_transport_rail import TransitRailService, transit_provider
from cj_api.plugin_tools import PluginError, _authorize
from cj_strict_json import reject_duplicates
from cj_usage.authorization_budget import AuthorizationBudget, HK_JOURNAL_ROOT
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.transit_budget import TransitBudget

from .configuration import TRANSIT_INTERNAL_SUBJECTS
from .plugin_roster import generate_plugin_subjects
from .translation_relay import TOKEN_LIMIT, _token_valid


SOCKET = Path('/run/g2c-demo/transit.sock')
MAX_REQUEST = 512
MAX_RESPONSE = 128 * 1024
# One AMap call (8 s per socket operation) plus admission; the API answers this mode as unavailable after it.
RELAY_TIMEOUT = 20
RESPONSE_STATUS = {200, 400, 401, 403, 409, 413, 429, 502, 503, 504}
FIELDS = {'request_id', 'origin_id', 'destination_id', 'day'}


def transit_request(token, raw, *, path=SOCKET):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(RELAY_TIMEOUT)
        connection.connect(str(path))
        connection.sendall(b'T' + token.encode('ascii') + b'\n' + len(raw).to_bytes(4, 'big') + raw)
        with connection.makefile('rb') as incoming:
            size = int.from_bytes(incoming.read(4), 'big')
            if not 0 < size <= MAX_RESPONSE:
                raise ValueError('bounded transit response required')
            response = incoming.read(size)
            if len(response) != size:
                raise ValueError('incomplete transit response')
            status, body = json.loads(response)
            if status not in RESPONSE_STATUS or type(body) is not dict:
                raise ValueError('invalid transit reply')
            return status, body


class TransitRelayClient:
    """The `rail` collaborator of TransportService in the API process."""

    def __init__(self, send=transit_request):
        self.send = send

    def trains(self, token, request_id, origin_id, destination_id, day):
        raw = json.dumps(dict(request_id=request_id, origin_id=origin_id, destination_id=destination_id, day=day),
                         separators=(',', ':')).encode()
        status, body = self.send(token, raw)
        if status != 200:
            code = body.get('error')
            raise PluginError(status, code if type(code) is str else 'unavailable')
        items = body.get('items')
        if type(items) is not list:
            raise ValueError('transit items required')
        return items


def _dispatch(incoming, service, checker, roster, disabled):
    action = incoming.read(1)
    supplied = incoming.readline(TOKEN_LIMIT + 2)
    if not supplied.endswith(b'\n') or not _token_valid(supplied[:-1]):
        raise PluginError(401, 'sign_in_required')
    token = supplied[:-1].decode('ascii')
    size = int.from_bytes(incoming.read(4), 'big')
    if not 0 < size <= MAX_REQUEST:
        raise PluginError(413, 'request_too_large')
    raw = incoming.read(size)
    if len(raw) != size or action != b'T':
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
        document = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate transit field'))
    except (ValueError, RecursionError):
        raise PluginError(400, 'invalid_request') from None
    if type(document) is not dict or set(document) != FIELDS or any(type(document[k]) is not str for k in FIELDS):
        raise PluginError(400, 'invalid_request')
    items = service.trains(scope_for(*owner), document['request_id'], document['origin_id'],
                           document['destination_id'], document['day'], authorize)
    return dict(items=items)


@contextmanager
def transit_socket(service, checker, roster, *, path=SOCKET, disabled=False):
    root = path.parent.lstat()
    if not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid() or stat.S_IMODE(root.st_mode) != 0o700:
        raise ValueError('owned private transit socket directory required')
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
                raise ValueError('invalid previous transit socket')
            path.unlink()
        with Server(str(path), Handler) as server:
            path.chmod(0o600)
            thread = Thread(target=server.serve_forever, daemon=True, name='transit-relay')
            thread.start()
            try:
                yield
            finally:
                server.shutdown()
                thread.join()
                path.unlink()


@contextmanager
def active_transit(runtime, authorization_guard):
    raw = os.environ.get(TRANSIT_INTERNAL_SUBJECTS)
    service = checker = None
    roster = frozenset()
    if raw is not None:
        try:
            values = json.loads(raw)
            if type(values) is not list or not values or any(type(item) is not str for item in values):
                raise ValueError('explicit transit roster required')
            selected = frozenset(values)
            # M4 entry 12 item 4 (JT 2026-11-25, #1531): a non-empty subset of the G2C@01-99 internal cohort.
            if len(selected) != len(values) or not selected.issubset(generate_plugin_subjects()):
                raise ValueError('invalid transit roster')
            provider = transit_provider(os.environ['CJ_AMAP_WEB_KEY'])
            journal = AuthorizationBudget(HK_JOURNAL_ROOT, authorization_guard=authorization_guard, demo=True)
            checker = account_checker_for(runtime.auth, runtime.database(), selected_subjects=selected)
            service = TransitRailService(provider, TransitBudget(journal))
            roster = selected
        except (KeyError, BudgetUnknown, CompositionUnavailable, psycopg.Error, sqlite3.Error,
                ValueError, OSError, RecursionError):
            service = checker = None
            roster = frozenset()
            print('ALERT transit_relay_configuration_unavailable', file=sys.stderr, flush=True)
    with ExitStack() as stack:
        try:
            stack.enter_context(transit_socket(service, checker, roster, disabled=raw is None))
        except (OSError, ValueError):
            print('ALERT transit_relay_socket_unavailable', file=sys.stderr, flush=True)
        yield
