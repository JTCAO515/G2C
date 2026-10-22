"""First manual save without source seed; new private PostgreSQL only."""
import json
import os
from pathlib import Path
import sys
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import psycopg
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'auth'),str(ROOT/'tests')]
from cj_auth.interfaces import TrustedPrincipal
from cj_memory.domain import Service,Conflict,InvalidInput,Unavailable
from cj_memory.manual import ManualPolicy,parse_manual
from cj_memory.operation import OperationWithheld
from cj_memory.postgres import Repository
from pg_checks import command
for key in tuple(os.environ):
    if key.startswith('PG'):del os.environ[key]
passfile=ROOT/'.local/manual/empty.pgpass';passfile.touch(mode=0o600,exist_ok=False)
def connect():return psycopg.connect(host='/tmp/cj011-manual-01a16218',port=56114,user='cj011_manual',dbname='postgres',passfile=str(passfile),connect_timeout=3)
with connect() as conn:
    conn.execute((ROOT/'schema.sql').read_text())
    conn.execute("INSERT INTO cj_memory_scope(scope) VALUES ('A'),('B')")
P=TrustedPrincipal('test','A','test',1,1,9999999999)
def allowed(_):return P,'A'
def raw(n,**changes):
    obj=json.loads(command(n));obj.pop('source_id');obj.pop('source_version');obj.update(changes)
    return json.dumps(obj,ensure_ascii=False).encode()
def policy():
    # Explicit SYNTHETIC test policy, not approval of any product content/retention.
    return ManualPolicy(subjects=frozenset({'self'}),slots=frozenset({'food'}),extents=frozenset({'long_term','current'}),context_ids=frozenset({'context-1'}),expires_at=datetime.now(timezone.utc)+timedelta(hours=1),content_allowed=lambda c,r:True,semantic_resolved=lambda c,r:True)
def encode(value):return json.dumps(asdict(value)).encode()

