"""Fresh task-private binding cluster ONLY; no existing database reuse."""
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import sys
import unittest
import psycopg
# Loads exact pinned USAGE from explicit --usage-repo, never mutable working tree.
from usage_composition_checks import UsageFixture, Config, Meter, Command, SyntheticFirstStep, ReconcileOriginal, rest, args
import pg_checks
from cj_run.core import Binding, Event, Service, Conflict, ResyncRequired
from cj_run.postgres import Repository, CommitUnknown
import hashlib

pg_checks.SOCKET=pg_checks.ROOT/'.local/binding/socket'
connect=pg_checks.connect
repository=pg_checks.repository


class BindingPgTests(unittest.TestCase):
    def setUp(self):
        self.scope=self.id()+(':targeted' if args.case else '')
        with connect() as c:
            c.execute('INSERT INTO cj_run_scope VALUES (%s,%s,true)',(self.scope,'epoch1'))
        self.b=Binding(self.scope,'chat','g','m','r',1)
        self.run=Service(repository(self.scope),lambda _:True)
        self.usage=UsageFixture()
        self.meter=Meter(self.usage,Config('synthetic-unit',100,0,1000,10,10,100,100),lambda:10)
        self.raw=b'{ "fixture_outbound" : true }\n'
        self.command=Command('a','original-operation','r','model',hashlib.sha256(self.raw).hexdigest(),20,10)
        self.calls=[]
    def adapter(self,command=None,run=None,raw=None):
        return SyntheticFirstStep(run or self.run,self.meter,original_binding=self.b,original_command=command or self.command,
                                  original_input_bytes=self.raw if raw is None else raw,
                                  synthetic_executor=lambda c:self.calls.append(c))
    def test_original_row_bytes_and_rebuild_conflicts(self):
        a=self.adapter()
        a.create_fixture()
        stored=repository(self.scope).recover(self.b).state
        self.assertEqual(stored.usage.input_bytes,self.raw)
        self.assertEqual(stored.usage.command_bytes,a.association.command_bytes)
        for field,value in [('attempt_id','new'),('operation_id','different'),('kind','tool'),('reserve',21),('output_limit',11)]:
            with self.subTest(field=field):
                rebuilt=self.adapter(replace(self.command,**{field:value}))
                with self.assertRaises(Conflict): rebuilt.create_fixture()
                with self.assertRaises(Conflict): rebuilt.execute_fixture(self.b,rebuilt.original_command,Event(self.b,1,'start','started'))
        with self.assertRaises(Conflict): self.adapter(replace(self.command,run_id='other'))
        with self.assertRaises(ValueError): self.adapter(raw=self.raw+b' ')
        newraw=self.raw+b' '
        rebuilt=self.adapter(replace(self.command,input_digest=hashlib.sha256(newraw).hexdigest()),raw=newraw)
        with self.assertRaises(Conflict): rebuilt.create_fixture()
        self.assertEqual(self.calls,[])
        self.assertEqual(self.usage.ledger.attempts,{})
    def test_legacy_unbound_and_direct_sql_mutation_refused(self):
        self.run.accept(self.b)
        a=self.adapter()
        with self.assertRaises(Conflict): a.create_fixture()
        with self.assertRaises(Conflict): a.execute_fixture(self.b,self.command,Event(self.b,1,'start','started'))
        with self.assertRaises(psycopg.errors.RaiseException):
            with connect() as c:
                c.execute('UPDATE cj_run_record SET usage_command_bytes=%s,usage_input_bytes=%s WHERE scope=%s',
                          (a.association.command_bytes,self.raw,self.scope))
        self.assertIsNone(self.run.snapshot(self.b).usage)
        self.assertEqual(self.usage.ledger.attempts,{})
    def test_create_ack_unknown_no_usage_and_no_rearm(self):
        class LostAck:
            def __init__(self): self.inner=connect()
            def __getattr__(self,name): return getattr(self.inner,name)
            def commit(self):
                self.inner.commit()
                raise OSError('binding commit ACK lost')
        a=self.adapter(run=Service(repository(self.scope,LostAck),lambda _:True))
        with self.assertRaises(CommitUnknown): a.create_fixture()
        state=self.run.snapshot(self.b)
        self.assertEqual(state.usage,a.association)
        rebuilt=self.adapter()
        with self.assertRaises(Conflict): rebuilt.create_fixture()
        with self.assertRaises(ReconcileOriginal): rebuilt.execute_fixture(self.b,self.command,Event(self.b,1,'start','started'))
        self.assertEqual(self.usage.ledger.attempts,{})
        self.assertEqual(self.calls,[])
    def test_claim_unknown_blocks_replacement_after_reconstruction(self):
        a=self.adapter()
        a.create_fixture()
        claim=self.meter.claim
        def lost(identity):
            claim(identity)
            raise OSError('claim ACK lost')
        self.meter.claim=lost
        with self.assertRaises(ReconcileOriginal): a.execute_fixture(self.b,self.command,Event(self.b,1,'start','started'))
        self.meter.claim=claim
        rebuilt=self.adapter(replace(self.command,attempt_id='replacement'))
        with self.assertRaises(Conflict): rebuilt.create_fixture()
        with self.assertRaises(Conflict): rebuilt.execute_fixture(self.b,rebuilt.original_command,Event(self.b,1,'start','started'))
        self.assertEqual(self.meter.query('a').state,'unknown')
        self.assertEqual(self.run.snapshot(self.b).status,'queued')
        self.assertEqual(self.calls,[])
    def test_expired_bound_row_not_replaced(self):
        a=self.adapter()
        a.create_fixture()
        with connect() as c:
            c.execute("UPDATE cj_run_record SET expires_at=clock_timestamp()-interval '1 second' WHERE scope=%s",(self.scope,))
        with self.assertRaises(ResyncRequired): a.create_fixture()
        with self.assertRaises(ResyncRequired): a.execute_fixture(self.b,self.command,Event(self.b,1,'start','started'))
        self.assertEqual(self.calls,[])
    def test_bound_sql_identity_immutable(self):
        a=self.adapter()
        a.create_fixture()
        for sql in ('UPDATE cj_run_record SET message_id=\'changed\' WHERE scope=%s',
                    'UPDATE cj_run_record SET usage_command_bytes=NULL,usage_input_bytes=NULL WHERE scope=%s'):
            with self.assertRaises(psycopg.errors.RaiseException):
                with connect() as c: c.execute(sql,(self.scope,))
        self.assertEqual(self.run.snapshot(self.b).usage,a.association)


if __name__=='__main__':
    with connect() as c:
        assert c.execute('SHOW listen_addresses').fetchone()[0]==''
        if not args.case:
            c.execute((pg_checks.ROOT/'sql/candidate.sql').read_text())
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(pg_checks.PgTests),
                             unittest.defaultTestLoader.loadTestsFromTestCase(BindingPgTests)])
    if args.case:
        suite=unittest.TestSuite([BindingPgTests(args.case)])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
