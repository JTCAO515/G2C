"""Local synthetic receipts; not the CJ production database or authorization."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


@contextmanager
def connect(root):
    db = sqlite3.connect(Path(root) / 'receipts.sqlite', timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA synchronous=FULL')
    try:
        yield db
        db.commit()
    finally:
        db.close()


def initialize(root):
    Path(root).mkdir(parents=True, exist_ok=True)
    with connect(root) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS attempts (
          attempt_id TEXT PRIMARY KEY, principal TEXT NOT NULL,
          request_hash TEXT NOT NULL, state TEXT NOT NULL,
          response TEXT, reason TEXT);
        CREATE TABLE IF NOT EXISTS provider_dispatches (
          seq INTEGER PRIMARY KEY, attempt_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS business (
          principal TEXT, operation TEXT, action_id TEXT,
          input_hash TEXT NOT NULL, receipt TEXT NOT NULL,
          PRIMARY KEY(principal, operation, action_id));
        CREATE TABLE IF NOT EXISTS probes (label TEXT PRIMARY KEY, count INTEGER);
        ''')


def begin_attempt(root, attempt_id, principal, request_hash):
    """Atomically reserve one send. An existing unresolved reservation never sends."""
    with connect(root) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM attempts WHERE attempt_id=?', (attempt_id,)).fetchone()
        if row:
            if row['principal'] != principal or row['request_hash'] != request_hash:
                raise ValueError('ATTEMPT_INPUT_CONFLICT')
            if row['state'] == 'COMPLETE':
                return json.loads(row['response'])
            db.execute("UPDATE attempts SET state='UNKNOWN', reason='original_attempt_unresolved' WHERE attempt_id=?", (attempt_id,))
            return {'outcome': 'UNKNOWN', 'reason': 'original_attempt_unresolved', 'attempt_id': attempt_id}
        db.execute("INSERT INTO attempts VALUES (?,?,?,'INTENT',NULL,NULL)", (attempt_id, principal, request_hash))
    return None


def dispatch(root, attempt_id):
    with connect(root) as db:
        db.execute('INSERT INTO provider_dispatches(attempt_id) VALUES (?)', (attempt_id,))


def complete_attempt(root, attempt_id, response):
    with connect(root) as db:
        db.execute("UPDATE attempts SET state='COMPLETE', response=? WHERE attempt_id=?", (encode(response), attempt_id))


def unknown_attempt(root, attempt_id, reason):
    with connect(root) as db:
        db.execute("UPDATE attempts SET state='UNKNOWN', reason=? WHERE attempt_id=?", (reason, attempt_id))


def commit_business(root, principal, action_id, value):
    """Single local transaction combines input guard and receipt, across workflows."""
    with connect(root) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM business WHERE principal=? AND operation=? AND action_id=?',
                         (principal, 'synthetic_record', action_id)).fetchone()
        if row:
            if row['input_hash'] != digest(value):
                raise ValueError('BUSINESS_INPUT_CONFLICT')
            return json.loads(row['receipt'])
        receipt = {'principal': principal, 'operation': 'synthetic_record', 'action_id': action_id,
                   'value': value, 'result': 'COMMITTED'}
        db.execute('INSERT INTO business VALUES (?,?,?,?,?)',
                   (principal, 'synthetic_record', action_id, digest(value), encode(receipt)))
        return receipt


def probe(root, label):
    with connect(root) as db:
        db.execute('INSERT INTO probes VALUES (?,1) ON CONFLICT(label) DO UPDATE SET count=count+1', (label,))


def snapshot(root):
    with connect(root) as db:
        return {table: [dict(r) for r in db.execute(f'SELECT * FROM {table}')]
                for table in ('attempts', 'provider_dispatches', 'business', 'probes')}
