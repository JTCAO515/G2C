"""Canonical AUTH types with synthetic facts; no real account or authority claim."""
from pathlib import Path
import sys
# Reuse sibling canonical AUTH types; no copied principal/permission model.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "auth"))
from copy import deepcopy
from dataclasses import asdict
import json
import unittest
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import (TrustedPrincipal, VerificationResult, VerificationStatus,
    AdmissionStatus, CJAccessFacts, Fact)
from cj_usage.core import Config, Ledger, Command, Attempt, Receipt, Run
from cj_usage.postgres import PostgresRepository, CommitUnknown, RepositoryUnavailable
from cj_usage.codec import CorruptLedger
from cj_usage.read_status import ReadUnavailable

class Cancelled(BaseException): pass

class ReadTests(unittest.TestCase):
    def setUp(self):
        self.allowed = True
        self.p = TrustedPrincipal('synthetic-issuer','synthetic-sub','synthetic-aud',0,0,1000)
        owner=self
        class Verifier:
            def verify(self,token): return VerificationResult(VerificationStatus.VALID,owner.p)
        class Facts:
            def evaluate(self,p): return CJAccessFacts(p,Fact.YES,Fact.YES,Fact.YES if owner.allowed else Fact.UNKNOWN)
        self.checker=AdmissionChecker(Verifier(),Facts(),clock=lambda:100)
        self.original=self.p
        self.log=[];self.hooks={};self.errors={}
        config=Config('synthetic-unit',10,0,1000,20,3,20,50)
        cmd=Command('a','op','run','model','a'*64,6,2)
        self.ledger=Ledger(config,{'a':Attempt(cmd,'unknown')},{'run':Run(100,1)},100)
        self.row=(7,1,asdict(self.ledger))
        self.conn=self.Conn(self)
        self.factory=lambda:self.conn
        self.repo=PostgresRepository(self.factory,'scope-a')

    def event(self,name):
        self.log.append(name)
        if name in self.hooks:self.hooks[name]()
        if name in self.errors:raise self.errors[name]

    class Conn:
        autocommit=False
        def __init__(self,o):self.o=o
        def cursor(self):self.o.event('cursor');return ReadTests.Cur(self.o)
        def commit(self):self.o.event('commit')
        def rollback(self):self.o.event('rollback')
        def close(self):self.o.event('connection_close')
    class Cur:
        def __init__(self,o):self.o=o
        def execute(self,sql,args=None):
            self.o.event('set' if sql.startswith('SET ') else 'select')
            self.o.log.append((sql,args))
        def fetchone(self):self.o.event('fetch');return deepcopy(self.o.row)
        def close(self):self.o.event('cursor_close')

    def guard(self):
        decision=self.checker.check('synthetic-only')
        if decision.status is not AdmissionStatus.ALLOWED or decision.principal != self.original:
            raise ReadUnavailable('authority changed')
    def read(self,**kwargs):
        return self.repo.read_status('a',guard=self.guard,max_response_bytes=4096,**kwargs)

    def test_select_only_and_minimal_unknown(self):
        result=json.loads(self.read())
        self.assertEqual(result['status'],'unknown')
        self.assertIsNone(result['confirmed_units'])
        self.assertIsNone(result['confirmed_output'])
        self.assertIsNone(result['receipt_id'])
        self.assertEqual(result['unit'],'synthetic-unit')
        self.assertTrue(result['message_zh']);self.assertTrue(result['message_en'])
        for key in ('input_digest','scope','config','budget','attempts'):
            self.assertNotIn(key,result)
        sql=[x[0] for x in self.log if isinstance(x,tuple)]
        self.assertEqual(len(sql),2)
        self.assertIn('READ ONLY',sql[0]);self.assertTrue(sql[1].startswith('SELECT '))
        self.assertNotIn('FOR UPDATE',sql[1])
        self.assertEqual(self.row[0],7)

    def test_all_states_zero_receipt_and_cancellation(self):
        for state in ('reserved','unknown','released','settled'):
            l=deepcopy(self.ledger)
            receipt=Receipt('a','receipt','synthetic-unit',0,0) if state=='settled' else None
            cancelled=state=='released'
            l.attempts['a']=Attempt(l.attempts['a'].command,state,receipt,cancelled)
            l.runs['run'].cancelled=cancelled
            self.row=(7,1,asdict(l))
            d=json.loads(self.read())
            self.assertEqual(d['status'],state)
            self.assertEqual(d['confirmed_units'],0 if receipt else None)
            self.assertEqual(d['cancelled'],cancelled)

    def test_admission_denied_before_connection(self):
        self.allowed=False
        with self.assertRaises(ReadUnavailable):self.read()
        self.assertEqual(self.log,[])

    def test_every_callback_revocation_withholds(self):
        for stage in ('cursor','set','select','fetch','commit','cursor_close','connection_close'):
            with self.subTest(stage=stage):
                self.setUp();self.hooks[stage]=lambda:setattr(self,'allowed',False)
                with self.assertRaises(ReadUnavailable):self.read()
                self.assertIn('connection_close',self.log)

    def test_resolver_connection_callback_rebinding(self):
        def connect():
            self.allowed=False
            return self.conn
        self.repo=PostgresRepository(connect,'scope-a')
        with self.assertRaises(ReadUnavailable):self.read()
        self.assertIn('connection_close',self.log)

    def test_final_close_identity_and_scope_change(self):
        for mutation in (lambda:setattr(self,'p',TrustedPrincipal('issuer','other','aud',0,0,1000)),
                         lambda:setattr(self.repo,'scope','scope-b'),
                         lambda:setattr(self.repo,'connect',lambda:self.conn)):
            self.setUp();self.hooks['connection_close']=mutation
            with self.assertRaises(ReadUnavailable):self.read()

    def test_project_final_encoding_and_revoke(self):
        def project(data):
            result=b'{"envelope":'+data+b'}'
            self.allowed=False
            return result
        with self.assertRaises(ReadUnavailable):self.read(project=project)
        self.assertIn('connection_close',self.log)

    def test_cleanup_error_prevents_result(self):
        for stage in ('cursor_close','connection_close'):
            self.setUp();self.errors[stage]=RuntimeError('synthetic close')
            with self.assertRaisesRegex(ReadUnavailable,'cleanup'):self.read()
            self.assertIn('connection_close',self.log)

    def test_primary_and_commit_unknown_priority(self):
        for stage,err in [('select',ValueError('primary')),('commit',OSError('unknown')),
                          ('fetch',Cancelled())]:
            self.setUp();self.errors[stage]=err
            self.errors['cursor_close']=RuntimeError('cleanup')
            self.errors['connection_close']=RuntimeError('cleanup')
            expected=CommitUnknown if stage=='commit' else type(err)
            with self.assertRaises(expected):self.read()
            if stage=='commit':self.assertNotIn('rollback',self.log)

    def test_missing_corrupt_and_version_never_reset(self):
        for row,err in [(None,RepositoryUnavailable),((7,1,{}),CorruptLedger),
                        ((7,2,asdict(self.ledger)),CorruptLedger)]:
            self.setUp();self.row=row
            with self.assertRaises(err):self.read()
            self.assertNotIn('commit',self.log)

    def test_bound_materialized_projection_and_guard_required(self):
        for project in (lambda b:'text',lambda b:iter([b]),lambda b:b*30):
            with self.assertRaises(ReadUnavailable):self.read(project=project)
        with self.assertRaises(ReadUnavailable):
            self.repo.read_status('a',guard=None,max_response_bytes=4096)
        with self.assertRaises(ReadUnavailable):
            self.repo.read_status('a',guard=lambda:True,max_response_bytes=4096)

    def test_cross_scope_missing_attempt_same_unavailable(self):
        self.row=None
        with self.assertRaises(RepositoryUnavailable):self.read()
        self.row=(7,1,asdict(Ledger(self.ledger.config)))
        with self.assertRaises(RepositoryUnavailable):self.read()

    def test_autocommit_rejected_and_closed(self):
        self.conn.autocommit=True
        with self.assertRaises(ReadUnavailable):self.read()
        self.assertIn('connection_close',self.log)
