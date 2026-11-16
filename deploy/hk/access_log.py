"""Content-free structured API access log for the Hong Kong synthetic beta (#1036).

Arrival and completion lines per non-health HTTP exchange: UTC time, a fresh
exchange ID, the matched route *template* after routing (never a
path parameter value), method, status, durations, the server-generated request
ID, the client build number when the stock iOS User-Agent or the explicit build
header carries one, a coarse error class and the exchange outcome.

Never read or written: query strings, other header values (Authorization,
cookies, invitation codes), request/response bodies (messages, Memory), client
addresses, account or subject identifiers, exception text.

Storage is a dedicated 0700 directory owned by the API UID, separate from the
raw-original/evidence/rejected-intake stores: one ``access-YYYY-MM-DD.jsonl``
(0600) per UTC day, pruned after ``RETENTION_DAYS`` and capped per day. If the
directory is absent or unqualified, lines go to stderr (container log) instead
and an ALERT is printed; logging failures never change an HTTP response.
Arrival records have no route or response request ID. An arrival proves that
the ASGI app was entered even if the process dies before a response. Missing
completion is an unresolved exchange, not proof of a still-running task.

Query (read-only, from the app image with the directory mounted read-only)::

    python -B -m deploy.hk.access_log query --since 2026-11-15T21:30:00+08:00 \
        --until 2026-11-15T22:00:00+08:00 [--min-status 400] [--route /v1/...]

Add ``--phase all`` to include arrival lines. Historical v1 completion-only
records remain readable; the default counts only completions.
"""
import argparse
import json
import os
import re
import stat
import sys
import threading
import time
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from pathlib import Path

VERSION = 'G2C-HK-access-log.2'
DIRECTORY = Path('/access-log')
RETENTION_DAYS = 14
DAILY_CAP_BYTES = 16 * 1024 * 1024
HEALTH_PATHS = frozenset({'/health/live', '/health/ready'})
METHODS = frozenset({'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'})
BUILD_HEADER = b'x-g2c-app-build'
_FILE = re.compile(r'access-([0-9]{4}-[0-9]{2}-[0-9]{2})\.jsonl')
_BUILD = re.compile(r'[0-9]{1,6}(?:\.[0-9]{1,6}){0,3}')
# Stock URLSession agent: "<bundle name>/<CFBundleVersion> CFNetwork/<v> Darwin/<v>".
_STOCK_AGENT = re.compile(r'[^/\s]{1,64}/([0-9]{1,6}(?:\.[0-9]{1,6}){0,3}) CFNetwork/[0-9.]{1,32} Darwin/[0-9.]{1,32}')
_REQUEST_ID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
_GATE = re.compile(r'[a-z_]{1,48}')
_ROUTE = re.compile(r'/[A-Za-z0-9_./{}:-]{0,200}')
_ERRORS = {400: 'bad_request', 401: 'unauthenticated', 403: 'forbidden', 404: 'not_found',
           405: 'method_not_allowed', 409: 'conflict', 410: 'gone', 412: 'precondition_failed',
           413: 'payload_too_large', 415: 'unsupported_media_type', 422: 'invalid_input',
           428: 'precondition_required', 429: 'rate_limited', 500: 'internal', 502: 'bad_gateway',
           503: 'unavailable', 504: 'timeout'}


def alert(code):
    print('ALERT ' + code, file=sys.stderr, flush=True)


def client_build(headers):
    """Only a validated build number; the raw header values are never kept."""
    agent = explicit = None
    for name, value in headers:
        name = name.lower()
        if name == BUILD_HEADER and explicit is None:
            explicit = value
        elif name == b'user-agent' and agent is None:
            agent = value
    if explicit is not None:
        text = explicit.decode('ascii', 'replace')
        return text if _BUILD.fullmatch(text) else None
    if agent is not None:
        match = _STOCK_AGENT.fullmatch(agent.decode('ascii', 'replace'))
        if match is not None:
            return match[1]
    return None


def error_class(status, gate=None):
    if gate is not None:
        return 'deployment_' + gate
    if status is None:
        return 'no_response'
    if status < 400:
        return None
    return _ERRORS.get(status, 'client_error' if status < 500 else 'server_error')


