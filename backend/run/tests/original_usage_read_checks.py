"""Actual MESSAGE bf79 + canonical RUN DB-API recovery, synthetic callbacks/data."""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import inspect
import json
import unittest
import display_snapshot_checks as message_fixture
from cj_message.auth_boundary import AccessBlocked, IdentityChanged
from cj_run.core import Conflict, Denied, ResyncRequired
from cj_run.postgres import Repository, CommitUnknown, RecoveryReadUnavailable
from cj_run.original_usage_read import (OriginalUsageAssociationReader, UsageAssociationReadConfiguration,
    UsageAssociationUnavailable, UsageAssociationChanged, UsageAssociationTooLarge)


class Database:
    def __init__(self, state):
        self.state=state
        self.epoch='epoch1'
        self.active=True
        self.expired=False
        self.missing=False
        self.hooks={}
        self.log=[]
    def call(self,name):
        self.log.append(name)
        if name in self.hooks: self.hooks[name]()
    def connect(self):
        self.call('connect')
        database=self
        class Connection:
            autocommit=False
            def cursor(self):
                database.call('cursor')
                return Cursor()
            def commit(self): database.call('commit')
            def rollback(self): database.call('rollback')
            def close(self): database.call('connection_close')
        class Cursor:
            query=''
            params=()
            def execute(self,query,params=()):
                self.query,self.params=query,params
                assert query.startswith(('SELECT','SET TRANSACTION')), 'read issued business mutation'
                database.call('execute')
            def fetchone(self):
                database.call('fetchone')
                if 'FROM cj_run_scope' in self.query:
                    return (database.epoch,database.active)
                if 'FROM cj_run_record' in self.query:
                    if database.missing:return None
                    state=database.state;b=state.binding;usage=state.usage
                    if self.params!=(b.scope,b.run_id):return None
                    return (b.conversation_id,b.generation,b.message_id,b.message_sequence,state.status,
                            state.sequence,not database.expired,usage.command_bytes if usage else None,
                            usage.input_bytes if usage else None)
                raise AssertionError('unexpected SQL')
            def fetchall(self):
                database.call('fetchall')
                return [(e.sequence,e.event_id,e.kind,e.value) for e in database.state.events]
            def close(self): database.call('cursor_close')
        return Connection()


