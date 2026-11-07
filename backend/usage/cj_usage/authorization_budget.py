"""M4 authorization ceiling, in addition to (never instead of) the RUN Meter.

One durable intent per original Meter attempt; no retry or financial settlement.
Complete, priceable receipts use public list prices. Unresolved attempts retain
their original hold, and a new attempt must fit its full hold before dispatch.
The operator keeps this journal across releases/restores, outside database dumps.
"""
from contextlib import contextmanager,nullcontext
from datetime import datetime
import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid
from zoneinfo import ZoneInfo

from .metered_exit import BudgetUnknown

# JT 2026-11-07, #495/6708986558. Keep the previous count limits and unit holds.
MODEL_STOP_CNY=10000
MODEL_TOTAL_CNY=10000
MODEL_M1_HOLD_CNY=13
LIMITS={'model':(min(MODEL_STOP_CNY,MODEL_TOTAL_CNY)-MODEL_M1_HOLD_CNY,1),
        'place':(1200,1),'route':(600,1),'weather':(200,1),'fact':(240,0)}
TOOL_STOP_CNY=10000
TOOL_TOTAL_CNY=500
# Fixed point in 10^-7 CNY. Gross public prices exclude free quota, discounts
# and cache deductions. These estimates do not settle the supplier invoice.
CNY_SCALE=10_000_000
MODEL_INPUT_PRICE=8
MODEL_OUTPUT_PRICE=27
AMAP_PRICE=30_000
AMAP_ENDPOINTS={
    'place': frozenset(('https://restapi.amap.com/v3/place/text','https://restapi.amap.com/v3/place/detail')),
    'route': frozenset(('https://restapi.amap.com/v3/direction/walking','https://restapi.amap.com/v3/direction/driving')),
    'weather': frozenset(('https://restapi.amap.com/v3/weather/weatherInfo',)),
}
# #2 / PR507 is outside this SQLite ledger: 8 complete Beijing receipts and
# five unresolved original holds. Keep the older 13-hold count cap above.
M1_ESTIMATED=1294*MODEL_INPUT_PRICE+129*MODEL_OUTPUT_PRICE
M1_UNRESOLVED_CNY=MODEL_M1_HOLD_CNY-8
DEADLINE=datetime(2026,12,1,tzinfo=ZoneInfo('Asia/Shanghai'))
MAC_PRODUCER='codex-mac'
HK_PRODUCER='hk-beta-47.83.147.176'
HK_JOURNAL_ROOT=Path('/home/cj/.local/share/g2c/m4-real-services')
HK_ANCHOR=Path('/control/budget/adoption.json')


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')


def journal_state(db):
    rows=db.execute('SELECT id,kind,input_sha,state,receipt FROM attempt ORDER BY id').fetchall()
    return len(rows),hashlib.sha256(canonical(rows)).hexdigest()


def _price_receipt(kind, raw):
    if raw is None:
        return None
    try:
        receipt=json.loads(raw)
    except (ValueError,TypeError):
        return None
    if type(receipt) is not dict:
        return None
    digest=receipt.get('receipt_sha256' if kind=='model' else 'response_sha256')
    if type(digest) is not str or re.fullmatch('[0-9a-f]{64}',digest) is None:
        return None
    if kind=='model':
        if (receipt.get('model_id')!='qwen3.8-flash' or receipt.get('region')!='cn-beijing'
                or receipt.get('endpoint')!='https://dashscope.aliyuncs.com/compatible-mode/v1'):
            return None
        usage=receipt.get('usage')
        if type(usage) is not dict:
            return None
        prompt,completion,total=(usage.get(key) for key in ('prompt_tokens','completion_tokens','total_tokens'))
        if (any(type(value) is not int or not 0<=value<=1_000_000 for value in (prompt,completion,total))
                or not 0<total==prompt+completion):
            return None
        return prompt*MODEL_INPUT_PRICE+completion*MODEL_OUTPUT_PRICE
    endpoint=receipt.get('endpoint')
    if kind in AMAP_ENDPOINTS and type(endpoint) is str and endpoint in AMAP_ENDPOINTS[kind]:
        return AMAP_PRICE
    return None