def route_template(scope):
    route = scope.get('route')
    template = getattr(route, 'path', None)
    if isinstance(template, str) and _ROUTE.fullmatch(template):
        return template
    # Only fixed literal health paths may be recorded without a matched route.
    return scope.get('path') if scope.get('path') in HEALTH_PATHS else None


def _stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


class Sink:
    """Append-only daily files in one qualified private directory."""

    def __init__(self, directory=DIRECTORY, *, retention_days=RETENTION_DAYS, daily_cap=DAILY_CAP_BYTES,
                 clock=time.time, fallback=None):
        self.directory = Path(directory)
        self.retention_days = retention_days
        self.daily_cap = daily_cap
        self.clock = clock
        self.fallback = fallback
        self._lock = threading.Lock()
        self._day = None
        self._fd = None
        self._size = 0
        self._alerted = set()
        self.enabled = self._qualified()

    def _alert_once(self, code):
        if code not in self._alerted:
            self._alerted.add(code)
            alert(code)

    def _qualified(self):
        try:
            info = self.directory.lstat()
        except FileNotFoundError:
            self._alert_once('access_log_directory_absent')
            return False
        except OSError:
            self._alert_once('access_log_directory_unqualified')
            return False
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            self._alert_once('access_log_directory_unqualified')
            return False
        return True

    def _emit_fallback(self, line):
        stream = self.fallback if self.fallback is not None else sys.stderr
        stream.write('ACCESS ' + line.decode())
        stream.flush()

    def _rotate(self, day):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self._day = day
        self.prune(day)
        path = self.directory / ('access-' + day + '.jsonl')
        self._fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        info = os.fstat(self._fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            os.close(self._fd)
            self._fd = None
            raise OSError('unqualified access log file')
        self._size = info.st_size

    def prune(self, today):
        oldest = (datetime.strptime(today, '%Y-%m-%d') - timedelta(days=self.retention_days - 1)).strftime('%Y-%m-%d')
        for entry in self.directory.iterdir():
            match = _FILE.fullmatch(entry.name)
            if match is not None and match[1] < oldest and entry.is_file() and not entry.is_symlink():
                entry.unlink()

    def write(self, record):
        line = (json.dumps(record, ensure_ascii=True, separators=(',', ':'), sort_keys=True) + '\n').encode()
        with self._lock:
            if not self.enabled:
                self._emit_fallback(line)
                return
            try:
                day = datetime.fromtimestamp(self.clock(), timezone.utc).strftime('%Y-%m-%d')
                if day != self._day or self._fd is None:
                    self._rotate(day)
                if self._size + len(line) > self.daily_cap:
                    self._alert_once('access_log_daily_cap_reached_' + day)
                    return
                os.write(self._fd, line)
                self._size += len(line)
            except OSError:
                self._alert_once('access_log_write_failed')
                self._day = None
                self._emit_fallback(line)


class AccessLog:
    """Pure ASGI wrapper: observes status/timing, never the bodies, and never alters the exchange."""

    def __init__(self, app, sink, clock=time.time, timer=time.perf_counter):
        self.app = app
        self.sink = sink
        self.clock = clock
        self.timer = timer

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        at = self.clock()
        started = self.timer()
        exchange_id = str(uuid4())
        seen = {'status': None, 'first': None, 'request_id': None, 'done': False}

        # Routing and the response trace ID do not exist yet. Never substitute
        # a raw path or a client-controlled ID for either of them.
        if scope.get('path') not in HEALTH_PATHS:
            try:
                self.sink.write({
                    'v': VERSION, 'phase': 'started', 'exchange_id': exchange_id,
                    'ts': _stamp(at), 'method': scope.get('method') if scope.get('method') in METHODS else 'OTHER',
                    'route': None, 'status': None, 'duration_ms': None, 'ttfb_ms': None,
                    'request_id': None, 'app_build': client_build(scope.get('headers', ())),
                    'error_class': None, 'outcome': 'in_flight',
                })
            except Exception:
                alert('access_log_record_failed')

        async def observe(message):
            if message['type'] == 'http.response.start':
                seen['status'] = message['status']
                seen['first'] = self.timer()
                for name, value in message.get('headers', ()):
                    if name.lower() == b'x-request-id':
                        text = value.decode('ascii', 'replace')
                        seen['request_id'] = text if _REQUEST_ID.fullmatch(text) else None
            await send(message)
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                seen['done'] = True

        failed = False
        try:
            await self.app(scope, receive, observe)
        except BaseException:
            failed = True
            raise
        finally:
            try:
                self._record(scope, at, started, seen, failed, exchange_id)
            except Exception:
                alert('access_log_record_failed')

    def _record(self, scope, at, started, seen, failed, exchange_id):
        path = scope.get('path')
        if path in HEALTH_PATHS and seen['status'] == 200 and seen['done']:
            return  # container healthcheck every 15 s; only non-200 health is useful
        gate = scope.get('state', {}).get('access_gate') if isinstance(scope.get('state'), dict) else None
        if gate is not None and (not isinstance(gate, str) or not _GATE.fullmatch(gate)):
            gate = 'unclassified'
        ended = self.timer()
        if seen['done']:
            outcome = 'completed'
        elif seen['status'] is not None:
            outcome = 'incomplete'
        else:
            outcome = 'exception' if failed else 'no_response'
        method = scope.get('method')
        self.sink.write({
            'v': VERSION,
            'phase': 'finished',
            'exchange_id': exchange_id,
            'ts': _stamp(at),
            'method': method if method in METHODS else 'OTHER',
            'route': route_template(scope),
            'status': seen['status'],
            'duration_ms': round((ended - started) * 1000, 1),
            'ttfb_ms': None if seen['first'] is None else round((seen['first'] - started) * 1000, 1),
            'request_id': seen['request_id'],
            'app_build': client_build(scope.get('headers', ())),
            'error_class': 'exception' if failed and seen['status'] is None else error_class(seen['status'], gate),
            'outcome': outcome,
        })


def _instant(text):
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        raise argparse.ArgumentTypeError('explicit UTC offset required, e.g. +08:00 or Z')
    return value.astimezone(timezone.utc)


def query(directory, since, until, *, min_status=None, route=None, phase='finished', out=sys.stdout):
    """Read-only: print matching lines in time order, then one summary line."""
    if not since < until or until - since > timedelta(days=RETENTION_DAYS):
        raise ValueError('bounded window within retention required')
    rows = []
    day = since.date()
    while day <= until.date():
        path = Path(directory) / ('access-' + day.isoformat() + '.jsonl')
        if path.is_file() and not path.is_symlink():
            for line in path.read_text().splitlines():
                record = json.loads(line)
                stamp = datetime.fromisoformat(record['ts'].replace('Z', '+00:00'))
                if not since <= stamp < until:
                    continue
                # v1 is the historical completion-only format. The default
                # keeps its count/status semantics; --phase all shows arrivals.
                if phase != 'all' and record.get('phase', 'finished') != phase:
                    continue
                # A missing status (no response sent) is always a failure worth showing.
                if min_status is not None and record['status'] is not None and record['status'] < min_status:
                    continue
                if route is not None and record['route'] != route:
                    continue
                rows.append((stamp, line))
        day += timedelta(days=1)
    rows.sort(key=lambda row: row[0])
    statuses = {}
    for _, line in rows:
        out.write(line + '\n')
        status = json.loads(line)['status']
        statuses[str(status)] = statuses.get(str(status), 0) + 1
    out.write(json.dumps({'summary': True, 'since': since.isoformat(), 'until': until.isoformat(),
                          'count': len(rows), 'by_status': statuses}, sort_keys=True) + '\n')
    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only HK access log query')
    sub = parser.add_subparsers(dest='command', required=True)
    q = sub.add_parser('query')
    q.add_argument('--directory', type=Path, default=DIRECTORY)
    q.add_argument('--since', type=_instant, required=True)
    q.add_argument('--until', type=_instant, required=True)
    q.add_argument('--min-status', type=int)
    q.add_argument('--route')
    q.add_argument('--phase', choices=('started', 'finished', 'all'), default='finished')
    args = parser.parse_args(argv)
    query(args.directory, args.since, args.until, min_status=args.min_status, route=args.route, phase=args.phase)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
