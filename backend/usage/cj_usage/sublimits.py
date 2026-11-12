"""Append-only line attribution in the original authorization SQLite journal.

No second balance/fee store. Usage is derived from original attempts/receipts;
unpriced/unknown attempts keep the same full hold as the parent ceiling.
"""
import hashlib
import json
import re
import uuid

from cj_strict_json import compact
from .metered_exit import BudgetUnknown

ADOPTED='ADOPTED_SUBLIMITS_1'  # Older financial binaries reject this control state.
TABLES=('sublimit','scope_sublimit','attempt_sublimit')


def scope_hash(scope):return hashlib.sha256(scope.encode()).hexdigest()[:32]


def operation_id(scope):return 'g2c1-'+scope_hash(scope)+'-'+uuid.uuid4().hex


def snapshot(db):
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    present=set(TABLES)&tables
    if not present:return None
    if present!=set(TABLES):raise BudgetUnknown('incomplete original sublimit schema')
    rows=[db.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall() for table in TABLES]
    return hashlib.sha256(compact(rows,sort_keys=True)).hexdigest()


def policy(value):
    keys={'cap','active_cap','model_cap','tool_cap','max_calls','model_calls','tool_calls'}
    if (type(value) is not dict or set(value)!=keys or
            any(v is not None and (type(v) is not int or not 0<v<=10500*10_000_000) for v in value.values()) or
            value['max_calls'] is not None and value['max_calls']>12227 or
            value['cap'] is not None and (value['active_cap'] is None or value['active_cap']>value['cap'])):
        raise BudgetUnknown('explicit bounded sublimit policy required')
    return compact(value,sort_keys=True).decode()


def activate(budget,grants,bindings):
    """B operator only; once on an existing journal, never reset/recreate history."""
    if (type(grants) is not dict or set(grants)!={'A','B','L','C','E','F'} or type(bindings) is not dict or not bindings
            or any(re.fullmatch('[a-f0-9]{32}',key) is None or line not in grants for key,line in bindings.items())):
        raise BudgetUnknown('explicit original scope allocations required')
    encoded={line:policy(value) for line,value in grants.items()}
    if (any(any(v is not None for v in grants[x].values()) for x in ('A','B'))
            or any(grants[x]['cap'] is None for x in ('L','C','E','F'))):
        raise BudgetUnknown('only original A/B use unchanged parent ceilings')
    budget.check_date()
    with budget.mutation() as db:
        if snapshot(db) is not None or not db.execute('SELECT 1 FROM attempt LIMIT 1').fetchone():
            raise BudgetUnknown('existing journal and first allocation required')
        db.execute('CREATE TABLE sublimit(line TEXT PRIMARY KEY,policy TEXT NOT NULL)')
        db.execute('CREATE TABLE scope_sublimit(scope_hash TEXT PRIMARY KEY,line TEXT NOT NULL REFERENCES sublimit(line))')
        db.execute('CREATE TABLE attempt_sublimit(attempt_id TEXT PRIMARY KEY REFERENCES attempt(id),line TEXT NOT NULL REFERENCES sublimit(line))')
        db.executemany('INSERT INTO sublimit VALUES(?,?)',sorted(encoded.items()))
        db.executemany('INSERT INTO scope_sublimit VALUES(?,?)',sorted(bindings.items()))


def usage(db,line):
    from .authorization_budget import _price_receipt,LIMITS,CNY_SCALE
    count=model_calls=tool_calls=0;model=tools=0
    for kind,state,receipt in db.execute('SELECT a.kind,a.state,a.receipt FROM attempt a JOIN attempt_sublimit s ON s.attempt_id=a.id WHERE s.line=?',(line,)):
        count+=1
        cost=_price_receipt(kind,receipt) if state=='RECEIVED' else None
        if cost is None:cost=LIMITS[kind][1]*CNY_SCALE
        if kind=='model':model+=cost;model_calls+=1
        else:tools+=cost;tool_calls+=1
    return dict(calls=count,model_calls=model_calls,tool_calls=tool_calls,model=model,tools=tools,total=model+tools)


def admit(db,attempt,kind):
    """Called inside the parent's BEGIN IMMEDIATE, before its original INSERT."""
    from .authorization_budget import LIMITS,CNY_SCALE
    match=re.fullmatch(r'g2c1-([a-f0-9]{32})-[a-f0-9]{32}',attempt)
    if match is None:raise BudgetUnknown('original registered scope id required for sublimit')
    row=db.execute('SELECT line FROM scope_sublimit WHERE scope_hash=?',(match[1],)).fetchone()
    if row is None:raise BudgetUnknown('original scope has no line allocation')
    line=row[0];limits=json.loads(db.execute('SELECT policy FROM sublimit WHERE line=?',(line,)).fetchone()[0])
    policy(limits)
    used=usage(db,line);reserve=LIMITS[kind][1]*CNY_SCALE
    if limits['max_calls'] is not None and used['calls']>=limits['max_calls']:
        raise BudgetUnknown('line provider call allowance exhausted')
    if limits['active_cap'] is not None and used['total']+reserve>limits['active_cap']:
        raise BudgetUnknown('line authorization ceiling')
    category='model' if kind=='model' else 'tool'
    if limits[category+'_calls'] is not None and used[category+'_calls']>=limits[category+'_calls']:
        raise BudgetUnknown('line category call allowance exhausted')
    if limits[category+'_cap'] is not None and used['model' if kind=='model' else 'tools']+reserve>limits[category+'_cap']:
        raise BudgetUnknown('line category authorization ceiling')
    return line


def read(budget):
    with budget.connect() as db:
        db.execute('BEGIN')
        budget.require_producer(db)
        if snapshot(db) is None:return None
        return {line:dict(policy=json.loads(raw),usage=usage(db,line)) for line,raw in db.execute('SELECT line,policy FROM sublimit ORDER BY line')}
