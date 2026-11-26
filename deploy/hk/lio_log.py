"""Separate, content-free retention for ``LIO_`` diagnostic lines (#1828).

The ``cj_usage.audit`` logger's ``LIO_*`` lines (pipeline refusals, uncaught
errors, first-text timing ...) are copied into one qualified host directory
mounted at ``/lio-log``: one ``lio-<role>-YYYY-MM-DD.jsonl`` (0600) per process
role and UTC day, kept ``RETENTION_DAYS`` and capped per day. The directory is a
host bind mount, so the lines survive container cutovers; the container log
still receives every line as before.

Only ``key=value`` tokens are kept. ``run_id``/``message_id``/``conversation_id``
values are replaced by a 12-hex SHA-256 prefix; tokens whose key is a subject,
scope, user, text, content, prompt, reply, answer or free-form detail are dropped; any other value outside a short safe
alphabet becomes ``redacted``. No conversation text or user identifier is stored.

If the directory is absent or not owned 0700 by this UID, nothing is written and
one ``ALERT lio_log_directory_*`` line goes to stderr; logging never raises.

Query (read-only)::

    python -B -m deploy.hk.lio_log query --since 2026-11-26 [--prefix LIO_PIPELINE_]
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time

VERSION = 'G2C-HK-lio-log.1'
DIRECTORY = Path('/lio-log')
RETENTION_DAYS = 30
DAILY_CAP_BYTES = 8 * 1024 * 1024
ROLES = ('api', 'worker')
_NAME = re.compile(r'LIO_[A-Z0-9_]{1,64}')
_TOKEN = re.compile(r'([a-z][a-z0-9_]{0,48})=(\S{0,400})')
_SAFE = re.compile(r'[A-Za-z0-9_.:,/+-]{0,200}')
_HASHED = frozenset({'run_id', 'message_id', 'conversation_id'})
_DROPPED = frozenset({'subject', 'scope', 'user', 'user_id', 'text', 'content', 'prompt', 'reply', 'answer', 'detail'})
_DROPPED_SUFFIXES = ('_subject', '_scope', '_text', '_content', '_prompt')
_FILE = re.compile(r'lio-(api|worker)-([0-9]{4}-[0-9]{2}-[0-9]{2})\.jsonl')


def sanitize(message):
    """``LIO_NAME k=v ...`` with identifiers hashed and anything unsafe removed; None if not a LIO_ line."""
    name, _, rest = message.partition(' ')
    if _NAME.fullmatch(name) is None:
        return None
    tokens = []
    for part in rest.split():
        match = _TOKEN.fullmatch(part)
        if match is None:
            continue
        key, value = match.groups()
        if key in _DROPPED or key.endswith(_DROPPED_SUFFIXES):
            continue
        if key in _HASHED:
            value = hashlib.sha256(value.encode()).hexdigest()[:12]
        elif _SAFE.fullmatch(value) is None:
            value = 'redacted'
        tokens.append(key + '=' + value)
    return ' '.join([name, *tokens])


class Store:
    """Append-only daily files in one qualified private directory."""

    def __init__(self, role, directory=DIRECTORY, *, retention_days=RETENTION_DAYS, daily_cap=DAILY_CAP_BYTES,
                 clock=time.time):
        if role not in ROLES:
            raise ValueError('explicit LIO log role required')
        self.role, self.directory, self.clock = role, Path(directory), clock
        self.retention_days, self.daily_cap = retention_days, daily_cap
        self._lock = threading.Lock()
        self._day = self._fd = None
        self._size = 0
        self._alerted = set()
        self.enabled = self._qualified()

    def _alert_once(self, code):
        if code not in self._alerted:
            self._alerted.add(code)
            print('ALERT ' + code, file=sys.stderr, flush=True)

    def _qualified(self):
        try:
            info = self.directory.lstat()
        except FileNotFoundError:
            self._alert_once('lio_log_directory_absent')
            return False
        except OSError:
            self._alert_once('lio_log_directory_unqualified')
            return False
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            self._alert_once('lio_log_directory_unqualified')
            return False
        return True

    def _rotate(self, day):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self._day = day
        self.prune(day)
        path = self.directory / ('lio-%s-%s.jsonl' % (self.role, day))
        self._fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        info = os.fstat(self._fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            os.close(self._fd)
            self._fd = None
            raise OSError('unqualified LIO log file')
        self._size = info.st_size

    def prune(self, today):
        oldest = (datetime.strptime(today, '%Y-%m-%d') - timedelta(days=self.retention_days - 1)).strftime('%Y-%m-%d')
        for entry in self.directory.iterdir():
            match = _FILE.fullmatch(entry.name)
            if match and match[1] == self.role and match[2] < oldest and entry.is_file() and not entry.is_symlink():
                entry.unlink()

    def write(self, line):
        if not self.enabled:
            return
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        record = (json.dumps(dict(version=VERSION, at=now.isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
                                  role=self.role, line=line), separators=(',', ':')) + '\n').encode()
        with self._lock:
            try:
                day = now.strftime('%Y-%m-%d')
                if day != self._day or self._fd is None:
                    self._rotate(day)
                if self._size + len(record) > self.daily_cap:
                    self._alert_once('lio_log_daily_cap_reached_' + day)
                    return
                os.write(self._fd, record)
                self._size += len(record)
            except OSError:
                self._alert_once('lio_log_write_failed')


class Handler(logging.Handler):
    """Copies sanitized LIO_ lines to the store; never raises into the caller."""

    def __init__(self, store):
        super().__init__(logging.INFO)
        self.store = store

    def emit(self, record):
        try:
            line = sanitize(record.getMessage())
            if line is not None:
                self.store.write(line)
        except Exception:
            pass


def install(role, logger_name='cj_usage.audit', directory=DIRECTORY):
    handler = Handler(Store(role, directory))
    logging.getLogger(logger_name).addHandler(handler)
    return handler


def query(directory, since, prefix, output):
    for path in sorted(Path(directory).iterdir()):
        match = _FILE.fullmatch(path.name)
        if match is None or match[2] < since:
            continue
        with path.open(encoding='utf-8') as source:
            for raw in source:
                value = json.loads(raw)
                if value.get('version') == VERSION and value['line'].startswith(prefix):
                    output.write(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    read = commands.add_parser('query')
    read.add_argument('--since', required=True, type=lambda s: datetime.strptime(s, '%Y-%m-%d').strftime('%Y-%m-%d'))
    read.add_argument('--prefix', default='LIO_')
    read.add_argument('--directory', default=str(DIRECTORY))
    args = parser.parse_args(argv)
    query(args.directory, args.since, args.prefix, sys.stdout)


if __name__ == '__main__':
    main()
