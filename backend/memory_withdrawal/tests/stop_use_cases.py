"""Real C stop-use writer and canonical capture; signed local AUTH, runtime PG."""
import json
import time
import uuid
from contextlib import contextmanager
from unittest.mock import patch
from fastapi.testclient import TestClient

from cj_api.local_app import ISSUER, AUDIENCE, KEY_ID, scope_for, InvitedSubjects
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import AdmissionStatus
from cj_auth.jwt_adapter import JWTConfiguration, StaticPublicKeys, VerificationKey, PyJWTVerifier
from cj_memory.domain import Conflict, Unavailable, CommitUnknown
from cj_memory.postgres import Repository
from cj_memory_management.guarded import GuardedService
from cj_memory_withdrawal.stop_use import StopUse
from cj_memory.runtime import RuntimeDenied


class StopUseCases:
    def stop_action(self, item):
        return json.dumps(dict(version='MEMORY-STOP-USE@1',action_id='stop-'+uuid.uuid4().hex,
            operation='withdraw',item_id=item.command.item_id,expected_version=item.version,
            source_id=item.command.source_id,expected_source_version=item.command.source_version),
            separators=(',',':')).encode()

    def guarded_management(self, identity='alice'):
        # Same real strict checker and original guarded domain producer as the host;
        # no callback manufactures AUTH, source history, Context or permission.
        token=self.headers(identity)['Authorization'].removeprefix('Bearer ')
        checker=AdmissionChecker(PyJWTVerifier(JWTConfiguration(ISSUER,AUDIENCE,'RS256',0),
            StaticPublicKeys({KEY_ID:VerificationKey('RS256',(self.auth/'public.pem').read_bytes())})),
            InvitedSubjects(self.auth/'invited.json'))
        scope=scope_for(ISSUER,identity)
        repository=Repository(lambda:self.database.connect(scope),scope,
            transaction_binder=lambda conn,cur:conn.bind_scope(cur))
        from cj_memory.local import LocalMemoryConfiguration
        policy=LocalMemoryConfiguration.from_bytes(json.dumps(self.policy).encode()).profiles[identity].manual_policy()
        service=GuardedService(repository,manual_policy=policy)
        def guard(stage):
            decision=checker.check(token)
            if decision.status is not AdmissionStatus.ALLOWED:
                raise Unavailable('fresh admission denied or unknown')
            return decision.principal,scope
        return service,guard

    def stop(self,raw,identity='alice'):
        service,guard=self.guarded_management(identity)
        def operation(context):
            result=context.apply(raw)
            return json.dumps(dict(action_id=result.operation_id,item_id=result.item_id,
                version=result.version,status=result.status,input_sha256=result.input_sha256)).encode()
        return json.loads(service.with_operation(guard,operation))

    def stopped_receipt(self,raw,identity='alice'):
        service,guard=self.guarded_management(identity)
        def operation(context):
            value=context.query(json.loads(raw)['action_id'])
            return json.dumps(None if value is None else dict(version=value.version,status=value.status)).encode()
        return json.loads(service.with_operation(guard,operation))

    def test_stop_use_complete_edit_history_preserved_and_no_resurrection(self):
        with TestClient(self.memory_app) as api,TestClient(self.manager) as manager:
            original=self.raw();self.assertEqual(self.save(api,original).status_code,200)
            iid=json.loads(original)['item_id'];source_ids=[self.service().detail(iid).command.source_id]
            for version in (1,2):
                self.assertEqual(self.apply(manager,self.action(original,version=version,text='edit '+str(version))).status_code,200)
                source_ids.append(self.service().detail(iid).command.source_id)
            others=tuple(i for i in self.service().effective('self').items if i.command.item_id!=iid)
            raw=self.stop_action(self.service().detail(iid));receipt=self.stop(raw)
            self.assertEqual((receipt['status'],receipt['version']),('withdrawn',4))
            self.assertEqual(self.stop(raw),receipt)
            self.assertEqual(self.stopped_receipt(raw),dict(version=4,status='withdrawn'))
            current,guard=self.guarded_management()
            legacy=GuardedService(current.repository)
            with self.assertRaises(Unavailable):
                legacy.with_operation(guard,lambda context:json.dumps(context.query(json.loads(raw)['action_id'])).encode())
            self.assertIsNone(self.stopped_receipt(raw,'bob'))
            with self.assertRaises(Conflict):self.stop(raw+b' ')
            self.assertEqual(self.service().effective('self').items,others)
            with self.database.connect(scope_for(ISSUER,'alice')) as conn:
                rows=conn.execute('SELECT source_id,active FROM cj_memory_source WHERE source_id=ANY(%s)',(source_ids,)).fetchall()
                self.assertEqual(dict(rows),dict.fromkeys(source_ids,False))
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_operation WHERE item_id=%s',(iid,)).fetchone()[0],1)
            for op in ('edit','resume'):
                self.assertNotEqual(self.apply(manager,self.action(original,op,version=4)).status_code,200)
            self.assertEqual(self.receipt(api,original).json()['receipt']['version'],1)
            # Another canonical slot remains usable; withdrawal never clears owner.
            other=self.raw('fact');self.assertEqual(self.save(api,other).status_code,200)
            self.assertEqual(len(self.service().effective('self').items),len(others)+1)

    def test_stop_use_shared_source_and_wrong_owner_fail_without_mutation(self):
        with TestClient(self.memory_app) as api:
            original=self.raw();self.assertEqual(self.save(api,original).status_code,200)
            item=self.service().detail(json.loads(original)['item_id']);raw=self.stop_action(item)
            with self.assertRaises(Unavailable):self.stop(raw,'bob')
            scope=scope_for(ISSUER,'alice')
            with self.database.connect(scope) as conn:
                # Restricted runtime creates an explicit preexisting shared-source
                # fixture; the authoritative reverse-reference scan must refuse.
                conn.execute('''INSERT INTO cj_memory_item
                    (scope,item_id,version,status,subject,slot,extent,context_id,source_id,source_version,original_input)
                    VALUES (%s,%s,1,'disabled','self','shared','long_term','',%s,1,%s)''',
                    (scope,'shared-'+self.tag,item.command.source_id,item.command.raw))
            with self.assertRaises(Unavailable):self.stop(raw)
            self.assertEqual(self.service().detail(item.command.item_id),item)
            self.assertIsNone(self.stopped_receipt(raw))

    def test_stop_use_rollback_unknown_and_original_reconciliation(self):
        from cj_memory.operation import OperationWithheld
        transaction=Repository.transaction
        with TestClient(self.memory_app) as api:
            original=self.raw();self.assertEqual(self.save(api,original).status_code,200)
            item=self.service().detail(json.loads(original)['item_id']);raw=self.stop_action(item)
            @contextmanager
            def rollback(repository):
                with transaction(repository) as tx:
                    yield tx
                    raise Unavailable('fixture before commit')
            with patch.object(Repository,'transaction',rollback),self.assertRaises(OperationWithheld):self.stop(raw)
            self.assertEqual(self.service().detail(item.command.item_id),item)
            self.assertIsNone(self.stopped_receipt(raw))
            @contextmanager
            def unknown(repository):
                with transaction(repository) as tx:yield tx
                raise CommitUnknown('fixture lost ACK after real commit')
            with patch.object(Repository,'transaction',unknown),self.assertRaises(OperationWithheld) as error:self.stop(raw)
            self.assertEqual(error.exception.operation_id,json.loads(raw)['action_id'])
            self.assertTrue(error.exception.commit_possible)
            self.assertEqual(self.stopped_receipt(raw),dict(status='withdrawn',version=2))

    def test_stop_use_nonempty_down_refuses(self):
        import psycopg
        import migrate
        from pathlib import Path
        from e2e_local import CONNINFO
        with TestClient(self.memory_app) as api:
            original=self.raw();self.assertEqual(self.save(api,original).status_code,200)
            raw=self.stop_action(self.service().detail(json.loads(original)['item_id']));self.stop(raw)
            with psycopg.connect(**json.loads(Path(CONNINFO).read_text()),autocommit=True) as conn:
                with self.assertRaises(psycopg.errors.RaiseException):migrate.down(conn,migrate.load(),19)
                self.assertEqual(migrate.applied(conn)[-1],20)
            self.assertEqual(self.stopped_receipt(raw)['status'],'withdrawn')

    def test_lifecycle_changes_stop_actual_inflight_worker(self):
        import runtime_host_pg as runtime
        with TestClient(self.memory_app) as api,TestClient(self.manager) as manager:
            for op in ('edit','pause','resume','withdraw'):
                with self.subTest(operation=op):
                    original=self.raw(text='Captured old 原值 '+op)
                    self.assertEqual(self.save(api,original).status_code,200)
                    iid=json.loads(original)['item_id']
                    if op=='resume':
                        self.assertEqual(self.apply(manager,self.action(original,'pause')).status_code,200)
                    current=self.service().detail(iid)
                    def change():
                        if op=='withdraw':self.stop(self.stop_action(current))
                        else:
                            result=self.apply(manager,self.action(original,op,version=current.version))
                            self.assertEqual(result.status_code,200,result.text)
                    mid,response=self.send(api,'alice','Do not publish an obsolete result',conversation=self.chat_a+'-'+op)
                    self.assertEqual(response.status_code,200,response.text)
                    model=runtime.ObservedProvider(after_first=change)
                    from cj_memory.runtime import RuntimeMemory
                    capture=RuntimeMemory.capture; captured=[]
                    def remember(owner,binding):
                        run=capture(owner,binding);captured.append(run);return run
                    with patch.object(RuntimeMemory,'capture',remember):outcomes=self.execute(model)
                    late_effect=[]
                    with self.assertRaises(RuntimeDenied):
                        with captured[0].hold(captured[0].binding) as check:
                            check();late_effect.append('derived candidate/index publication')
                    self.assertEqual(late_effect,[])  # Same actual PG lease; no CJ020 business claim.
                    self.assertEqual([x.status for x in outcomes if x.message_id==mid],['context_invalid'])
                    self.assertEqual(model.calls,1)
                    self.assertEqual(self.events(api,'alice',mid)[-1][2],{'status':'context_invalid'})
                    # No new proposal or replayed provider attempt follows refusal.
                    if op!='withdraw':self.stop(self.stop_action(self.service().detail(iid)))

    def test_publication_lock_orders_real_stop_use_writer(self):
        from concurrent.futures import ThreadPoolExecutor
        from cj_agent.worker import RunWorker
        from cj_memory.runtime import RuntimeRun
        import runtime_host_pg as runtime
        event,hold=RunWorker._event,RuntimeRun.hold
        state={'kind':None,'used':False,'published':False,'waited':False}
        with TestClient(self.memory_app) as api:
            raw=self.raw(text='Published prefix / 历史片段')
            self.assertEqual(self.save(api,raw).status_code,200)
            action=self.stop_action(self.service().detail(json.loads(raw)['item_id']))
            mid,response=self.send(api,'alice','Publish then stop',conversation=self.chat_a)
            self.assertEqual(response.status_code,200,response.text)
            def marked(worker,binding,old,kind,value=''):
                previous=state['kind'];state.update(kind=kind,worker=worker)
                try:return event(worker,binding,old,kind,value)
                finally:state['kind']=previous
            with ThreadPoolExecutor(max_workers=1) as pool:
                @contextmanager
                def held(run,binding):
                    future=None
                    with hold(run,binding) as check:
                        if state['kind']=='text_delta' and not state['used']:
                            state['used']=True;future=pool.submit(self.stop,action)
                            deadline=time.monotonic()+4
                            while time.monotonic()<deadline:
                                with self.database.connect(binding.scope) as conn:
                                    blocked=conn.execute("SELECT count(*) FROM pg_stat_activity WHERE usename=current_user AND wait_event_type='Lock' AND query LIKE 'SELECT epoch FROM cj_memory_scope%' AND cardinality(pg_blocking_pids(pid))>0").fetchone()[0]
                                if blocked:break
                                time.sleep(.01)
                            self.assertGreater(blocked,0,'actual stop writer must wait on the held MEMORY row')
                            self.assertFalse(future.done());state['waited']=True
                        yield check
                        if future is not None:
                            state['published']=bool(state['worker'].runs.snapshot(binding).text)
                            self.assertTrue(state['published'])
                            self.assertFalse(future.done())
                    if future is not None:
                        self.assertEqual(future.result(timeout=5)['status'],'withdrawn')
                with patch.object(RunWorker,'_event',marked),patch.object(RuntimeRun,'hold',held):
                    outcomes=self.execute(runtime.ObservedProvider())
            self.assertTrue(state['waited'] and state['published'])
            self.assertEqual([x.status for x in outcomes if x.message_id==mid],['context_invalid'])
            events=self.events(api,'alice',mid)
            self.assertTrue(any(x[0]=='delta' for x in events))
            self.assertEqual(events[-1][2],{'status':'context_invalid'})

    def prepare_draft_context(self, api, conversation):
        # Consume the existing approved B local operator, never fabricate a
        # Context/lease or change C memory/source flags with initialization SQL.
        from e2e_local import CONNINFO
        import local_run_context as operator
        self.assertEqual(api.put('/v1/conversations',params={'conversation_id':conversation},
                                 headers=self.headers('alice')).status_code,200)
        needs_id='needs-'+uuid.uuid4().hex
        raw=json.dumps(dict(action_id='needs-action-'+uuid.uuid4().hex,needs_id=needs_id,
            expected_version=0,source={'kind':'manual','text':'explicit local fixture user input'},
            changes={'party_size':{'state':'known','value':1}})).encode()
        operator.put_needs(CONNINFO,self.auth,'alice',raw)
        operator.bind_needs(CONNINFO,'alice',conversation,needs_id)

    def test_draft_lifecycle_first_refuses_actual_proposal(self):
        from cj_agent.provider import FakeProvider
        with TestClient(self.memory_app) as api,TestClient(self.manager) as manager:
            for op in ('edit','pause','resume','withdraw'):
                with self.subTest(operation=op):
                    original=self.raw(text='Before draft '+op)
                    self.assertEqual(self.save(api,original).status_code,200)
                    iid=json.loads(original)['item_id']
                    if op=='resume':self.assertEqual(self.apply(manager,self.action(original,'pause')).status_code,200)
                    current=self.service().detail(iid)
                    def change():
                        if op=='withdraw':self.stop(self.stop_action(current))
                        else:self.assertEqual(self.apply(manager,self.action(original,op,version=current.version)).status_code,200)
                    class DraftChanged(FakeProvider):
                        def stream(model,messages,system=None):
                            yield from super().stream(messages,system)
                            if system is not None:change()
                    self.prepare_draft_context(api,self.chat_a+'-'+op)
                    mid,response=self.send(api,'alice','Beijing draft please',conversation=self.chat_a+'-'+op,intent='consider_trip')
                    self.assertEqual(response.status_code,200,response.text)
                    model=DraftChanged();outcomes=self.execute(model)
                    self.assertEqual([x.status for x in outcomes if x.message_id==mid],['context_invalid'])
                    self.assertEqual(model.calls,2)
                    self.assertIsNone(next(x for x in outcomes if x.message_id==mid).proposal_id)
                    with self.database.connect(scope_for(ISSUER,'alice')) as conn:
                        self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],0)
                    if op!='withdraw':self.stop(self.stop_action(self.service().detail(iid)))

    def test_wall_clock_expiry_during_draft_materialization_refuses_publish(self):
        from datetime import datetime,timedelta,timezone
        from cj_agent.provider import FakeProvider
        import cj_agent.draft as draft
        deadline=datetime.now(timezone.utc)+timedelta(seconds=20)
        self.policy['expires_at']=deadline.isoformat();self.write_policy();self.memory_app=self.app_from_policy()
        materialize=draft.document_from_model
        def expires_inside(text):
            value=materialize(text)
            time.sleep(max(0,deadline.timestamp()-time.time())+.05)
            return value
        with TestClient(self.memory_app) as api:
            original=self.raw();self.assertEqual(self.save(api,original).status_code,200)
            self.prepare_draft_context(api,self.chat_a)
            mid,response=self.send(api,'alice','Draft after exact source deadline',conversation=self.chat_a,intent='consider_trip')
            self.assertEqual(response.status_code,200,response.text)
            model=FakeProvider()
            with patch.object(draft,'document_from_model',expires_inside):outcomes=self.execute(model)
            self.assertEqual(model.calls,2)
            self.assertIn(next(x.status for x in outcomes if x.message_id==mid),('unknown','context_invalid'))
            with self.database.connect(scope_for(ISSUER,'alice')) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],0)

    def test_signed_stop_use_api_strict_wire_unknown_and_rebuilt_query(self):
        from cj_memory.postgres import Repository
        transaction=Repository.transaction
        with TestClient(self.memory_app) as api,TestClient(self.manager) as manager:
            original=self.raw(text='Stop-use API / 停止使用')
            self.assertEqual(self.save(api,original).status_code,200)
            item=self.service().detail(json.loads(original)['item_id']);raw=self.stop_action(item)
            headers={**self.headers('alice'),'Content-Type':'application/octet-stream'}
            def post(value,identity='alice'):
                return manager.post('/v1/memory-withdrawal-actions',content=value,
                    headers={**self.headers(identity),'Content-Type':'application/octet-stream'})
            for change in ({'owner':'bob'},{'version':'unknown'},{'expected_version':True}):
                value=json.loads(raw);value.update(change)
                self.assertEqual(post(json.dumps(value).encode()).status_code,400)
            self.assertEqual(post(raw[:-1]+b',"operation":"withdraw"}').status_code,400)
            self.assertNotEqual(post(raw,'bob').status_code,200)
            self.assertEqual(manager.post('/v1/memory-management-actions',content=raw,headers=headers).status_code,400)
            @contextmanager
            def unknown(repository):
                with transaction(repository) as tx:yield tx
                raise CommitUnknown('fixture lost ACK after real stop-use API commit')
            with patch.object(Repository,'transaction',unknown):response=post(raw)
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.json()['error']['recovery'],'reconcile_original')
            self.assertNotIn('receipt',response.json())
            query={'action_id':json.loads(raw)['action_id']}
            result=manager.get('/v1/memory-withdrawal-receipts',params=query,headers=self.headers('alice'))
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(result.json()['receipt']['status'],'withdrawn')
            self.assertEqual(post(raw).json()['receipt'],result.json()['receipt'])
            self.assertEqual(manager.get('/v1/memory-withdrawal-receipts',params=query,headers=self.headers('bob')).json()['receipt'],None)
            self.assertEqual(manager.get('/v1/memory-management-receipts',params=query,headers=self.headers('alice')).status_code,503)
            (self.auth/'invited.json').write_text('[]')
            try:self.assertNotEqual(manager.get('/v1/memory-withdrawal-receipts',params=query,headers=self.headers('alice')).status_code,200)
            finally:(self.auth/'invited.json').write_text(json.dumps(['alice','bob']))
        with TestClient(self.management_app()) as rebuilt:
            self.assertEqual(rebuilt.get('/v1/memory-withdrawal-receipts',params=query,
                headers=self.headers('alice')).json()['receipt'],result.json()['receipt'])
