"""Review's exact cancellation faults plus original-ledger receipt hash checks."""
import asyncio
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
import psycopg
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'auth'),str(ROOT/'tests')]
from cj_auth.interfaces import TrustedPrincipal
from cj_memory.domain import Service,Conflict
from cj_memory.manual import ManualPolicy,parse_manual
from cj_memory.operation import OperationWithheld
from cj_memory.postgres import Repository
from pg_checks import command
for key in tuple(os.environ):
    if key.startswith('PG'):del os.environ[key]
passfile=ROOT/'.local/cancel/empty.pgpass';passfile.touch(mode=0o600,exist_ok=False)
def connect():return psycopg.connect(host='/tmp/cj011-cancel-01a16218',port=56115,user='cj011_cancel',dbname='postgres',passfile=str(passfile),connect_timeout=3)
with connect() as conn:
    conn.execute((ROOT/'schema.sql').read_text())
    conn.execute("INSERT INTO cj_memory_scope(scope) VALUES ('A'),('B')")
P=TrustedPrincipal('synthetic','A','test',1,1,9999999999)
def guard(_):return P,'A'
def policy():return ManualPolicy(frozenset({'self'}),frozenset({'test'}),frozenset({'long_term'}),frozenset(),datetime.now(timezone.utc)+timedelta(hours=1),lambda c,r:True,lambda c,r:True)
def service(factory=connect):return Service(Repository(factory,'A'),manual_policy=policy())
def encode(r):return json.dumps(asdict(r)).encode()
def prepare(n,manual=False):
    r=command(n,kind='inference',slot='test')
    if manual:
        obj=json.loads(r);obj.pop('source_id');obj.pop('source_version')
        return json.dumps(obj,ensure_ascii=False,indent=2).encode()+b'\n'
    with connect() as conn:conn.execute("INSERT INTO cj_memory_source VALUES ('A',%s,1,%s,true,false,true,true,clock_timestamp()+interval '1 hour')",(json.loads(r)['source_id'],r))
    return r

def save(ctx,r,manual):return ctx.save_manual(r) if manual else ctx.save(r)

class Checks(unittest.TestCase):
    def test_01_exact_review_commit_cancellation(self):
        for manual in (False,True):
            for interruption in (asyncio.CancelledError,KeyboardInterrupt):
                r=prepare('commit-'+str(manual)+interruption.__name__,manual)
                class CancelAfterCommit:
                    def __init__(self):self.conn=connect()
                    def __getattr__(self,key):return getattr(self.conn,key)
                    def commit(self):self.conn.commit();raise interruption('synthetic after commit')
                with self.assertRaises(OperationWithheld) as caught:service(CancelAfterCommit).with_operation(guard,lambda ctx:encode(save(ctx,r,manual)))
                e=caught.exception
                self.assertTrue(e.commit_possible);self.assertEqual(e.recovery,'reconcile_original');self.assertEqual(e.operation_id,json.loads(r)['operation_id'])
                receipt=service().query(e.operation_id)
                self.assertIsNotNone(receipt);self.assertEqual(receipt.input_sha256,hashlib.sha256(r).hexdigest())
    def test_02_exact_review_swallowed_guard_cancellation(self):
        for manual in (False,True):
            for catch_all in (False,True):
                r=prepare('precommit-'+str(manual)+str(catch_all),manual)
                def cancelling(stage):
                    if stage=='precommit':raise asyncio.CancelledError('synthetic cancelled policy check')
                    return guard(stage)
                def swallow(ctx):
                    try:save(ctx,r,manual)
                    except BaseException as exc:
                        # Exact Review catches CancelledError. Also test stronger
                        # catch-all callback cannot suppress sticky Withheld.
                        if not catch_all and not isinstance(exc,asyncio.CancelledError):raise
                    return b'{}'
                with self.assertRaises(OperationWithheld) as caught:service().with_operation(cancelling,swallow)
                self.assertFalse(caught.exception.commit_possible)
                self.assertIsNone(service().query(json.loads(r)['operation_id']))
                if manual:
                    with connect() as conn:self.assertEqual(conn.execute("SELECT count(*) FROM cj_memory_source WHERE source_id=%s",(parse_manual(r).source_id,)).fetchone()[0],0)
    def test_03_projection_interruption_after_commit(self):
        r=prepare('projection',True)
        def project(ctx):ctx.save_manual(r);raise asyncio.CancelledError()
        with self.assertRaises(OperationWithheld) as caught:service().with_operation(guard,project)
        self.assertTrue(caught.exception.commit_possible)
        self.assertEqual(caught.exception.operation_id,json.loads(r)['operation_id'])
        self.assertIsNotNone(service().query(caught.exception.operation_id))
    def test_04_cancellation_before_commit_attempt(self):
        r=prepare('policycancel',True)
        def cancel_content(c,r):raise asyncio.CancelledError()
        p=policy()
        from dataclasses import replace
        s=Service(Repository(connect,'A'),manual_policy=replace(p,content_allowed=cancel_content))
        def swallow(ctx):
            try:ctx.save_manual(r)
            except BaseException:pass
            return b'{}'
        with self.assertRaises(OperationWithheld) as caught:s.with_operation(guard,swallow)
        self.assertFalse(caught.exception.commit_possible)
        self.assertIsNone(service().query(json.loads(r)['operation_id']))
    def test_05_independent_query_hash_manual_reference(self):
        for manual in (False,True):
            r=prepare('hash-'+str(manual),manual)
            saved=json.loads(service().with_operation(guard,lambda ctx:encode(save(ctx,r,manual))))
            oid=json.loads(r)['operation_id']
            # New service/query has only original op ID, not request body.
            queried=json.loads(service().with_operation(guard,lambda ctx:encode(ctx.query(oid))))
            self.assertEqual(saved,queried);self.assertEqual(saved['input_sha256'],hashlib.sha256(r).hexdigest())
            self.assertEqual(len(saved['input_sha256']),64)
            self.assertEqual(set(saved),{'operation_id','item_id','version','status','input_sha256'})
            if manual:self.assertNotEqual(saved['input_sha256'],hashlib.sha256(parse_manual(r).raw).hexdigest())
            with self.assertRaises(Conflict):service().with_operation(guard,lambda ctx:encode(save(ctx,r+b' ',manual)))
            self.assertEqual(service().query(oid).input_sha256,saved['input_sha256'])
            self.assertIsNone(Service(Repository(connect,'B')).query(oid))
    def test_06_postcommit_guard_cancel_stays_reconcile(self):
        r=prepare('postreturn',True)
        def cancelled(stage):
            if stage=='private_return':raise asyncio.CancelledError()
            return guard(stage)
        with self.assertRaises(OperationWithheld) as caught:service().with_operation(cancelled,lambda ctx:encode(ctx.save_manual(r)))
        self.assertTrue(caught.exception.commit_possible)
        self.assertIsNotNone(service().query(caught.exception.operation_id))

if __name__=='__main__':unittest.main(verbosity=2)