class OriginalUsageTests(unittest.TestCase):
    def setUp(self):
        self.f=message_fixture.SnapshotTests();self.f.setUp()
        self.db=Database(self.f.service.snapshot(self.f.binding))
        self.repo=Repository(self.db.connect,'trusted-a',expires_at=datetime(2099,1,1,tzinfo=timezone.utc),
                             statement_timeout_ms=1000,lock_timeout_ms=1000)
        self.resolutions=[]
        def resolver(principal,scope):
            self.resolutions.append((principal,scope))
            return self.repo
        self.reader=OriginalUsageAssociationReader(self.f.boundary,resolver,
                         configuration=UsageAssociationReadConfiguration(10000))
    def read(self,project=None):
        if project is None:return self.reader.read('synthetic','mé')
        return self.reader.read_projected('synthetic','mé',project)
    @staticmethod
    def envelope(body):return b'{"request_id":"synthetic-trace","association":'+body+b'}'

    def test_exact_original_whitelist_only_and_no_mutation(self):
        encoded=self.read();data=json.loads(encoded)
        self.assertEqual(data,dict(conversation_id='chat',generation='g1',message_id='mé',message_sequence=1,
                                  run_id='original-run',attempt_id='PRIVATE_ATTEMPT',operation_id='PRIVATE_OPERATION'))
        for secret in (b'PRIVATE_OUTBOUND',b'PRIVATE_USER_BODY',b'trusted-a',b'input_digest',b'reserve',b'output_limit',b'kind',b'period',b'usage',b'text',b'PRIVATE_EFFECT'):
            self.assertNotIn(secret,encoded)
        self.assertEqual(self.resolutions,[(self.f.p,'trusted-a')])
        self.assertEqual(self.db.log.count('connect'),2)
        self.assertEqual(self.db.log.count('connection_close'),2)
        self.assertNotIn('rollback',self.db.log)
        self.assertEqual(self.db.state,self.f.service.snapshot(self.f.binding))

    def test_projected_envelope_and_explicit_final_limit(self):
        body=self.read();envelope=self.envelope(body)
        self.reader.configuration=UsageAssociationReadConfiguration(len(envelope))
        self.assertEqual(self.read(self.envelope),envelope)
        self.reader.configuration=UsageAssociationReadConfiguration(len(envelope)-1)
        with self.assertRaises(UsageAssociationTooLarge):self.read(self.envelope)
        with self.assertRaises(ValueError):UsageAssociationReadConfiguration(True)
        with self.assertRaises(ValueError):UsageAssociationReadConfiguration(0)
        with self.assertRaises(ValueError):OriginalUsageAssociationReader(self.f.boundary,lambda p,s:self.repo,configuration=None)

    def test_original_association_absent_incomplete_or_corrupt_is_unavailable(self):
        self.db.state=replace(self.db.state,usage=None)
        with self.assertRaises(UsageAssociationUnavailable):self.read()
        for change in ('incomplete','digest','run'):
            with self.subTest(change=change):
                self.setUp();usage=self.db.state.usage
                if change=='incomplete':raw=b'{}'
                else:
                    values=usage.values();values['input_digest' if change=='digest' else 'run_id']='0'*64 if change=='digest' else 'different'
                    raw=json.dumps(values).encode()
                # Synthetic corrupt on-disk row bytes: no valid constructor fabricated.
                object.__setattr__(usage,'command_bytes',raw)
                with self.assertRaises(ResyncRequired):self.read()
        self.assertFalse(any('insert' in item.lower() for item in self.db.log))

    def test_full_binding_wrong_user_missing_or_expired(self):
        self.f.p=replace(self.f.p,subject='other')
        with self.assertRaises(UsageAssociationUnavailable):self.read()
        self.assertEqual(self.resolutions,[])
        for field,value in [('scope','other'),('conversation_id','other'),('generation','other'),('message_id','other'),('run_id','other'),('message_sequence',2)]:
            with self.subTest(field=field):
                self.setUp();self.db.state=replace(self.db.state,binding=replace(self.db.state.binding,**{field:value}))
                with self.assertRaises(Conflict):self.read()
        self.setUp();self.db.missing=True
        with self.assertRaises(Conflict):self.read()
        self.setUp();self.db.expired=True
        with self.assertRaises(ResyncRequired):self.read()
        self.setUp();self.db.active=False
        with self.assertRaises(Denied):self.read()
        self.setUp();self.f.stored=None
        with self.assertRaises(UsageAssociationUnavailable):self.read()
        self.setUp();self.f.generation='old'
        with self.assertRaises(message_fixture.Unavailable):self.read()

    def test_projection_changed_source_association_epoch_or_identity(self):
        for change in ('source','association','epoch','identity'):
            with self.subTest(change=change):
                self.setUp()
                def project(body):
                    if change=='source':self.f.stored=replace(self.f.original,receipt=replace(self.f.original.receipt,sequence=2))
                    elif change=='association':self.db.state=replace(self.db.state,usage=None)
                    elif change=='epoch':self.db.epoch='epoch2'
                    else:self.f.p=replace(self.f.p,subject='other')
                    return self.envelope(body)
                with self.assertRaises((UsageAssociationUnavailable,IdentityChanged)):self.read(project)

    def test_projection_reentry_deferred_exception_and_cancel(self):
        with self.assertRaises(RuntimeError):self.read(lambda body:self.read())
        async def deferred():return b'never'
        pending=deferred()
        for value in ({},'not bytes',bytearray(b'body'),iter([b'body']),pending):
            with self.assertRaises(UsageAssociationUnavailable):self.read(lambda body:value)
        self.assertEqual(inspect.getcoroutinestate(pending),inspect.CORO_CLOSED)
        for error in (OSError('projection'),asyncio.CancelledError()):
            def project(body):raise error
            with self.assertRaises(type(error)):self.read(project)
        self.assertIs(type(self.read()),bytes)

    def test_storage_commit_close_and_cancel_failures_withhold(self):
        def fail(error):
            def hook():raise error
            return hook
        for stage in ('connect','cursor','execute','fetchone','fetchall'):
            with self.subTest(stage=stage):
                self.setUp();self.db.hooks[stage]=fail(OSError('synthetic DB failure'))
                with self.assertRaises(OSError):self.read()
        self.setUp();self.db.hooks['commit']=fail(OSError('commit ACK unknown'))
        with self.assertRaises(CommitUnknown):self.read()
        for stage in ('cursor_close','connection_close'):
            with self.subTest(stage=stage):
                self.setUp();self.db.hooks[stage]=fail(OSError('close failed'))
                with self.assertLogs('cj_run.postgres'):
                    with self.assertRaises(RecoveryReadUnavailable):self.read()
        self.setUp();self.db.hooks['connection_close']=fail(asyncio.CancelledError())
        with self.assertLogs('cj_run.postgres'):
            with self.assertRaises(asyncio.CancelledError):self.read()

    def test_storage_callbacks_scope_connect_and_config_rebinding(self):
        for stage in ('connect','cursor','execute','fetchone','fetchall','commit','cursor_close','connection_close'):
            with self.subTest(stage=stage):
                self.setUp()
                self.db.hooks[stage]=lambda:setattr(self.repo,'connect',lambda:None)
                with self.assertRaises(UsageAssociationChanged):self.read()
        self.setUp()
        def enlarge(body):
            self.reader.configuration=UsageAssociationReadConfiguration(999999)
            return body
        with self.assertRaises(UsageAssociationChanged):self.read(enlarge)

    def test_final_auth_callback_cannot_rebind_domain_before_publication(self):
        for kind in ('scope','connect','configuration','resolver','boundary','timeout','expiry','config_value'):
            with self.subTest(kind=kind):
                self.setUp();self.install_last_callback(kind)
                with self.assertRaises(UsageAssociationChanged):self.read()
                self.assertEqual(self.last_access.after_close,4)
                self.assertEqual(self.db.log.count('connection_close'),2)

    def install_last_callback(self,kind):
        owner=self;original=self.f.boundary.checker._access
        class LastAccess:
            after_close=0
            def evaluate(self,p):
                if owner.db.log.count('connection_close')>=2:
                    self.after_close+=1
                    if self.after_close==4:
                        if kind=='scope':owner.repo.scope='replacement'
                        elif kind=='connect':owner.repo.connect=lambda:None
                        elif kind=='configuration':owner.reader.configuration=UsageAssociationReadConfiguration(10000)
                        elif kind=='resolver':owner.reader.resolve_run_repository=lambda p,s:owner.repo
                        elif kind=='boundary':owner.reader.message_boundary=None
                        elif kind=='timeout':owner.repo.lock_timeout_ms=999
                        elif kind=='expiry':owner.repo.expires_at=datetime(2100,1,1,tzinfo=timezone.utc)
                        elif kind=='config_value':object.__setattr__(owner.reader.configuration,'max_response_bytes',99999)
                return original.evaluate(p)
        self.last_access=LastAccess();self.f.boundary.checker._access=self.last_access

    def test_final_same_principal_denial_withholds(self):
        self.install_last_callback('nothing')
        original=self.last_access.evaluate
        def deny(p):
            result=original(p)
            if self.last_access.after_close==4:return replace(result,invited=message_fixture.Fact.UNKNOWN)
            return result
        self.last_access.evaluate=deny
        with self.assertRaises(AccessBlocked):self.read()

    def test_query_never_mints_attempt_for_claim_or_execution_unknown(self):
        self.f.seed_text();self.f.event('unknown')
        self.db.state=self.f.service.snapshot(self.f.binding)
        original=self.db.state
        result=json.loads(self.read())
        self.assertEqual(result['attempt_id'],'PRIVATE_ATTEMPT')
        self.assertNotIn('status',result)
        self.assertEqual(self.db.state,original)

    def test_canonical_repository_required_and_legacy_recovery_unchanged(self):
        self.reader.resolve_run_repository=lambda p,s:object()
        with self.assertRaises(UsageAssociationUnavailable):self.read()
        self.db.hooks['connection_close']=lambda:(_ for _ in ()).throw(OSError('close failed'))
        with self.assertLogs('cj_run.postgres'):
            # Explicit default compatibility: existing recover still returns its value.
            self.assertIsNotNone(self.repo.recover(self.f.binding))


if __name__=='__main__':unittest.main(verbosity=2)
