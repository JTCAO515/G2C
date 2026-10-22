import asyncio
from contextlib import contextmanager
from dataclasses import asdict, fields, replace
import hashlib
import json
import unittest
from cj_run.core import Binding, Event, State, Service, Conflict, Denied, ResyncRequired
from cj_run.fixture import MemoryRepository
from cj_run.postgres import Repository as PgRepository, Transaction as PgTransaction, CommitUnknown
from cj_run.usage_binding import UsageBinding
from cj_run.diagnostics import read_diagnostic, RunDiagnostic
from test_postgres_transaction import Connection, repo as pg_repo


class ReadFixture:
    def __init__(self, state=None, error=None, exit_error=None):
        self.state, self.error, self.exit_error = state, error, exit_error
    @contextmanager
    def transaction(self):
        yield self
        if self.exit_error: raise self.exit_error
    def get(self,binding):
        if self.error: raise self.error
        return self.state


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.b=Binding('fixture-scope','chat','g','m','r',1)
        self.repo=MemoryRepository()
        self.service=Service(self.repo,lambda _:True)
        raw=b'PRIVATE_OUTBOUND'
        values=dict(attempt_id='PRIVATE_ATTEMPT',operation_id='PRIVATE_OPERATION',run_id='r',kind='model',
                    input_digest=hashlib.sha256(raw).hexdigest(),reserve=17,output_limit=23)
        usage=UsageBinding(json.dumps(values).encode(),raw)
        self.service.accept_with_usage(self.b,usage)
        self.service.apply(Event(self.b,1,'start','started'))
        self.service.apply(Event(self.b,2,'text','text_delta','PRIVATE_TEXT'))
        self.service.apply(Event(self.b,3,'effect','effect_committed','PRIVATE_RECEIPT'))

    def test_exact_whitelist_no_raw_or_inferred_fields(self):
        result=read_diagnostic(self.repo,self.b)
        self.assertEqual(result,RunDiagnostic(self.b,'running',3))
        self.assertEqual({f.name for f in fields(result)}, {'binding','status','event_highwater'})
        encoded=json.dumps(asdict(result))
        for secret in ('PRIVATE_', 'input_digest', 'usage', 'text', 'effects', 'event_id', 'model_version', 'failure_stage', 'tool_status'):
            self.assertNotIn(secret,encoded)
        self.assertNotIsInstance(result,State)

    def test_same_run_wrong_complete_binding_rejected(self):
        for key,value in [('scope','other'),('message_id','other'),('conversation_id','other'),('generation','other'),('message_sequence',2)]:
            with self.subTest(key=key):
                with self.assertRaises(Conflict): read_diagnostic(self.repo,replace(self.b,**{key:value}))
        with self.assertRaises(ValueError): read_diagnostic(self.repo,{'run_id':'r'})

    def test_cancelled_run_and_unknown_are_truthful_statuses(self):
        self.service.apply(Event(self.b,4,'cancel','cancelled'))
        self.assertEqual(read_diagnostic(self.repo,self.b),RunDiagnostic(self.b,'cancelled',4))
        unknown=State(self.b,status='unknown')
        self.assertEqual(read_diagnostic(ReadFixture(unknown),self.b).status,'unknown')

    def test_read_failures_never_become_null_success(self):
        for error in (Conflict('missing'),Denied('inactive'),ResyncRequired('expired'),OSError('read failed'),asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)): read_diagnostic(ReadFixture(error=error),self.b)
        with self.assertRaises(Conflict): read_diagnostic(ReadFixture(None),self.b)

    def test_exit_guard_unknown_commit_and_cancel_withhold_result(self):
        state=self.service.snapshot(self.b)
        for error in (Denied('return identity guard'),CommitUnknown(),asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)): read_diagnostic(ReadFixture(state,exit_error=error),self.b)

    def test_corrupt_foreign_and_future_state_not_guessed(self):
        state=self.service.snapshot(self.b)
        for corrupt in (replace(state,binding=replace(self.b,generation='foreign')),
                        replace(state,status='new_future_status'),replace(state,events=(state.events[-1],))):
            with self.subTest(status=corrupt.status):
                with self.assertRaises((Conflict,ResyncRequired)): read_diagnostic(ReadFixture(corrupt),self.b)

    def test_pg_active_guard_is_consumed(self):
        connection=Connection(active=False)
        with self.assertRaises(Denied): read_diagnostic(pg_repo(connection),self.b)
        self.assertNotIn('commit',connection.actions)

    def test_pg_expiry_and_scope_guards_are_consumed(self):
        class Cursor:
            def execute(self,*_): pass
            def fetchone(self): return ('chat','g','m',1,'running',3,False,None,None)
        tx=PgTransaction(Cursor(),self.b.scope,'epoch',None)
        class Injected:
            @contextmanager
            def transaction(self): yield tx
        with self.assertRaises(ResyncRequired): read_diagnostic(Injected(),self.b)
        with self.assertRaises(Denied): read_diagnostic(Injected(),replace(self.b,scope='foreign'))
