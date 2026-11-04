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
from zoneinfo import ZoneInfo

from .metered_exit import BudgetUnknown

LIMITS={'model':(227,1),'place':(600,1),'route':(300,1),'weather':(100,1),'fact':(120,0)}
DEADLINE=datetime(2026,12,1,tzinfo=ZoneInfo('Asia/Shanghai'))
MAC_PRODUCER='codex-mac'
HK_PRODUCER='hk-beta-47.83.147.176'


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')


class AuthorizationBudget:
    def __init__(self,root,*,clock=lambda:datetime.now(ZoneInfo('Asia/Shanghai'))):
        self.root=Path(root);self.clock=clock
        self.producer=os.environ.get('CJ_M4_BUDGET_PRODUCER',MAC_PRODUCER)
        if self.producer not in (MAC_PRODUCER,HK_PRODUCER):raise BudgetUnknown('explicit M4 producer required')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=self.root/'m4-outflows.sqlite'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS attempt(id TEXT PRIMARY KEY,kind TEXT NOT NULL,input_sha TEXT NOT NULL,state TEXT NOT NULL,receipt TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS producer(singleton INTEGER PRIMARY KEY CHECK(singleton=1),identity TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO producer VALUES(1,?)',(MAC_PRODUCER,))
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        connection=sqlite3.connect(self.path,timeout=10)
        connection.execute('PRAGMA synchronous=FULL')
        try:
            with connection:yield connection
        finally:connection.close()

    def check_date(self):
        now=self.clock()
        if now.tzinfo is None or now>=DEADLINE:raise BudgetUnknown('M4 authorization expired')

    def require_producer(self,db):
        if db.execute('SELECT identity FROM producer WHERE singleton=1').fetchone()!=(self.producer,):
            raise BudgetUnknown('M4 journal moved; original producer is read only')

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
