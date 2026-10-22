"""Exact opaque ID keyset validation in a separate fresh UTF8 PG cluster."""
import os
import sys
from pathlib import Path
import json
import psycopg
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'auth'),str(ROOT/'tests')]
from cj_memory.domain import Service,InvalidInput
from cj_memory.postgres import Repository
from cj_auth.interfaces import TrustedPrincipal
from pg_checks import command
for key in tuple(os.environ):
    if key.startswith('PG'):del os.environ[key]
passfile=ROOT/'.local/list/empty.pgpass';passfile.touch(mode=0o600,exist_ok=False)
def connect():return psycopg.connect(host='/tmp/cj011-list-01a16218',port=56113,user='cj011_list',dbname='postgres',passfile=str(passfile),connect_timeout=3)
with connect() as conn:
    conn.execute((ROOT/'schema.sql').read_text())
    conn.execute("INSERT INTO cj_memory_scope(scope) VALUES ('A')")
ids=['a','A','é','e\u0301','中','😀',' a','a ','ß','ss','İ','i']
s=Service(Repository(connect,'A'))
p=TrustedPrincipal('test','A','test',1,1,9999999999)
for n,iid in enumerate(ids):
    raw=command(str(n),item_id=iid)
    with connect() as conn:conn.execute("INSERT INTO cj_memory_source VALUES ('A',%s,1,%s,true,true,true,true,clock_timestamp()+interval '1 hour')",(json.loads(raw)['source_id'],raw))
    s.with_operation(lambda _:(p,'A'),lambda ctx:(ctx.save(raw),b'{}')[1])
after=None;seen=[];page_lengths=[]
while True:
    def project(ctx):
        items=ctx.list_items(after=after,limit=5)
        return json.dumps({'items':[i.command.item_id for i in items],'next_after':items[-1].command.item_id if items else None},ensure_ascii=False).encode()
    page=json.loads(s.with_operation(lambda _:(p,'A'),project));page_lengths.append(len(page['items']))
    if not page['items']:
        assert page['next_after'] is None;break
    seen+=page['items'];after=page['next_after']
assert seen==sorted(ids,key=lambda s:s.encode('utf-8'))
assert len(set(seen))==len(ids)
assert page_lengths==[5,5,2,0]
for limit in (0,101,True):
    try:s.list_items(limit=limit)
    except InvalidInput:pass
    else:raise AssertionError('bad limit accepted')
assert len(s.list_items(limit=1))==1
assert len(s.list_items(limit=100))==12
print('PASS 12 opaque IDs: ASCII case, whitespace, CJK, emoji, NFC/NFD distinct; C byte order; pages 5/5/2/0; limits 1..100')