def authorization_usage(db):
    """Read-only totals over original rows, in fixed-point CNY for each category."""
    counts=dict.fromkeys(LIMITS,0)
    estimates=dict.fromkeys(LIMITS,0)
    holds=dict.fromkeys(LIMITS,0)
    for kind,state,receipt in db.execute('SELECT kind,state,receipt FROM attempt'):
        counts[kind]+=1
        estimate=_price_receipt(kind,receipt) if state=='RECEIVED' else None
        if estimate is None:
            holds[kind]+=LIMITS[kind][1]*CNY_SCALE
        else:
            estimates[kind]+=estimate
    estimates['model']+=M1_ESTIMATED
    holds['model']+=M1_UNRESOLVED_CNY*CNY_SCALE
    return counts,estimates,holds


def save_anchor(value):
    temporary=HK_ANCHOR.with_suffix('.tmp')
    with temporary.open('x') as output:
        os.chmod(temporary,0o600);json.dump(value,output);output.flush();os.fsync(output.fileno())
    temporary.replace(HK_ANCHOR)
    descriptor=os.open(HK_ANCHOR.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


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
                    or journal_state(db)!=(anchor['attempt_count'],anchor['attempts_sha256'])):
                raise BudgetUnknown('M4 non-restored adoption control differs')
            return anchor

    @contextmanager
    def mutation(self):
        # Commit a non-restored write intent before SQLite can commit. A crash
        # between stores is HOLD, never permission to replay an original send.
        lock=(HK_ANCHOR.parent/'adoption.lock').open('a') if self.producer==HK_PRODUCER else nullcontext()
        with lock as handle:
            if self.producer==HK_PRODUCER:fcntl.flock(handle,fcntl.LOCK_EX)
            intent=None
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                anchor=self.require_producer(db)
                yield db
                if self.producer==HK_PRODUCER:
                    count,digest=journal_state(db)
                    intent=dict(anchor,state='WRITE_INTENT',attempt_count=count,attempts_sha256=digest)
                    save_anchor(intent)
            if intent is not None:save_anchor(dict(intent,state='ADOPTED'))

    def begin(self,attempt,kind,raw):
        self.check_date()
        if kind not in LIMITS or type(attempt) is not str or not 1<=len(attempt)<=128:
            raise BudgetUnknown('M4 original attempt unavailable')
        with self.mutation() as db:
            if db.execute('SELECT 1 FROM attempt WHERE id=?',(attempt,)).fetchone():
                raise BudgetUnknown('M4 original attempt is read only')
            counts,estimates,holds=authorization_usage(db)
            if counts[kind]>=LIMITS[kind][0]:raise BudgetUnknown('M4 call allowance exhausted')
            reserve=LIMITS[kind][1]*CNY_SCALE
            if kind=='model':
                if estimates[kind]+holds[kind]+reserve>min(MODEL_STOP_CNY,MODEL_TOTAL_CNY)*CNY_SCALE:
                    raise BudgetUnknown('M4 model authorization ceiling')
            elif sum(estimates[k]+holds[k] for k in LIMITS if k!='model')+reserve>min(TOOL_STOP_CNY,TOOL_TOTAL_CNY)*CNY_SCALE:
                raise BudgetUnknown('M4 tool authorization ceiling')
            db.execute('INSERT INTO attempt VALUES(?,?,?,\'INTENT\',NULL)',
                       (attempt,kind,hashlib.sha256(raw).hexdigest()))

    def finish(self,attempt,receipt):
        # The producer supplies bounded metadata only; keys/body/text never enter.
        with self.mutation() as db:
            if 'receipt_sha256' in receipt and db.execute("SELECT 1 FROM attempt WHERE id<>? AND kind='model' AND json_extract(receipt,'$.receipt_sha256')=?",(attempt,receipt['receipt_sha256'])).fetchone():
                raise BudgetUnknown('M4 supplier receipt identity reused; original outcome unknown')
            if db.execute('UPDATE attempt SET state=\'RECEIVED\',receipt=? WHERE id=? AND state=\'INTENT\'',
                          (canonical(receipt).decode(),attempt)).rowcount!=1:
                raise BudgetUnknown('M4 original receipt unavailable')

    def inspect(self):
        with self.connect() as db:
            rows=db.execute('SELECT id,kind,input_sha,state,receipt FROM attempt ORDER BY rowid').fetchall()
        return [dict(attempt_id=a,kind=k,input_sha=s,state=t,receipt=None if r is None else json.loads(r)) for a,k,s,t,r in rows]
