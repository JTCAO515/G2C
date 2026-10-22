"""Dedicated new private PG; synthetic guard decisions, not live AUTH acceptance."""
import json
import os
from pathlib import Path
import sys
import unittest
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor
import psycopg
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT.parent/'auth'),str(ROOT/'tests')]
from cj_auth.interfaces import TrustedPrincipal
from cj_memory.domain import Service, CommitUnknown
from cj_memory.operation import OperationWithheld
from cj_memory.postgres import Repository
from pg_checks import command
for key in tuple(os.environ):
    if key.startswith('PG'): del os.environ[key]
PASSFILE = ROOT/'.local/guard/empty.pgpass'
PASSFILE.touch(mode=0o600,exist_ok=False)
KW = dict(host='/tmp/cj011-guard-01a16218',port=56112,user='cj011_guard',dbname='postgres',passfile=str(PASSFILE),connect_timeout=3)
def connect():return psycopg.connect(**KW)
with connect() as conn:
    conn.execute((ROOT/'schema.sql').read_text())
    conn.execute("INSERT INTO cj_memory_scope(scope) VALUES ('A'),('B')")
P = TrustedPrincipal('synthetic-issuer','A','test-audience',1,1,9999999999)
Q = TrustedPrincipal('synthetic-issuer','B','test-audience',1,1,9999999999)
def grant(raw):
    c=json.loads(raw)
    with connect() as conn:
        conn.execute("INSERT INTO cj_memory_source VALUES ('A',%s,1,%s,true,true,true,true,clock_timestamp()+interval '1 hour')",(c['source_id'],raw))
def encode(receipt):return json.dumps(asdict(receipt)).encode()
def allowed(stage):return P,'A'

class Checks(unittest.TestCase):
    def setUp(self):self.service=Service(Repository(connect,'A'))
    def raw(self,suffix=''):
        raw=command(self._testMethodName+suffix);grant(raw);return raw
    def assert_absent(self,raw):
        c=json.loads(raw)
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_operation WHERE operation_id=%s',(c['operation_id'],)).fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_item WHERE item_id=%s',(c['item_id'],)).fetchone()[0],0)
    def test_01_success_order(self):
        raw=self.raw();stages=[]
        def guard(stage):stages.append(stage);return allowed(stage)
        value=self.service.with_operation(guard,lambda ctx:encode(ctx.save(raw)))
        self.assertEqual(json.loads(value)['status'],'active')
        self.assertEqual(stages,['entry','transaction','transaction_ready','precommit','private_return','return'])
    def test_02_precommit_denied_unknown_identity_scope_rollback(self):
        for mode in ('denied','unknown','principal','scope'):
            raw=self.raw(mode)
            def guard(stage):
                if stage=='precommit':
                    if mode=='denied':raise PermissionError()
                    if mode=='unknown':return None
                    return (Q,'A') if mode=='principal' else (P,'B')
                return allowed(stage)
            with self.assertRaises(OperationWithheld) as caught:
                self.service.with_operation(guard,lambda ctx:encode(ctx.save(raw)))
            self.assertFalse(caught.exception.commit_possible)
            self.assertEqual(caught.exception.stage,'precommit')
            self.assert_absent(raw)
    def test_03_after_commit_withhold_original(self):
        raw=self.raw()
        def guard(stage):
            if stage=='private_return':return None
            return allowed(stage)
        with self.assertRaises(OperationWithheld) as caught:self.service.with_operation(guard,lambda ctx:encode(ctx.save(raw)))
        self.assertTrue(caught.exception.commit_possible)
        self.assertEqual(caught.exception.recovery,'reconcile_original')
        self.assertEqual(self.service.query(caught.exception.operation_id).item_id,json.loads(raw)['item_id'])
    def test_04_projection_then_final_guard(self):
        raw=self.raw();self.service.save(raw);calls=[]
        def guard(stage):
            calls.append(stage)
            return None if stage=='return' else allowed(stage)
        def projection(ctx):
            result=encode(ctx.query(json.loads(raw)['operation_id']))
            calls.append('encoded')
            return result
        with self.assertRaises(OperationWithheld) as caught:self.service.with_operation(guard,projection)
        self.assertEqual(calls[-2:],['encoded','return'])
        self.assertFalse(caught.exception.commit_possible)
    def test_05_escaped_context_and_deferred_result(self):
        escaped=[]
        self.assertEqual(self.service.with_operation(allowed,lambda ctx:(escaped.append(ctx),b'{}')[1]),b'{}')
        with self.assertRaises(RuntimeError):escaped[0].groups()
        for factory in (lambda ctx:ctx,lambda ctx:iter([1]),lambda ctx:ctx.groups):
            with self.assertRaises(TypeError):self.service.with_operation(allowed,factory)
    def test_06_cross_thread_rejected(self):
        def callback(ctx):
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaises(RuntimeError):pool.submit(ctx.groups).result()
            return b'{}'
        self.service.with_operation(allowed,callback)
    def test_07_all_read_methods_guarded(self):
        raw=self.raw();self.service.save(raw);c=json.loads(raw)
        calls=[lambda ctx:ctx.query(c['operation_id']),lambda ctx:ctx.detail(c['item_id']),lambda ctx:ctx.groups(),lambda ctx:ctx.list_items(),lambda ctx:ctx.effective('self')]
        for call in calls:
            stages=[]
            def guard(stage):stages.append(stage);return allowed(stage)
            self.service.with_operation(guard,lambda ctx:(call(ctx),b'{}')[1])
            self.assertIn('precommit',stages);self.assertEqual(stages[-1],'return')
    def test_08_lost_ack(self):
        raw=self.raw()
        class Lost:
            def __init__(self):self.conn=connect()
            def __getattr__(self,k):return getattr(self.conn,k)
            def commit(self):self.conn.commit();raise OSError()
        with self.assertRaises(OperationWithheld) as caught:Service(Repository(Lost,'A')).with_operation(allowed,lambda ctx:encode(ctx.save(raw)))
        self.assertEqual(caught.exception.recovery,'reconcile_original')
        self.assertIsNotNone(self.service.query(caught.exception.operation_id))
    def test_09_projection_error_after_commit(self):
        raw=self.raw()
        def callback(ctx):ctx.save(raw);raise ValueError('projection failed')
        with self.assertRaises(OperationWithheld) as caught:self.service.with_operation(allowed,callback)
        self.assertEqual(caught.exception.recovery,'reconcile_original')
    def test_10_swallowed_denial_stays_withheld(self):
        raw=self.raw()
        def guard(stage):return None if stage=='precommit' else allowed(stage)
        def callback(ctx):
            try:ctx.save(raw)
            except OperationWithheld:pass
            return b'{}'
        with self.assertRaises(OperationWithheld):self.service.with_operation(guard,callback)
        self.assert_absent(raw)
    def test_11_entry_denial_never_opens_repository(self):
        def no_connect():raise AssertionError('must not connect')
        with self.assertRaises(OperationWithheld):Service(Repository(no_connect,'A')).with_operation(lambda _:None,lambda ctx:ctx.groups())
    def test_12_repo_scope_mutation_rejected(self):
        raw=self.raw()
        def guard(stage):
            if stage=='precommit':self.service.repository.scope='B'
            return allowed(stage)
        with self.assertRaises(OperationWithheld):self.service.with_operation(guard,lambda ctx:encode(ctx.save(raw)))
        self.assert_absent(raw)

if __name__=='__main__':unittest.main(verbosity=2)
