"""Typed storage with real signed B identity APIs/current leases and runtime PG."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
import uuid
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/agent/tests'),str(ROOT/'scripts')]
from e2e_local import Harness,CONNINFO
from cj_api.local_app import LocalDatabase,scope_for,ISSUER
from cj_api.local_worker_context import checker_for
from cj_auth.interfaces import AdmissionStatus
from cj_memory.domain import Service,Command,Unavailable,Conflict
from cj_memory.postgres import Repository
from cj_memory.manual import ManualPolicy
from cj_memory.typed import ContextRef
from cj_message.travel_reference import MessageContextAuthority
from cj_message.travel import Selection
from title_projection_pg import TitleProjectionPG


class TypedStorageChecks(TitleProjectionPG,Harness):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import time
        import local_run_context as operator
        import dev_auth as local_auth
        from cj_api.local_app import create_local_app
        from cj_api.local_run_context import load_run_context
        from cj_message.travel import ABI
        now=int(time.time());cls.run_path=cls.auth/'typed-run.json'
        cls.run_path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(
            unit='provider_call',budget=100,period_start=now-60,period_end=now+3600,max_steps=20,
            max_tools=10,max_output=10000,max_seconds=600),
            output_limits=dict(model=4000,tool=8000,memory=2000)),history=[])))
        cls.run_context=load_run_context(cls.run_path)
        for identity in ('alice','bob'):
            operator.provision_budget(CONNINFO,cls.run_context,identity)
            local_auth.activate_travel(CONNINFO,identity,cls.run_context,ABI)
        cls.database=LocalDatabase(CONNINFO,run_context=cls.run_context,travel_context=True)
        cls.app=create_local_app(conninfo_path=CONNINFO,auth_dir=cls.auth,
                                run_context=cls.run_context,travel_context=True)

    def setUp(self):
        self.tag=uuid.uuid4().hex
        self.scope=scope_for(ISSUER,'alice')
        self.checker=checker_for(self.auth)
        self.token=self.headers('alice')['Authorization'].removeprefix('Bearer ')
        def admit():
            value=self.checker.check(self.token)
            if value.status is not AdmissionStatus.ALLOWED:raise Unavailable('fresh actual admission required')
            return value.principal
        self.admit=admit
        self.authority=MessageContextAuthority(self.database.message_repository(self.scope),admit)
        with TestClient(self.app) as client:
            self.travel=[]
            for label in ('A','B'):
                raw=json.dumps(dict(version='TRAVEL-context-action.1',action_id=label+'-'+self.tag,
                                    operation='create',travel_context=None)).encode()
                response=client.post('/v1/travel-context-actions',content=raw,
                    headers={**self.headers('alice'),'Content-Type':'application/octet-stream'})
                self.assertEqual(response.status_code,200,response.text)
                self.travel.append(response.json()['receipt']['travel_context'])
        with self.database.connect(self.scope) as conn:
            conn.execute('INSERT INTO cj_memory_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',(self.scope,))
        policy=ManualPolicy(frozenset({'self'}),frozenset({'pace-'+self.tag}),
            frozenset({'long_term','current'}),frozenset(x['id'] for x in self.travel),
            datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:True,lambda command,raw:True)
        self.service=Service(Repository(lambda:self.database.connect(self.scope),self.scope,
            transaction_binder=lambda conn,cur:conn.bind_scope(cur),typed_context=True),manual_policy=policy)

    def raw(self,context=None,*,text='长期 / long term'):
        return json.dumps(dict(version='MEMORY-manual.2',operation_id='op-'+uuid.uuid4().hex,
            item_id='item-'+uuid.uuid4().hex,subject='self',slot='pace-'+self.tag,kind='preference',text=text,
            extent='long_term' if context is None else 'current',
            context=None if context is None else dict(kind='travel',id=context['id'],expected_version=context['version']),
            occurred_at='date unknown'),ensure_ascii=False,separators=(',',':')).encode()

    def guard(self,stage):return self.admit(),self.scope
    def save(self,raw,authority=None):
        return json.loads(self.service.with_operation(self.guard,lambda operation:json.dumps(
            operation.save_manual_typed(raw,self.authority if authority is None else authority).__dict__).encode()))
    def selected(self,context):
        with self.authority.hold_current(Selection(context['id'],context['version'])) as lease:
            return self.service.effective('self',ContextRef('travel',lease.context.id))

    @contextmanager
    def readonly_connections(self,database):
        from unittest.mock import patch
        original=database._open_runtime_connection;opened=[]
        def connect():
            conn=original();conn.read_only=True;opened.append(True);return conn
        with patch.object(database,'_open_runtime_connection',connect):yield opened

    def memory_snapshot(self,scope):
        tables=('cj_memory_scope','cj_memory_item','cj_memory_source','cj_memory_operation',
                'cj_memory_management_action','cj_run_metered_operation','cj_message_context_profile')
        with self.database.connect(scope) as conn:
            return {table:conn.execute('SELECT row_to_json(t)::text FROM '+table+' t ORDER BY 1').fetchall()
                    for table in tables}

    def test_readonly_binding_existing_typed_memory_uses_no_DML(self):
        from psycopg.errors import ReadOnlySqlTransaction
        raw=self.raw(self.travel[0]);saved=self.save(raw)
        configuration,_=self.runtime_configuration()
        database=LocalDatabase(CONNINFO,run_context=self.run_context,travel_context=True)
        authority=MessageContextAuthority(database.message_repository(self.scope),self.admit)
        before=self.memory_snapshot(self.scope)
        with self.readonly_connections(database) as opened:
            bound=configuration.bind_readonly(database,self.scope,'alice',self.admit,message_context=authority)
            self.assertEqual(bound.guard('readonly_probe'),(self.admit(),self.scope))
            self.assertEqual(bound.payload_version,'MEMORY-RUN-CONSUME@2')
            self.assertEqual(len(opened),1)
            # Control: the unchanged provisioning bind really attempts its old
            # INSERT, even for an existing namespace, and PostgreSQL rejects it.
            with self.assertRaises(ReadOnlySqlTransaction):
                configuration.bind(database,self.scope,'alice',self.admit,message_context=authority)
        self.assertEqual(bound.service.detail(saved['item_id']).command.raw,
                         self.service.detail(saved['item_id']).command.raw)
        self.assertEqual(self.memory_snapshot(self.scope),before)

    def test_readonly_binding_missing_namespace_refuses_without_creating_it(self):
        from copy import deepcopy
        from e2e_local import dev_auth
        from cj_memory.typed_runtime import TypedRuntimeConfiguration
        from cj_memory.runtime import RuntimeDenied
        identity='readonly-'+self.tag;scope=scope_for(ISSUER,identity)
        auth=Path(self.tmp.name)/identity;dev_auth('init',str(auth),'--invite',identity)
        token=dev_auth('token',str(auth),'--subject',identity);checker=checker_for(auth)
        def admit():
            decision=checker.check(token);self.assertIs(decision.status,AdmissionStatus.ALLOWED)
            return decision.principal
        _,document=self.runtime_configuration();profile=deepcopy(document['collection']['collection']['profiles']['alice'])
        document['collection']['collection']['profiles']={identity:profile}
        document['collection']['travel_contexts']={identity:[]}
        document['selections']={identity:document['selections']['alice']}
        configuration=TypedRuntimeConfiguration.from_bytes(json.dumps(document).encode())
        import local_run_context as operator
        import dev_auth as local_auth
        from cj_message.travel import ABI
        operator.provision_budget(CONNINFO,self.run_context,identity)
        local_auth.activate_travel(CONNINFO,identity,self.run_context,ABI)
        database=LocalDatabase(CONNINFO,run_context=self.run_context,travel_context=True)
        database.provision(scope)
        authority=MessageContextAuthority(database.message_repository(scope),admit)
        before=self.memory_snapshot(scope);self.assertEqual(before['cj_memory_scope'],[])
        with self.readonly_connections(database):
            with self.assertRaisesRegex(RuntimeDenied,'original memory scope unavailable'):
                configuration.bind_readonly(database,scope,identity,admit,message_context=authority)
        self.assertEqual(self.memory_snapshot(scope),before)
        # Compatibility: the existing bind still provisions its own namespace.
        configuration.bind(database,scope,identity,admit,message_context=authority)
        after=self.memory_snapshot(scope);self.assertEqual(len(after['cj_memory_scope']),1)
        self.assertEqual(after['cj_run_metered_operation'],before['cj_run_metered_operation'])

    def test_fresh_runtime_epoch_view_needs_no_candidate_history_fence(self):
        """Existing public capture/hold API; no new collection or history grant."""
        from copy import deepcopy
        from unittest.mock import patch
        from e2e_local import dev_auth
        from cj_api.local_app import create_local_app
        from cj_memory.typed_runtime import TypedRuntimeConfiguration
        from cj_memory.runtime import RuntimeDenied
        from cj_run.core import Binding
        import local_run_context as operator
        import dev_auth as local_auth
        from cj_message.travel import ABI
        identity='epoch-view-'+self.tag;scope=scope_for(ISSUER,identity)
        auth=Path(self.tmp.name)/identity;dev_auth('init',str(auth),'--invite',identity)
        token=dev_auth('token',str(auth),'--subject',identity);checker=checker_for(auth)
        def admit():
            decision=checker.check(token)
            if decision.status is not AdmissionStatus.ALLOWED:raise Unavailable('current signed identity required')
            return decision.principal
        _,document=self.runtime_configuration()
        profile=deepcopy(document['collection']['collection']['profiles']['alice'])
        document['collection']['collection']['profiles']={identity:profile}
        document['collection']['travel_contexts']={identity:[]}
        document['selections']={identity:document['selections']['alice']}
        configuration=TypedRuntimeConfiguration.from_bytes(json.dumps(document).encode())
        operator.provision_budget(CONNINFO,self.run_context,identity)
        local_auth.activate_travel(CONNINFO,identity,self.run_context,ABI)
        database=LocalDatabase(CONNINFO,run_context=self.run_context,travel_context=True)
        database.provision(scope)
        authority=MessageContextAuthority(database.message_repository(scope),admit)
        # Explicit fixture setup, not part of the display read: creates the initial active scope
        # through the unchanged provisioner, with no history consent/fence.
        configuration.bind(database,scope,identity,admit,message_context=authority)
        app=create_local_app(conninfo_path=CONNINFO,auth_dir=auth,run_context=self.run_context,travel_context=True)
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
        with TestClient(app) as client:
            chat=client.put('/v1/conversations',params={'conversation_id':'fresh-epoch-view'},headers=headers).json()
            raw=json.dumps(dict(version='MESSAGE-send.2',conversation_id='fresh-epoch-view',message_id='epoch-'+self.tag,
                text='Read current profile only',trip_id=None,creation_intent='none',expected_generation=chat['generation'],
                expected_sequence=chat['last_sequence'],travel_context=None,needs_reference=None)).encode()
            response=client.post('/v2/messages',content=raw,headers=headers)
            self.assertEqual(response.status_code,200,response.text)
            receipt=response.json()['receipt']
        binding=Binding(scope,receipt['conversation_id'],receipt['generation'],receipt['message_id'],receipt['run_id'],receipt['sequence'])
        runtime=configuration.bind_readonly(database,scope,identity,admit,message_context=authority)
        def snapshot():
            with database.connect(scope) as connection:
                digest=hashlib.sha256(scope.encode()).hexdigest()
                fence=connection.execute('SELECT erased FROM cj_memory_history_fence WHERE scope_digest=%s',(digest,)).fetchall()
            return self.memory_snapshot(scope),fence
        before,fence=snapshot();self.assertEqual(fence,[])
        with database.connect(scope) as connection:
            native_epoch=connection.execute('SELECT epoch FROM cj_memory_scope WHERE scope=%s',(scope,)).fetchone()[0]
        self.assertGreater(native_epoch,0)
        with authority.hold_for_effect(binding):
            captured=runtime.capture(binding)
            self.assertEqual(captured.snapshot.epoch,native_epoch)
            with captured.hold(binding) as check:
                encoded=json.dumps(dict(memory_epoch=captured.snapshot.epoch)).encode()
                check()
            self.assertEqual(json.loads(encoded),dict(memory_epoch=native_epoch))
        self.assertEqual(snapshot(),(before,[]))
        # Exact API-host composition: one existing HistoryReadContext M frame,
        # not a worker's MessageContextAuthority lease or a second M lock.
        from cj_memory.epoch_projection import CurrentScopeEpochReader
        from cj_message.auth_boundary import Boundary,HistoryReadContext
        from cj_message.postgres import Transaction as MessageTransaction
        from cj_api.local_account_admission_v2 import account_checker_for,retired_in_transaction
        from cj_api.local_worker_context import checker_factory_for
        database=LocalDatabase(CONNINFO,run_context=self.run_context,travel_context=True,needs_context=True,trip_context=True)
        subjects=frozenset({identity})
        lio=create_local_app(conninfo_path=None,auth_dir=auth,database=database,run_context=self.run_context,
            account_admission=True,demo_dialogue_subjects=subjects,lio_dialogue_subjects=subjects)
        lio_mid='epoch-lio-'+self.tag
        with TestClient(lio) as client:
            result=client.post('/v2/lio/messages',content=json.dumps(dict(version='LIO-message.2',
                message_id=lio_mid,text='Read a profile only',locale='en',new_conversation=True)).encode(),headers=headers)
            self.assertEqual(result.status_code,200,result.text)
        checker_builder=checker_factory_for(auth,selected_subjects=subjects)
        def transaction_checker(transaction,scope):return checker_builder(retired_in_transaction(transaction.cur,scope))
        boundary=Boundary(account_checker_for(auth,database,selected_subjects=subjects),
            lambda principal:database.message_repository(scope_for(principal.issuer,principal.subject)),lambda:'unused',
            checker_in_transaction=transaction_checker)
        # Actual API supplies only TypedConfiguration; worker selections and
        # MEMORY_RUN_POLICY are deliberately not passed to this constructor.
        reader=CurrentScopeEpochReader.for_api(database,configuration.collection)
        self.assertIsNone(reader.selections)
        with self.assertRaises(RuntimeDenied):CurrentScopeEpochReader.for_api(database,None)
        locks=[];lock=MessageTransaction.lock_scope
        def counted(tx):locks.append(tx.scope);return lock(tx)
        observed=[]
        def project(context):
            def framed():
                stored=context.query_lio_message(lio_mid);r=stored.receipt
                original=Binding(scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
                observed.append(original)
                return reader.project(context,original,lambda epoch:json.dumps(dict(memory_epoch=epoch)).encode(),max_result_bytes=1000)
            return context.with_lio_timeline_projection(framed)
        before,fence=snapshot()
        with patch.object(MessageTransaction,'lock_scope',counted):
            self.assertEqual(json.loads(boundary.with_history_context(token,project)),dict(memory_epoch=native_epoch))
        self.assertEqual(locks,[scope]);self.assertEqual(snapshot(),(before,[]))
        with self.assertRaisesRegex(RuntimeError,'projection frame required'):
            boundary.with_history_context(token,lambda context:reader.project(context,observed[0],lambda epoch:b'{}',max_result_bytes=1000))
        def wrong_run(context):
            old=observed[0]
            wrong=Binding(old.scope,old.conversation_id,old.generation,old.message_id,'wrong-run',old.message_sequence)
            return context.with_lio_timeline_projection(lambda:reader.project(context,wrong,lambda epoch:b'{}',max_result_bytes=1000))
        with self.assertRaises(RuntimeDenied):boundary.with_history_context(token,wrong_run)
        for payload,limit in (('not materialized',1000),(b'oversize',1)):
            def invalid_projection(context):
                return context.with_lio_timeline_projection(lambda:reader.project(context,observed[0],
                    lambda epoch:payload,max_result_bytes=limit))
            with self.assertRaises(RuntimeDenied):boundary.with_history_context(token,invalid_projection)
        # A live API policy can expire while the complete profile is encoded.
        # The final check must withhold those bytes, without a worker selection.
        from datetime import datetime,timezone
        with patch('cj_memory.epoch_projection.datetime') as clock:
            clock.now.return_value=datetime.now(timezone.utc)
            def expire_after_encode(context):
                def encoded(epoch):
                    clock.now.return_value=configuration.collection.collection.profiles[identity].expires_at
                    return b'{"private":"must be withheld"}'
                return context.with_lio_timeline_projection(lambda:reader.project(context,observed[0],encoded,max_result_bytes=1000))
            with self.assertRaises(RuntimeDenied):boundary.with_history_context(token,expire_after_encode)
        self.assertEqual(snapshot(),(before,[]))
        invited=auth/'invited.json';original=invited.read_bytes()
        try:
            from cj_message.auth_boundary import AccessBlocked,IdentityChanged
            def revoke_after_encode(context):
                def encoded(epoch):
                    invited.write_text('[]')
                    return b'{"private":"must be withheld"}'
                return context.with_lio_timeline_projection(lambda:reader.project(context,observed[0],encoded,max_result_bytes=1000))
            with self.assertRaises((AccessBlocked,IdentityChanged,RuntimeDenied)):
                boundary.with_history_context(token,revoke_after_encode)
            invited.write_text('[]')
            with self.assertRaises((RuntimeDenied,Unavailable)):
                with captured.hold(binding):pass
        finally:invited.write_bytes(original)

    def test_readonly_binding_wrong_owner_authority_and_fresh_admission_refused(self):
        from cj_memory.runtime import RuntimeDenied
        configuration,_=self.runtime_configuration();database=LocalDatabase(CONNINFO,run_context=self.run_context,travel_context=True)
        bob=scope_for(ISSUER,'bob');token=self.headers('bob')['Authorization'].removeprefix('Bearer ')
        def other():
            decision=self.checker.check(token);self.assertIs(decision.status,AdmissionStatus.ALLOWED)
            return decision.principal
        alice_authority=MessageContextAuthority(database.message_repository(self.scope),self.admit)
        bob_authority=MessageContextAuthority(database.message_repository(bob),other)
        before=self.memory_snapshot(self.scope)
        with self.readonly_connections(database) as opened:
            with self.assertRaisesRegex(RuntimeDenied,'principal/owner mismatch'):
                configuration.bind_readonly(database,self.scope,'bob',other,message_context=alice_authority)
            for wrong in (bob_authority,object()):
                with self.assertRaisesRegex(RuntimeDenied,'canonical original context authority'):
                    configuration.bind_readonly(database,self.scope,'alice',self.admit,message_context=wrong)
            self.assertEqual(opened,[])
            import dev_auth as local_auth
            expired=local_auth.token(self.auth,'alice',-1)
            def denied():
                self.assertIs(self.checker.check(expired).status,AdmissionStatus.DENIED)
                raise RuntimeDenied('actual admission denied')
            with self.assertRaisesRegex(RuntimeDenied,'actual admission denied'):
                configuration.bind_readonly(database,self.scope,'alice',denied,message_context=alice_authority)
            self.assertEqual(opened,[])
            state=[self.token]
            def current():
                decision=self.checker.check(state[0]);self.assertIs(decision.status,AdmissionStatus.ALLOWED)
                return decision.principal
            bound=configuration.bind_readonly(database,self.scope,'alice',current,message_context=alice_authority)
            state[0]=token
            with self.assertRaisesRegex(RuntimeDenied,'principal/owner mismatch'):bound.guard('late_check')
        self.assertEqual(self.memory_snapshot(self.scope),before)

    def test_actual_owned_lease_type_isolation_longterm_and_original_bytes(self):
        long=self.raw();saved=self.save(long)
        first=self.raw(self.travel[0],text='仅A / A only');a=self.save(first)
        second=self.raw(self.travel[1],text='仅B / B only');b=self.save(second)
        slot='pace-'+self.tag
        self.assertEqual([i.command.text for i in self.selected(self.travel[0]).items if i.command.slot==slot],['仅A / A only'])
        self.assertEqual([i.command.text for i in self.selected(self.travel[1]).items if i.command.slot==slot],['仅B / B only'])
        self.assertEqual(self.save(first),a)
        with self.assertRaises(Conflict):self.save(first+b' ')
        self.assertEqual(saved['input_sha256'],hashlib.sha256(long).hexdigest())
        self.assertEqual(self.service.detail(saved['item_id']).command.text,'长期 / long term')
        # Same opaque string may also be a legacy conversation. It is not travel.
        original=dict(operation_id='legacy-'+self.tag,item_id='legacy-item-'+self.tag,subject='self',slot=slot,
            kind='preference',text='Legacy only',extent='current',context_id=self.travel[0]['id'],
            source_id='legacy-source-'+self.tag,source_version=1,occurred_at='date unknown')
        command=Command.parse(json.dumps(original,separators=(',',':')).encode())
        with self.service.repository.transaction() as tx:
            tx.lock_scope();tx.create_manual_source(command,True,self.service.manual_policy.expires_at);tx.insert(command,'active')
        legacy=self.service.effective('self',ContextRef('legacy',self.travel[0]['id']))
        self.assertEqual([i.command.text for i in legacy.items if i.command.slot==slot],['Legacy only'])
        self.assertEqual([i.command.text for i in self.selected(self.travel[0]).items if i.command.slot==slot],['仅A / A only'])
        # An explicit legacy-only decoder fails closed on new stored bytes.
        old=Service(Repository(lambda:self.database.connect(self.scope),self.scope,
            transaction_binder=lambda conn,cur:conn.bind_scope(cur)))
        from cj_memory.domain import InvalidInput
        with self.assertRaises(InvalidInput):old.detail(a['item_id'])

    def test_wrong_owner_current_version_and_lease_scope_rejected(self):
        self.save(self.raw())
        from cj_run.core import Denied
        from cj_memory.operation import OperationWithheld
        wrong=dict(self.travel[0],version=2)
        with self.assertRaises((Denied,OperationWithheld)):self.save(self.raw(wrong))
        bob=scope_for(ISSUER,'bob');token=self.headers('bob')['Authorization'].removeprefix('Bearer ')
        other=MessageContextAuthority(self.database.message_repository(bob),lambda:self.checker.check(token).principal)
        with self.assertRaises((Unavailable,OperationWithheld)):self.save(self.raw(self.travel[0]),other)
        with self.database.connect(bob) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(self.scope,)).fetchone()[0],0)


    def typed_configuration(self):
        from copy import deepcopy
        from cj_memory.typed_api import create_local_typed_app
        from cj_memory.typed_local import TypedConfiguration
        profile=dict(subjects=['self'],slots={'pace-'+self.tag:dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
                     extents=['long_term','current'],context_ids=[])
        value=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
            expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            profiles={'alice':profile,'bob':deepcopy(profile)}),travel_contexts={'alice':[x['id'] for x in self.travel],'bob':[]})
        config=TypedConfiguration.from_bytes(json.dumps(value).encode())
        return config

    def typed_app(self):
        from cj_memory.typed_api import create_local_typed_app
        return create_local_typed_app(conninfo_path=CONNINFO,auth_dir=self.auth,configuration=self.typed_configuration())

    def test_actual_typed_api_receipt_projection_reopen_and_foreign_scope(self):
        raw=self.raw(self.travel[0],text='API typed / 本次旅行')
        with TestClient(self.typed_app()) as client:
            headers={**self.headers('alice'),'Content-Type':'application/octet-stream'}
            saved=client.post('/v2/memories',content=raw,headers=headers)
            self.assertEqual(saved.status_code,200,saved.text)
            receipt=saved.json()['receipt']
            self.assertEqual(receipt['input_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(client.post('/v2/memories',content=raw,headers=headers).json()['receipt'],receipt)
            item=client.get('/v2/memory-items',params={'item_id':receipt['item_id']},headers=self.headers('alice'))
            self.assertEqual(item.status_code,200,item.text)
            self.assertEqual(item.json()['item']['command']['context'],dict(kind='travel',id=self.travel[0]['id'],expected_version=1))
            self.assertIsNone(client.get('/v2/memory-items',params={'item_id':receipt['item_id']},headers=self.headers('bob')).json()['item'])
            listing=client.get('/v2/memories',params={'limit':'100'},headers=self.headers('alice'))
            self.assertEqual(listing.status_code,200,listing.text)
            self.assertIn(receipt['item_id'],[i['command']['item_id'] for i in listing.json()['items']])
            bad=json.loads(raw);bad['owner']='bob'
            self.assertEqual(client.post('/v2/memories',content=json.dumps(bad).encode(),headers=headers).status_code,400)
        with TestClient(self.typed_app()) as client:
            read=client.get('/v2/memory-receipts',params={'operation_id':json.loads(raw)['operation_id']},headers=self.headers('alice'))
            self.assertEqual(read.status_code,200,read.text);self.assertEqual(read.json()['receipt'],receipt)


    def injected_typed_app(self,database,configuration=None):
        from cj_api.local_app import create_local_app
        from cj_memory.typed_api import register_typed_routes
        app=create_local_app(conninfo_path=None,auth_dir=self.auth,database=database,
                             run_context=self.run_context,travel_context=True)
        register_typed_routes(app,database=database,auth_dir=self.auth,
                              configuration=configuration or self.typed_configuration())
        return app

    def test_injected_typed_cohost_original_receipts_owner_and_withdrawal(self):
        raw=self.raw(self.travel[0],text='Injected 本次旅行')
        command=json.loads(raw)
        with TestClient(self.injected_typed_app(self.database)) as client:
            headers={**self.headers('alice'),'Content-Type':'application/octet-stream'}
            self.assertEqual(client.post('/v2/memories',content=raw,
                headers={'Content-Type':'application/octet-stream'}).status_code,401)
            import dev_auth as local_auth
            for token in ('invalid-signature',local_auth.token(self.auth,'alice',-1)):
                denied=client.post('/v2/memories',content=raw,
                    headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'})
                self.assertEqual(denied.status_code,401,denied.text)
            opened=client.put('/v1/conversations',params={'conversation_id':'injected-'+self.tag},headers=headers)
            self.assertEqual(opened.status_code,200,opened.text)
            saved=client.post('/v2/memories',content=raw,headers=headers)
            self.assertEqual(saved.status_code,200,saved.text);receipt=saved.json()['receipt']
            self.assertEqual(receipt['input_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(client.post('/v2/memories',content=raw,headers=headers).json()['receipt'],receipt)
            self.assertIsNone(client.get('/v2/memory-items',params={'item_id':command['item_id']},
                headers=self.headers('bob')).json()['item'])
            action=dict(version='MEMORY-management.2',action_id='pause-'+self.tag,operation='pause',
                item_id=command['item_id'],expected_version=1,expected_source_version=1)
            foreign=client.post('/v2/memory-management-actions',content=json.dumps(action).encode(),
                headers={**self.headers('bob'),'Content-Type':'application/octet-stream'})
            self.assertNotEqual(foreign.status_code,200)
            paused=client.post('/v2/memory-management-actions',content=json.dumps(action).encode(),headers=headers)
            self.assertEqual(paused.status_code,200,paused.text)
            query=client.get('/v2/memory-management-receipts',params={'action_id':action['action_id']},headers=headers)
            self.assertEqual(query.json()['receipt'],paused.json()['receipt'])
            item=client.get('/v2/memory-items',params={'item_id':command['item_id']},headers=headers).json()['item']
            self.assertEqual((item['version'],item['status']),(2,'disabled'))
            stop=dict(version='MEMORY-STOP-USE@2',action_id='withdraw-'+self.tag,operation='withdraw',
                item_id=command['item_id'],expected_version=2,source_id=item['command']['source_id'],expected_source_version=1)
            withdrawn=client.post('/v2/memory-withdrawal-actions',content=json.dumps(stop).encode(),headers=headers)
            self.assertEqual(withdrawn.status_code,200,withdrawn.text)
            self.assertEqual(withdrawn.json()['receipt']['status'],'withdrawn')
            self.assertNotIn(command['item_id'],[i.command.item_id for i in self.selected(self.travel[0]).items])
            listing=client.get('/v2/memories',params={'limit':'100'},headers=headers)
            self.assertEqual(listing.status_code,200,listing.text)
            self.assertEqual([i['status'] for i in listing.json()['items'] if i['command']['item_id']==command['item_id']],['withdrawn'])
        with TestClient(self.injected_typed_app(self.database)) as client:
            original=client.get('/v2/memory-receipts',params={'operation_id':command['operation_id']},headers=self.headers('alice'))
            self.assertEqual(original.status_code,200,original.text)
            self.assertEqual(original.json()['receipt'],receipt)

    def test_injected_database_transaction_guard_blocks_real_storage(self):
        from cj_api.composition import CompositionUnavailable
        from unittest.mock import patch
        database=LocalDatabase(CONNINFO,run_context=self.run_context,travel_context=True)
        state=dict(denied=False,checks=0)
        def guard(cursor):
            self.assertEqual(cursor.execute('SELECT current_user').fetchone()[0],'cj_m1_runtime')
            state['checks']+=1
            if state['denied']:raise CompositionUnavailable('test release guard closed')
        raw=self.raw(self.travel[0]);command=json.loads(raw)
        with patch.object(database,'_before_scope',guard),TestClient(self.injected_typed_app(database)) as client:
            headers={**self.headers('alice'),'Content-Type':'application/octet-stream'}
            state['denied']=True
            denied=client.post('/v2/memories',content=raw,headers=headers)
            self.assertEqual(denied.status_code,503,denied.text)
            self.assertGreater(state['checks'],0)
            with self.database.connect(self.scope) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_operation WHERE operation_id=%s',
                    (command['operation_id'],)).fetchone()[0],0)
            state['denied']=False
            saved=client.post('/v2/memories',content=raw,headers=headers)
            self.assertEqual(saved.status_code,200,saved.text)
            before=state['checks'];state['denied']=True
            denied=client.get('/v2/memory-items',params={'item_id':command['item_id']},headers=headers)
            self.assertEqual(denied.status_code,503,denied.text)
            self.assertGreater(state['checks'],before)
        with self.database.connect(self.scope) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_operation WHERE operation_id=%s',
                (command['operation_id'],)).fetchone()[0],1)


    def test_typed_edit_pause_resume_stop_and_new_context_version(self):
        with TestClient(self.typed_app()) as client,TestClient(self.app) as identity:
            headers={**self.headers('alice'),'Content-Type':'application/octet-stream'}
            raw=self.raw(self.travel[0],text='Old typed / 原值')
            result=client.post('/v2/memories',content=raw,headers=headers)
            self.assertEqual(result.status_code,200,result.text);iid=result.json()['receipt']['item_id']
            def action(op,version,context=None,text=None):
                value=dict(version='MEMORY-management.2',action_id='action-'+uuid.uuid4().hex,
                    operation=op,item_id=iid,expected_version=version,expected_source_version=1)
                if op=='edit':value.update(context=context,text=text)
                return json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
            def post(body):return client.post('/v2/memory-management-actions',content=body,headers=headers)
            pause=post(action('pause',1));self.assertEqual(pause.status_code,200,pause.text)
            original_context=dict(kind='travel',id=self.travel[0]['id'],expected_version=1)
            edit=action('edit',2,original_context,'New typed / 新值')
            changed=post(edit);self.assertEqual(changed.status_code,200,changed.text)
            self.assertEqual((changed.json()['receipt']['status'],changed.json()['receipt']['version']),('disabled',3))
            self.assertEqual(post(action('resume',3)).status_code,200)
            invalid=dict(kind='travel',id='invalid',expected_version=1)
            self.assertEqual(post(action('edit',4,invalid,'invalid syntax')).status_code,400)

            request=dict(version='TRAVEL-context-action.1',action_id='advance-'+self.tag,operation='advance',
                travel_context=dict(id=self.travel[0]['id'],expected_version=1))
            advanced=identity.post('/v1/travel-context-actions',content=json.dumps(request).encode(),headers=headers)
            self.assertEqual(advanced.status_code,200,advanced.text)
            self.assertNotEqual(post(action('edit',4,original_context,'stale context')).status_code,200)
            current_context=dict(original_context,expected_version=2)
            updated=post(action('edit',4,current_context,'Current version / 新旅行版本'))
            self.assertEqual(updated.status_code,200,updated.text)
            self.assertEqual(post(edit).json()['receipt'],changed.json()['receipt'])
            current=client.get('/v2/memory-items',params={'item_id':iid},headers=self.headers('alice')).json()['item']
            self.assertEqual(current['version'],5);self.assertEqual(current['command']['context'],current_context)
            wrong=dict(kind='travel',id=self.travel[1]['id'],expected_version=1)
            self.assertEqual(post(action('edit',5,wrong,'retarget')).status_code,409)
            stop=dict(version='MEMORY-STOP-USE@2',action_id='stop-'+self.tag,operation='withdraw',item_id=iid,
                      expected_version=5,source_id=current['command']['source_id'],expected_source_version=1)
            stopped=client.post('/v2/memory-withdrawal-actions',content=json.dumps(stop).encode(),headers=headers)
            self.assertEqual(stopped.status_code,200,stopped.text)
            self.assertEqual((stopped.json()['receipt']['status'],stopped.json()['receipt']['version']),('withdrawn',6))
            self.assertNotEqual(post(action('resume',6)).status_code,200)
            with self.database.connect(self.scope) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_source WHERE source_id IN (SELECT previous_source_id FROM cj_memory_management_action WHERE item_id=%s) AND active',(iid,)).fetchone()[0],0)


    def runtime_configuration(self):
        from cj_memory.typed_runtime import TypedRuntimeConfiguration
        # Serialize the operator document explicitly; never fabricate Context or lease.
        from copy import deepcopy
        profile=dict(subjects=['self'],slots={'pace-'+self.tag:dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
                     extents=['long_term','current'],context_ids=[])
        collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
            expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={'alice':profile,'bob':deepcopy(profile)}),
            travel_contexts={'alice':[x['id'] for x in self.travel],'bob':[]})
        value=dict(version='local-memory-run.2',collection=collection,selections={identity:dict(subject='self',
            slots=['pace-'+self.tag],max_bytes=32768) for identity in ('alice','bob')})
        return TypedRuntimeConfiguration.from_bytes(json.dumps(value).encode()),value

    def send_v2(self,client,conversation,selected,text='Current explicit request'):
        head=client.put('/v1/conversations',params={'conversation_id':conversation},headers=self.headers('alice'))
        self.assertEqual(head.status_code,200,head.text);head=head.json()['head'] if 'head' in head.json() else head.json()
        # Root PUT currently returns the head object directly (request_id aside).
        if 'generation' not in head:
            status=client.get('/v2/message-send-status',params={'conversation_id':conversation},headers=self.headers('alice'))
            self.assertEqual(status.status_code,200,status.text);head=status.json()['head']
        mid='message-'+uuid.uuid4().hex
        raw=json.dumps(dict(version='MESSAGE-send.2',conversation_id=conversation,message_id=mid,text=text,trip_id=None,
            creation_intent='none',expected_generation=head['generation'],expected_sequence=head['last_sequence'],
            travel_context=None if selected is None else dict(id=selected['id'],expected_version=selected['version']),
            needs_reference=None),ensure_ascii=False).encode()
        result=client.post('/v2/messages',content=raw,headers={**self.headers('alice'),'Content-Type':'application/octet-stream'})
        self.assertEqual(result.status_code,200,result.text)
        return mid,result.json()

    def test_actual_worker_same_conversation_other_travel_none_and_process(self):
        from cj_agent.provider import FakeProvider
        import run_worker
        configuration,document=self.runtime_configuration()
        with TestClient(self.typed_app()) as api,TestClient(self.app) as messages:
            for context,text in ((None,'Long-term 原长期'),(self.travel[0],'Only A 仅A'),(self.travel[1],'Only B 仅B')):
                result=api.post('/v2/memories',content=self.raw(context,text=text),
                    headers={**self.headers('alice'),'Content-Type':'application/octet-stream'})
                self.assertEqual(result.status_code,200,result.text)
            class Observed(FakeProvider):
                def __init__(model):super().__init__();model.inputs=[]
                def stream(model,inputs,system=None):
                    model.inputs.append(inputs);yield from super().stream(inputs,system)
            for chat,travel,expected in ((self.tag,self.travel[0],'Only A 仅A'),(self.tag,self.travel[1],'Only B 仅B'),
                                         ('other-'+self.tag,self.travel[0],'Only A 仅A'),(self.tag,None,'Long-term 原长期')):
                mid,_=self.send_v2(messages,chat,travel)
                model=Observed();outcomes=run_worker.run_once(self.database,model,self.auth,memory_configuration=configuration)
                self.assertEqual([o.status for o in outcomes if o.message_id==mid],['completed'])
                data=json.loads(model.inputs[0][0]['content'].split('\n',1)[1])
                self.assertEqual(data['version'],'MEMORY-RUN-CONSUME@2')
                self.assertEqual([i['text'] for i in data['items']],[expected])
            mid,_=self.send_v2(messages,'process-'+self.tag,self.travel[0])
            path=self.auth/('typed-runtime-'+self.tag+'.json');path.write_text(json.dumps(document));path.chmod(0o600)
            import subprocess
            result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/run_worker.py'),'--conninfo-json',CONNINFO,
                '--auth-dir',str(self.auth),'--run-context',str(self.run_path),'--travel-context','message-travel.1',
                '--memory-run-policy',str(path),'--once'],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('completed',result.stdout)
            legacy=messages.get('/v1/run-events',params={'message_id':mid},headers=self.headers('alice'))
            self.assertEqual(legacy.status_code,503)  # Old read must not strip the new reference.
            status=messages.get('/v3/run-draft-status',params={'message_id':mid},headers=self.headers('alice'))
            self.assertEqual(status.status_code,200,status.text)
            self.assertEqual(status.json()['run_status'],'completed')
            self.assertEqual(status.json()['reference']['context_id'],self.travel[0]['id'])

    def test_actual_worker_aba_and_old_runtime_configuration_refused(self):
        from cj_agent.provider import FakeProvider
        from cj_memory.runtime import RuntimeDenied
        import run_worker
        configuration,_=self.runtime_configuration()
        with TestClient(self.typed_app()) as api,TestClient(self.app) as messages:
            result=api.post('/v2/memories',content=self.raw(self.travel[0],text='A only'),
                headers={**self.headers('alice'),'Content-Type':'application/octet-stream'})
            self.assertEqual(result.status_code,200,result.text)
            a,_=self.send_v2(messages,self.tag,self.travel[0]);b,_=self.send_v2(messages,self.tag,self.travel[1]);again,_=self.send_v2(messages,self.tag,self.travel[0])
            model=FakeProvider();outcomes=run_worker.run_once(self.database,model,self.auth,memory_configuration=configuration)
            states={o.message_id:o.status for o in outcomes}
            self.assertEqual((states[a],states[b],states[again]),('context_invalid','context_invalid','completed'))
            self.assertEqual(model.calls,1)
            pending,_=self.send_v2(messages,'missing-'+self.tag,self.travel[0])
            denied=FakeProvider()
            with self.assertRaises(RuntimeDenied):run_worker.run_once(self.database,denied,self.auth)
            self.assertEqual(denied.calls,0)
            configured=FakeProvider()
            resumed=run_worker.run_once(self.database,configured,self.auth,memory_configuration=configuration)
            self.assertEqual([o.status for o in resumed if o.message_id==pending],['completed'])
            self.assertEqual(configured.calls,1)  # Original queued run; no prior dispatch or replacement ID.


    def test_typed_rollback_lost_ack_rebuild_and_nonempty_down(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        from cj_memory.domain import CommitUnknown,Unavailable
        import psycopg,migrate
        transaction=Repository.transaction
        with TestClient(self.typed_app()) as api:
            headers={**self.headers('alice'),'Content-Type':'application/octet-stream'}
            rollback=self.raw(self.travel[0],text='Rollback 原值不得出现')
            def wrapped(fail_after_commit,target):
                @contextmanager
                def use(repository):
                    changed=False
                    with transaction(repository) as tx:
                        yield tx
                        changed=tx.operation(json.loads(target)['operation_id']) is not None
                        if changed and not fail_after_commit:raise Unavailable('fixture rollback before real commit')
                    if changed and fail_after_commit:raise CommitUnknown('fixture lost actual commit ACK')
                return use
            with patch.object(Repository,'transaction',wrapped(False,rollback)):
                failed=api.post('/v2/memories',content=rollback,headers=headers)
            self.assertNotEqual(failed.status_code,200)
            found=api.get('/v2/memory-receipts',params={'operation_id':json.loads(rollback)['operation_id']},headers=self.headers('alice'))
            self.assertIsNone(found.json()['receipt'])
            lost=self.raw(self.travel[0],text='Independent lost ACK / 新原动作')
            with patch.object(Repository,'transaction',wrapped(True,lost)):
                unknown=api.post('/v2/memories',content=lost,headers=headers)
            self.assertEqual(unknown.status_code,503);self.assertEqual(unknown.json()['error']['recovery'],'reconcile_original')
            found=api.get('/v2/memory-receipts',params={'operation_id':json.loads(lost)['operation_id']},headers=self.headers('alice'))
            self.assertEqual(found.status_code,200,found.text)
            self.assertEqual(found.json()['receipt']['input_sha256'],hashlib.sha256(lost).hexdigest())
            config=json.loads(Path(CONNINFO).read_text())
            with psycopg.connect(**config,autocommit=True) as conn:
                chain=migrate.load();typed=next(m for m in chain if m['name']=='memory_typed_context')
                applied_before=migrate.applied(conn)
                self.assertIn(typed['version'],applied_before)
                with self.assertRaises(psycopg.errors.RaiseException):
                    with conn.transaction():conn.execute((ROOT/typed['down']).read_text())
                self.assertEqual(migrate.applied(conn),applied_before)
        with TestClient(self.typed_app()) as api:
            self.assertEqual(api.get('/v2/memory-receipts',params={'operation_id':json.loads(lost)['operation_id']},
                headers=self.headers('alice')).json()['receipt'],found.json()['receipt'])

    def test_actual_worker_rejects_typed_edit_after_capture(self):
        from cj_agent.provider import FakeProvider
        import run_worker
        configuration,_=self.runtime_configuration()
        with TestClient(self.typed_app()) as api,TestClient(self.app) as messages:
            headers={**self.headers('alice'),'Content-Type':'application/octet-stream'}
            saved=api.post('/v2/memories',content=self.raw(self.travel[0],text='Captured old typed value'),headers=headers)
            self.assertEqual(saved.status_code,200,saved.text);iid=saved.json()['receipt']['item_id']
            mid,_=self.send_v2(messages,self.tag,self.travel[0])
            def edit():
                value=dict(version='MEMORY-management.2',action_id='edit-'+self.tag,operation='edit',item_id=iid,
                    expected_version=1,expected_source_version=1,text='Current new typed value',
                    context=dict(kind='travel',id=self.travel[0]['id'],expected_version=1))
                response=api.post('/v2/memory-management-actions',content=json.dumps(value).encode(),headers=headers)
                self.assertEqual(response.status_code,200,response.text)
            class Changed(FakeProvider):
                def stream(model,inputs,system=None):
                    for index,chunk in enumerate(super().stream(inputs,system)):
                        yield chunk
                        if index==0:edit()
            model=Changed();outcomes=run_worker.run_once(self.database,model,self.auth,memory_configuration=configuration)
            self.assertEqual([o.status for o in outcomes if o.message_id==mid],['context_invalid'])
            self.assertEqual(model.calls,1)
            status=messages.get('/v3/run-draft-status',params={'message_id':mid},headers=self.headers('alice'))
            self.assertEqual(status.status_code,200,status.text);self.assertEqual(status.json()['run_status'],'context_invalid')

    def test_runtime_role_wrong_owner_typed_fk_and_immutable_context_kind(self):
        import psycopg
        from cj_memory.typed import parse_manual
        bob=scope_for(ISSUER,'bob')
        with self.database.connect(bob) as conn:
            conn.execute('INSERT INTO cj_memory_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',(bob,))
        command=parse_manual(self.raw(self.travel[0]))
        other=Repository(lambda:self.database.connect(bob),bob,
            transaction_binder=lambda conn,cur:conn.bind_scope(cur),typed_context=True)
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            with other.transaction() as tx:
                tx.lock_scope();tx.create_manual_source(command,True,self.service.manual_policy.expires_at);tx.insert(command,'active')
        with self.database.connect(bob) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_source WHERE source_id=%s',(command.source_id,)).fetchone()[0],0)
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.database.connect(self.scope) as conn:conn.execute("UPDATE cj_memory_item SET context_kind='travel'")


    def test_actual_typed_memory_and_registered_place_tool_loop(self):
        from cj_api.local_tools import LocalTools,SyntheticToolModel
        from cj_run.step_usage import ledger_scope_for
        from cj_usage.codec import decode
        from cj_usage.core import Meter
        import run_worker
        configuration,_=self.runtime_configuration()
        def exposure():
            with self.database.connect(self.scope) as conn:
                row=conn.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',
                    (ledger_scope_for(self.scope,self.run_context.current.meter),)).fetchone()
                return Meter.exposure(decode(row[0]))
        with TestClient(self.typed_app()) as api,TestClient(self.app) as messages:
            result=api.post('/v2/memories',content=self.raw(self.travel[0],text='Travel A slow pace / 慢节奏'),
                headers={**self.headers('alice'),'Content-Type':'application/octet-stream'})
            self.assertEqual(result.status_code,200,result.text)
            mid,_=self.send_v2(messages,self.tag,self.travel[0],text='查询合成酒店 / Find synthetic hotel')
            class Observed(SyntheticToolModel):
                def __init__(model):super().__init__();model.inputs=[]
                def stream(model,inputs,system=None):
                    model.inputs.append(inputs);yield from super().stream(inputs,system)
            tools=LocalTools();model=Observed();before=exposure()
            outcomes=run_worker.run_once(self.database,model,self.auth,memory_configuration=configuration,tools_configuration=tools)
            status=messages.get('/v3/run-draft-status',params={'message_id':mid},headers=self.headers('alice'))
            self.assertEqual([o.status for o in outcomes if o.message_id==mid],['completed'],status.text)
            self.assertEqual((model.calls,tools.place.invocations,tools.place.transport_calls),(2,1,1))
            self.assertEqual(exposure(),before+3)
            for inputs in model.inputs:
                memory=json.loads(inputs[0]['content'].split('\n',1)[1])
                self.assertEqual([item['text'] for item in memory['items']],['Travel A slow pace / 慢节奏'])
            display=messages.get('/v2/run-display',params={'message_id':mid},headers=self.headers('alice'))
            self.assertEqual(display.status_code,200,display.text)
            frames=[json.loads(line) for line in display.json()['snapshot']['text'].splitlines()]
            self.assertEqual([f['version'] for f in frames],['TOOL-output.1','TOOL-answer.1'])
            self.assertEqual(display.json()['reference']['context_id'],self.travel[0]['id'])
            self.assertTrue(all(frame['data_origin']=='synthetic' for frame in frames))


if __name__=='__main__':unittest.main(verbosity=2)
