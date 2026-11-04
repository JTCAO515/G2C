"""M4 authorization ceiling, in addition to (never instead of) the RUN Meter.

One durable intent per original Meter attempt; no retry or financial settlement.
All attempts retain a conservative CNY hold when actual billing is unavailable.
The operator keeps this journal across releases/restores, outside database dumps.
"""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
from zoneinfo import ZoneInfo

from .metered_exit import BudgetUnknown

LIMITS={'model':(227,1),'place':(600,1),'route':(300,1),'weather':(100,1),'fact':(120,0)}
DEADLINE=datetime(2026,12,1,tzinfo=ZoneInfo('Asia/Shanghai'))
MAC_PRODUCER='codex-mac'
HK_PRODUCER='hk-beta-47.83.147.176'
HK_JOURNAL_ROOT=Path('/home/cj/.local/share/g2c/m4-real-services')
HK_ANCHOR=Path('/control/budget/adoption.json')


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')


class AuthorizationBudget:
    def __init__(self,root,*,clock=lambda:datetime.now(ZoneInfo('Asia/Shanghai')),authorization_guard=None):
        self.root=Path(root);self.clock=clock;self.authorization_guard=authorization_guard
        self.producer=os.environ.get('CJ_M4_BUDGET_PRODUCER',MAC_PRODUCER)
        if self.producer not in (MAC_PRODUCER,HK_PRODUCER):raise BudgetUnknown('explicit M4 producer required')
        if self.producer==HK_PRODUCER and (self.root!=HK_JOURNAL_ROOT or not (self.root/'m4-outflows.sqlite').is_file() or not HK_ANCHOR.is_file()):
            raise BudgetUnknown('existing_unique_HK_journal_and_control_required')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=self.root/'m4-outflows.sqlite'
        with self.connect() as db:
            if self.producer==MAC_PRODUCER:
                db.execute('CREATE TABLE IF NOT EXISTS attempt(id TEXT PRIMARY KEY,kind TEXT NOT NULL,input_sha TEXT NOT NULL,state TEXT NOT NULL,receipt TEXT)')
                db.execute('CREATE TABLE IF NOT EXISTS producer(singleton INTEGER PRIMARY KEY CHECK(singleton=1),identity TEXT NOT NULL,ledger_id TEXT NOT NULL)')
                db.execute('INSERT OR IGNORE INTO producer VALUES(1,?,?)',(MAC_PRODUCER,uuid.uuid4().hex))
            self.ledger_id=db.execute('SELECT ledger_id FROM producer WHERE singleton=1').fetchone()[0]
            if self.producer==HK_PRODUCER:self.require_producer(db)
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        connection=sqlite3.connect(self.path.resolve().as_uri()+('?mode=rw' if self.producer==HK_PRODUCER else '?mode=rwc'),uri=True,timeout=10)
        connection.execute('PRAGMA synchronous=FULL')
        try:
            with connection:yield connection
        finally:connection.close()

    def check_date(self):
        now=self.clock()
        if now.tzinfo is None or now>=DEADLINE:raise BudgetUnknown('M4 authorization expired')
        if self.authorization_guard is not None:self.authorization_guard()

    def require_producer(self,db):
        if db.execute('SELECT identity,ledger_id FROM producer WHERE singleton=1').fetchone()!=(self.producer,self.ledger_id):
            raise BudgetUnknown('M4 journal moved; original producer is read only')
        if self.producer==MAC_PRODUCER and (self.root/'transfer.json').exists():
            raise BudgetUnknown('M4 original Mac transfer is read only')
        if self.producer==HK_PRODUCER:
            anchor=json.loads(HK_ANCHOR.read_bytes())
            if (anchor['state']!='ADOPTED' or anchor['ledger_id']!=self.ledger_id
                    or db.execute('SELECT count(*) FROM attempt').fetchone()[0]<anchor['attempt_count']):
                raise BudgetUnknown('M4 non-restored adoption control differs')

    def begin(self,attempt,kind,raw):
        self.check_date()
        if kind not in LIMITS or type(attempt) is not str or not 1<=len(attempt)<=128:
            raise BudgetUnknown('M4 original attempt unavailable')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.require_producer(db)
            if db.execute('SELECT 1 FROM attempt WHERE id=?',(attempt,)).fetchone():
                raise BudgetUnknown('M4 original attempt is read only')
            counts=dict(db.execute('SELECT kind,count(*) FROM attempt GROUP BY kind'))
            # M1 #2 retains thirteen CNY holds. Never release UNKNOWN or assume a
            # fresh quota when the current operation/period/database changes.
            if counts.get(kind,0)>=LIMITS[kind][0]:raise BudgetUnknown('M4 call allowance exhausted')
            if kind!='model' and sum(counts.get(k,0)*LIMITS[k][1] for k in LIMITS if k!='model')+LIMITS[kind][1]>80:
                raise BudgetUnknown('M4 tool authorization stop threshold')
            db.execute('INSERT INTO attempt VALUES(?,?,?,\'INTENT\',NULL)',
                       (attempt,kind,hashlib.sha256(raw).hexdigest()))

    def finish(self,attempt,receipt):
        # The producer supplies bounded metadata only; keys/body/text never enter.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.require_producer(db)
            if 'receipt_sha256' in receipt and db.execute("SELECT 1 FROM attempt WHERE id<>? AND kind='model' AND json_extract(receipt,'$.receipt_sha256')=?",(attempt,receipt['receipt_sha256'])).fetchone():
                raise BudgetUnknown('M4 supplier receipt identity reused; original outcome unknown')
            if db.execute('UPDATE attempt SET state=\'RECEIVED\',receipt=? WHERE id=? AND state=\'INTENT\'',
                          (canonical(receipt).decode(),attempt)).rowcount!=1:
                raise BudgetUnknown('M4 original receipt unavailable')

    def inspect(self):
        with self.connect() as db:
            rows=db.execute('SELECT id,kind,input_sha,state,receipt FROM attempt ORDER BY rowid').fetchall()
        return [dict(attempt_id=a,kind=k,input_sha=s,state=t,receipt=None if r is None else json.loads(r)) for a,k,s,t,r in rows]