class Checks(unittest.TestCase):
    def setUp(self):self.policy=policy();self.s=Service(Repository(connect,'A'),manual_policy=self.policy)
    def save(self,r,service=None,guard=allowed):return (service or self.s).with_operation(guard,lambda ctx:encode(ctx.save_manual(r)))
    def counts(self,r):
        c=parse_manual(r)
        with connect() as conn:
            return tuple(conn.execute('SELECT count(*) FROM '+table+' WHERE scope=\'A\' AND '+column+'=%s',(value,)).fetchone()[0] for table,column,value in [('cj_memory_source','source_id',c.source_id),('cj_memory_item','item_id',c.item_id),('cj_memory_operation','operation_id',c.operation_id)])
    def test_01_first_save_without_source_seed(self):
        r=raw('first',slot='food');self.assertEqual(self.counts(r),(0,0,0))
        response=json.loads(self.save(r));self.assertEqual(response['status'],'active');self.assertEqual(self.counts(r),(1,1,1))
        c=parse_manual(r)
        self.assertTrue(self.s.detail(c.item_id).command.source_id.startswith('manual-v1:'))
        with connect() as conn:
            self.assertEqual(bytes(conn.execute('SELECT original_input FROM cj_memory_operation WHERE scope=\'A\' AND operation_id=%s',(c.operation_id,)).fetchone()[0]),r)
            self.assertEqual(bytes(conn.execute('SELECT approved_input FROM cj_memory_source WHERE scope=\'A\' AND source_id=%s',(c.source_id,)).fetchone()[0]),c.raw)
    def test_02_same_bytes_replay_concurrent_different_bytes_conflict(self):
        r=raw('replay',slot='food',kind='inference')
        with ThreadPoolExecutor(max_workers=6) as pool:receipts=list(pool.map(lambda _:self.save(r),range(12)))
        self.assertEqual(len(set(receipts)),1);self.assertEqual(self.counts(r),(1,1,1))
        with self.assertRaises(Conflict):self.save(r+b' ')
    def test_03_client_cannot_approve_or_reference_source(self):
        for field,value in [('source_id','other'),('source_version',1),('owner','B'),('confirmed',True),('authorized',True),('source_kind','manual')]:
            with self.assertRaises(InvalidInput):self.save(raw('bad-'+field,slot='food',**{field:value}))
    def test_04_missing_expired_sensitive_unknown_and_scope_policy(self):
        for suffix,p,changes in [('missing',None,{}),('expired',replace(self.policy,expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)),{}),('sensitive',replace(self.policy,content_allowed=lambda c,r:False),{}),('unknown',replace(self.policy,content_allowed=lambda c,r:None),{}),('companion',self.policy,{'subject':'companion'}),('slot',self.policy,{'slot':'unknown'}),('context',self.policy,{'extent':'current','context_id':'other'})]:
            r=raw('policy-'+suffix,slot='food',**{k:v for k,v in changes.items() if k!='slot'}) if 'slot' not in changes else raw('policy-'+suffix,**changes)
            with self.assertRaises(Unavailable):self.save(r,Service(Repository(connect,'A'),manual_policy=p))
            self.assertEqual(self.counts(r),(0,0,0))
    def test_05_inference_and_ambiguous_stay_candidate(self):
        for suffix,p,k in [('infer',self.policy,'inference'),('ambiguous',replace(self.policy,semantic_resolved=lambda c,r:None),'preference')]:
            r=raw(suffix,slot='food',kind=k)
            self.assertEqual(json.loads(self.save(r,Service(Repository(connect,'A'),manual_policy=p)))['status'],'candidate')
            self.assertNotIn(parse_manual(r).item_id,[i.command.item_id for i in self.s.effective('self').items])
    def test_06_precommit_rolls_back_source_item_receipt(self):
        r=raw('rollback',slot='food',kind='inference')
        def guard(stage):return None if stage=='precommit' else allowed(stage)
        with self.assertRaises(OperationWithheld) as caught:self.save(r,guard=guard)
        self.assertFalse(caught.exception.commit_possible);self.assertEqual(self.counts(r),(0,0,0))
    def test_07_item_conflict_rolls_back_new_source(self):
        r=raw('itemconflict',slot='food') # first already occupies same active slot
        with self.assertRaises(Conflict):self.save(r)
        self.assertEqual(self.counts(r),(0,0,0))
    def test_08_commit_ack_unknown_original_query(self):
        r=raw('lost',slot='food',kind='inference')
        class Lost:
            def __init__(self):self.conn=connect()
            def __getattr__(self,k):return getattr(self.conn,k)
            def commit(self):self.conn.commit();raise OSError()
        with self.assertRaises(OperationWithheld) as caught:self.save(r,Service(Repository(Lost,'A'),manual_policy=self.policy))
        self.assertEqual(caught.exception.recovery,'reconcile_original')
        self.assertEqual(caught.exception.operation_id,parse_manual(r).operation_id)
        self.assertEqual(self.counts(r),(1,1,1))
        result=self.s.with_operation(allowed,lambda ctx:encode(ctx.query(caught.exception.operation_id)))
        self.assertEqual(json.loads(result)['item_id'],parse_manual(r).item_id)
    def test_09_scope_isolation_and_no_source_reactivation(self):
        r=raw('revoked',slot='food',kind='inference');self.save(r);c=parse_manual(r)
        b=Service(Repository(connect,'B'),manual_policy=self.policy)
        self.assertIsNone(b.query(c.operation_id));self.assertIsNone(b.detail(c.item_id))
        with connect() as conn:conn.execute("UPDATE cj_memory_source SET active=false,version=2 WHERE scope='A' AND source_id=%s",(c.source_id,))
        self.assertEqual(json.loads(self.save(r))['item_id'],c.item_id)
        with connect() as conn:self.assertEqual(conn.execute("SELECT active,version FROM cj_memory_source WHERE scope='A' AND source_id=%s",(c.source_id,)).fetchone(),(False,2))
    def test_10_policy_replacement_precommit_rejected(self):
        r=raw('policyreplace',slot='food',kind='inference')
        def guard(stage):
            if stage=='precommit':self.s.manual_policy=policy()
            return allowed(stage)
        with self.assertRaises(OperationWithheld):self.save(r,guard=guard)
        self.assertEqual(self.counts(r),(0,0,0))
    def test_11_reference_path_compatible(self):
        r=command('reference',kind='inference');c=json.loads(r)
        with connect() as conn:conn.execute("INSERT INTO cj_memory_source VALUES ('A',%s,1,%s,true,false,false,true,clock_timestamp()+interval '1 hour')",(c['source_id'],r))
        result=self.s.with_operation(allowed,lambda ctx:encode(ctx.save(r)))
        self.assertEqual(json.loads(result)['status'],'candidate')
    def test_12_current_scope(self):
        r=raw('current',slot='food',extent='current',context_id='context-1')
        self.assertEqual(json.loads(self.save(r))['status'],'active')
        self.assertEqual(self.s.effective('self','context-1').items[0].command.item_id,parse_manual(r).item_id)
        self.assertNotIn(parse_manual(r).item_id,[i.command.item_id for i in self.s.effective('self','other').items])

if __name__=='__main__':unittest.main(verbosity=2)
