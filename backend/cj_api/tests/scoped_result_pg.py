"""B360 ABI2 bridge: actual C pure functions/leases, not C result-product delivery."""
import sys,json,unittest,hashlib,base64
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from datetime import datetime,timezone
import psycopg
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/memory/tests'),str(ROOT/'backend/agent/tests'),str(ROOT/'scripts')]
from edit_support import Fixture,ProbePublisher,Harness,CONNINFO
from cj_draft.scoped_publisher import ScopedPublisher,ScopedState,memory_descriptor,local_configuration
from cj_manual_edit.scoped import Request,resolve
from cj_manual_edit.scoped_explanation import explain
from cj_trip.domain import Trip,packed,Conflict as TripConflict
from cj_trip.current_needs_source import CurrentNeedsSource
from cj_api.local_needs import protected_reader
from cj_api.local_app import LocalDatabase,create_local_app,load_history_configuration,ISSUER
from cj_api.edit_result_profile import activate
from cj_message.edit_result_protocol import EditResultConfiguration,PreparedClarification,ScopedResult,PUBLISHER_ABI
from cj_message.travel import Selection
from cj_agent.provider import FakeProvider,ProviderUnknown
from cj_agent.draft import DraftRejected
from cj_run.core import Binding
from cj_feasibility.solver import Limits


class Model(FakeProvider):
    def __init__(self,*,invalid=False,hook=None):super().__init__();self.invalid,self.hook=invalid,hook
    def stream(self,messages,system=None):
        self.calls+=1;yield ''
        if self.hook:self.hook()
        d=json.loads(system)
        yield packed(dict(version=d['edit_version'],request_id=d['request_id'],trip_id=d['trip_id'],expected_version=d['expected_version'],
            original_hash=d['original_hash'],title='Explicit new global title',order=None,
            changes=[dict(item_id=d['selected_item_ids'][0],field='fixed' if self.invalid else 'text',value=dict(state='known',value=True) if self.invalid else 'Lighter')])).decode()


class Bridge(ScopedPublisher):
    """Only the test table differs; C owns the production table/API in #336."""
    abi=PUBLISHER_ABI
    def prepare(self,binding,source):
        ref=source.reference.public_value();trip=Trip(ref['trip_context']['id'],ref['trip_context']['expected_version'],source.trip_content)
        request=Request.parse(packed(dict(version='TRIP-scoped-request.1',request_id='scoped-'+binding.run_id,trip_id=trip.trip_id,expected_version=trip.version,
            original_hash=ref['trip_context']['content_sha256'],text=json.loads(source.original_utf8)['text'],language=self.language,
            selection=dict(kind='items',item_ids=list(source.selected_item_ids)))))
        resolution=resolve(trip,request)
        if resolution.status=='READY':
            prepared=super().prepare(binding,source)
            if self.after_prepare:self.after_prepare()
            return prepared
        token=self.credentials(binding.scope)
        needs=CurrentNeedsSource(self.database,self.checker,token,protected_reader(self.database,self.checker)).capture(ref['needs_reference']['id'],ref['needs_reference']['expected_version'])
        run=self.memory.registry.captured(binding)
        prepared=PreparedClarification(ScopedState(binding,source,resolution,needs,packed({}),memory_descriptor(run),token))
        if self.after_prepare:self.after_prepare()
        return prepared
    def store(self,publication,prepared,explanation,kind):
        publication.lock_trip()
        key='result-'+prepared.state.binding.run_id
        publication.before_write()
        publication.cursor.execute('INSERT INTO b360_result_probe VALUES(%s,%s,%s,%s,%s,%s)',(prepared.state.binding.scope,key,
            prepared.state.binding.run_id,kind,prepared.state.source.original_utf8,explanation.raw))
        if self.after_write:self.after_write()
        return ScopedResult(kind,key)
    def publish_clarification_in_transaction(self,publication,prepared):
        return self.store(publication,prepared,explain(prepared.state.scope),'clarification_required')
    def publish_in_transaction(self,publication,prepared,reply):
        try:explanation=explain(prepared.state.scope,reply.encode())
        except (ValueError,TripConflict) as exc:raise DraftRejected(str(exc)) from None
        if explanation is not None:
            return self.store(publication,prepared,explanation,'expansion_required')
        return super().publish_in_transaction(publication,prepared,reply)


class ResultChecks(unittest.TestCase):
    headers=Harness.headers
    @classmethod
    def setUpClass(cls):
        Harness.setUpClass.__func__(cls)
        with psycopg.connect(**json.loads(Path(CONNINFO).read_text())) as admin:
            admin.execute('CREATE TABLE b360_result_probe(scope text NOT NULL,result_id text NOT NULL,run_id text NOT NULL,kind text NOT NULL,original_input bytea NOT NULL,explanation bytea NOT NULL,PRIMARY KEY(scope,result_id))')
            admin.execute('ALTER TABLE b360_result_probe ENABLE ROW LEVEL SECURITY');admin.execute('ALTER TABLE b360_result_probe FORCE ROW LEVEL SECURITY')
            admin.execute("CREATE POLICY b360_probe_owner ON b360_result_probe TO cj_m1_runtime USING(scope=NULLIF(current_setting('cj.message_scope',true),'')) WITH CHECK(scope=NULLIF(current_setting('cj.message_scope',true),''))")
            admin.execute('GRANT SELECT,INSERT ON b360_result_probe TO cj_m1_runtime')
    tearDownClass=classmethod(Harness.tearDownClass.__func__)
    def fixture(self,subject):
        f=Fixture(self,subject,ProbePublisher())
        credentials=lambda owner:f.host.headers[owner.removeprefix('local:'+ISSUER+':')]['Authorization'][7:]
        _,cfg=local_configuration(conninfo_path=CONNINFO,auth_dir=f.auth,run_context=f.context,memory=f.memory,credentials=credentials,confirmation=f.signer,
            limits=Limits(datetime(2026,11,1,tzinfo=timezone.utc),7*86400,1,10_000_000,60,120,128,.05,.05,100),language='en')
        p=cfg.publisher
        database=LocalDatabase(CONNINFO,run_context=f.context,travel_context=True,needs_context=True)
        bridge=Bridge(database,p.checker,p.credentials,p.memory,p.confirmation,p.limits,language=p.language)
        bridge.after_write=None;bridge.after_prepare=None
        f.configuration=EditResultConfiguration(cfg.memory,bridge)
        database.edit_configuration=f.configuration;f.database=database
        self.assertEqual(activate(CONNINFO,subject,f.context,f.configuration,Selection(f.namespace['id'],1)),'activated')
        f.app=create_local_app(conninfo_path=CONNINFO,auth_dir=f.auth,run_context=f.context,travel_context=True,needs_profile='manual-v1',edit_configuration=f.configuration,history_configuration=load_history_configuration(f.auth))
        return f,bridge
    def send(self,f,text):
        with TestClient(f.app) as client:
            head=client.put('/v1/conversations',params=dict(conversation_id='original'),headers=f.headers).json()
            raw=packed(dict(version='MESSAGE-send.4',conversation_id='original',message_id='original',text=text,trip_id=None,creation_intent='none',
                expected_generation=head['generation'],expected_sequence=0,modification_intent='propose_scoped_edit',
                trip_context=dict(id=f.trip.trip_id,expected_version=f.trip.version,content_sha256=hashlib.sha256(f.trip.content).hexdigest(),day=None,item_ids=[json.loads(f.trip.content)['items'][-1]['id']]),
                travel_context=dict(id=f.namespace['id'],expected_version=1),needs_reference=dict(id='visit',expected_version=1)))
            response=client.post('/v4/messages',content=raw,headers={**f.headers,'Content-Type':'application/octet-stream'})
            self.assertEqual(response.status_code,200,response.text);receipt=response.json()['receipt']
            status=client.get('/v5/message-send-status',params=dict(conversation_id='original',message_id='original'),headers=f.headers)
            self.assertEqual(status.status_code,200,status.text);self.assertIsNone(status.json()['scoped_result'])
        return raw,receipt,Binding(f.scope,'original',receipt['generation'],'original',receipt['run_id'],1)
    def rows(self,f):
        with f.database.connect(f.scope) as c:return c.execute('SELECT result_id,run_id,kind,original_input,explanation FROM b360_result_probe').fetchall()
    def test_original_recovery_both_categories_zero_formal_writes(self):
        for subject,text,kind,calls in [('clarify','Tomorrow please / 明天轻松一点','clarification_required',0),('expand','Explicit selected item lighter','expansion_required',1)]:
            with self.subTest(kind=kind):
                f,p=self.fixture(subject);raw,receipt,binding=self.send(f,text)
                with f.database.connect(f.scope) as c:before=c.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0]
                model=Model();result=f.run(model)[0]
                self.assertEqual((result.status,result.proposal_id,model.calls),('completed',None,calls))
                state=f.database.run_repository(f.scope).recover(binding).state
                self.assertEqual(state.scoped_result[0],kind);self.assertEqual(len(state.effects),1)
                self.assertEqual(state.effects[0],'scoped_result:'+kind+':'+state.scoped_result[1]);self.assertIsNone(state.draft_outcome)
                self.assertEqual(f.run(model),[]);self.assertEqual(model.calls,calls)
                rows=self.rows(f);self.assertEqual(len(rows),1);self.assertEqual(bytes(rows[0][3]),raw)
                with f.database.connect(f.scope) as c:
                    self.assertEqual(c.execute('SELECT version,content FROM cj_trip_record WHERE trip_id=%s',(f.trip.trip_id,)).fetchone(),(f.trip.version,f.trip.content))
                    self.assertEqual(c.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],before)
                    self.assertEqual(c.execute("SELECT count(*) FROM cj_run_metered_operation WHERE run_id=%s AND kind='model'",(binding.run_id,)).fetchone()[0],calls)
                with TestClient(f.app) as client:
                    for path in ['/v6/run-draft-status','/v5/run-display']:
                        response=client.get(path,params=dict(message_id='original'),headers=f.headers)
                        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['scoped_result']['kind'],kind)
                    self.assertEqual(client.get('/v6/run-draft-status',params=dict(message_id='original'),headers=f.headers).json()['draft_outcome'],kind)
                    for path in ['/v5/run-draft-status','/v4/run-display']:
                        response=client.get(path,params=dict(message_id='original'),headers=f.headers);self.assertEqual(response.status_code,503,response.text)
                    history=client.get('/v4/message-history',params=dict(conversation_id='original',limit=10),headers=f.headers)
                    self.assertEqual(history.status_code,200,history.text)
                    entry=history.json()['messages'][0];self.assertEqual(base64.b64decode(entry['original_utf8_base64']),raw);self.assertEqual(entry['receipt'],receipt)
                    replay=client.post('/v4/messages',content=raw,headers={**f.headers,'Content-Type':'application/octet-stream'})
                    self.assertEqual(replay.json()['receipt'],receipt)
                    foreign=client.get('/v6/run-draft-status',params=dict(message_id='original'),headers=f.host.headers['other-'+subject]);self.assertEqual(foreign.status_code,503)
                original=f.database
                f.database=LocalDatabase(CONNINFO,run_context=f.context,travel_context=True,edit_configuration=f.configuration)
                self.assertEqual(f.database.run_repository(f.scope).recover(binding).state,state)
                with self.assertRaises(psycopg.Error),psycopg.connect(**json.loads(Path(CONNINFO).read_text())) as admin:
                    migration=next(v for v in __import__('migrate').load() if v['version']==29);admin.execute((ROOT/migration['down']).read_text())
    def test_parse_fixed_violation_stays_validation_failed(self):
        f,p=self.fixture('invalid');raw,receipt,binding=self.send(f,'Explicit original selection')
        model=Model(invalid=True);result=f.run(model)[0]
        self.assertEqual(result.status,'completed');self.assertEqual(model.calls,1);self.assertEqual(self.rows(f),[])
        state=f.database.run_repository(f.scope).recover(binding).state;self.assertEqual(state.draft_outcome,'validation_failed');self.assertEqual(state.effects,())

    def test_original_completed_zero_model_run_survives_process_restart_before_delivery_ack(self):
        from cj_message.domain import Service
        f,p=self.fixture('restart');raw,receipt,binding=self.send(f,'Tomorrow / 明天')
        model=Model()
        with patch.object(Service,'acknowledge',side_effect=OSError('controlled process loss before delivery ACK')):
            with self.assertRaises(OSError):f.run(model)
        self.assertEqual(model.calls,0);self.assertEqual(len(self.rows(f)),1)
        result=f.run(model)[0]
        self.assertEqual(result.status,'completed');self.assertEqual(model.calls,0);self.assertEqual(len(self.rows(f)),1)

    def test_memory_and_needs_change_after_model_refuse_results(self):
        for mode in ('memory','needs'):
            f,p=self.fixture('changed-'+mode);raw,receipt,binding=self.send(f,'Explicit original selected item')
            def change():
                if mode=='memory':f.manage('edit',1,text='New actual preference')
                else:
                    with TestClient(f.app) as client:
                        response=client.post('/v1/needs-actions',content=packed(dict(action_id='correct',needs_id='visit',expected_version=1,
                            source=dict(kind='manual',text='explicit correction'),changes=dict(party_size=dict(state='known',value=2)))),headers={**f.headers,'Content-Type':'application/octet-stream'})
                        self.assertEqual(response.status_code,200,response.text)
            model=Model(hook=change);result=f.run(model)[0]
            self.assertIn(result.status,('context_invalid','unknown'));self.assertEqual(model.calls,1);self.assertEqual(self.rows(f),[])

    def test_cancel_unknown_and_deadline_before_result_keep_zero_models_and_rows(self):
        from cj_run.core import Service,Event
        from cj_usage.metered_exit import MeteredExitCore
        for mode in ('cancel','unknown','deadline'):
            f,p=self.fixture('before-'+mode);raw,receipt,binding=self.send(f,'Tomorrow / 明天');expired=[False]
            def change():
                service=Service(f.database.run_repository(f.scope),lambda _:True)
                if mode=='cancel':service.cancel(binding)
                elif mode=='unknown':
                    state=service.snapshot(binding);service.apply(Event(binding,state.sequence+1,'original-unknown','unknown'))
                else:expired[0]=True
            p.after_prepare=change
            original_now=MeteredExitCore._now
            def clock(core,previous):
                value=original_now(core,previous)
                return value+core.config.max_seconds+1 if expired[0] else value
            model=Model()
            with patch.object(MeteredExitCore,'_now',clock):result=f.run(model)[0]
            state=f.database.run_repository(f.scope).recover(binding).state
            self.assertEqual(model.calls,0)
            self.assertEqual(self.rows(f),[]);self.assertEqual(state.effects,())
            if mode=='deadline':self.assertEqual((result.status,state.draft_outcome),('completed','budget_exhausted'))
            else:self.assertEqual(result.status,'cancelled' if mode=='cancel' else 'unknown')

    def test_common_transaction_rollback_removes_result_and_run_effect(self):
        f,p=self.fixture('rollback');raw,receipt,binding=self.send(f,'Tomorrow / 明天')
        def fail():raise OSError('controlled after-write rollback')
        p.after_write=fail;model=Model()
        with self.assertRaises(OSError):f.run(model)
        self.assertEqual(self.rows(f),[]);self.assertEqual(model.calls,0)
        state=f.database.run_repository(f.scope).recover(binding).state
        self.assertEqual(state.status,'running');self.assertEqual(state.effects,())
        p.after_write=None
        self.assertEqual(f.run(model)[0].status,'unknown');self.assertEqual(model.calls,0);self.assertEqual(self.rows(f),[])

    def test_physical_commit_ack_loss_reconciles_original_common_commit(self):
        f,p=self.fixture('physical-ack');raw,receipt,binding=self.send(f,'Tomorrow / 明天')
        connect=LocalDatabase.connect
        class Cursor:
            def __init__(self,base,connection):self.base,self.connection=base,connection
            def __getattr__(self,key):return getattr(self.base,key)
            def execute(self,query,*args,**kwargs):
                if isinstance(query,str) and query.startswith('INSERT INTO b360_result_probe'):self.connection.wrote=True
                return self.base.execute(query,*args,**kwargs)
        class Connection:
            def __init__(self,base):self.base,self.wrote=base,False
            def __getattr__(self,key):return getattr(self.base,key)
            def __enter__(self):return self.base.__enter__()
            def __exit__(self,*args):return self.base.__exit__(*args)
            def cursor(self,*args,**kwargs):return Cursor(self.base.cursor(*args,**kwargs),self)
            def commit(self):
                self.base.commit()
                if self.wrote:raise OSError('controlled physical result ACK loss')
        def wrapped(database,*args,**kwargs):return Connection(connect(database,*args,**kwargs))
        model=Model()
        with patch.object(LocalDatabase,'connect',wrapped):result=f.run(model)[0]
        self.assertEqual(result.status,'completed');self.assertEqual(model.calls,0);self.assertEqual(len(self.rows(f)),1)
        state=f.database.run_repository(f.scope).recover(binding).state
        self.assertEqual(state.status,'completed');self.assertEqual(state.scoped_result[0],'clarification_required')
        self.assertEqual(f.run(model),[]);self.assertEqual(model.calls,0)

    def test_trip_selection_aba_and_account_fences_keep_zero_results(self):
        for mode in ('trip','aba','account'):
            f,p=self.fixture('fence-'+mode);raw,receipt,binding=self.send(f,'Tomorrow / 明天')
            def change():
                if mode=='trip':
                    # Actual C sole Proposal/Signer/act writer supplies a changed
                    # formal-record counterexample, not a production replan claim.
                    import time
                    from cj_trip.postgres import Repository
                    from cj_trip.domain import Proposal
                    from cj_agent.draft import trip_scope_for
                    repository=Repository(lambda:f.database.connect(f.scope),trip_scope_for(f.scope),f.signer,structured=True)
                    content=json.loads(f.trip.content);content['title']='Explicit counterexample version'
                    proposal=Proposal('counterexample-version',f.trip.trip_id,f.trip.version,'fixture-explicit.1',int(time.time())+300,packed(content))
                    repository.publish(proposal);detail=repository.proposal_detail(proposal.proposal_id)
                    action=f.signer.issue(repository.scope,detail,action_id='counterexample-accept',kind='accept',candidate_hash=detail.candidate_hash).action
                    repository.act(action)
                elif mode=='aba':
                    with TestClient(f.app) as client:
                        for index,namespace in enumerate((f.other_namespace,f.namespace),1):
                            value=json.loads(raw);value.update(message_id='new-'+str(index),expected_sequence=index)
                            value['travel_context']=dict(id=namespace['id'],expected_version=1)
                            response=client.post('/v4/messages',content=packed(value),headers={**f.headers,'Content-Type':'application/octet-stream'})
                            self.assertEqual(response.status_code,200,response.text)
                else:
                    invited=f.auth/'invited.json';invited.write_text(json.dumps(['other-'+f.subject]))
            p.after_prepare=change;model=Model();result=f.run(model)[0]
            self.assertIn(result.status,('context_invalid','unknown'));self.assertEqual(model.calls,0);self.assertEqual(self.rows(f),[])

    def test_actual_registered_budget_denial_keeps_original_outcome(self):
        from cj_usage.core import Meter
        f,p=self.fixture('budget')
        remaining=16-Meter.exposure(f.host.ledger(f.subject))
        for index in range(remaining):
            f.send('discussion-'+str(index),intent='none');model=FakeProvider()
            self.assertEqual(f.run(model)[0].status,'completed');self.assertEqual(model.calls,1)
        raw,receipt,binding=self.send(f,'Explicit original selected item')
        model=Model();result=f.run(model)[0]
        state=f.database.run_repository(f.scope).recover(binding).state
        self.assertEqual((result.status,model.calls,state.draft_outcome,state.budget_exhausted_stage),('completed',0,'budget_exhausted','draft'))
        self.assertEqual(state.effects,());self.assertEqual(self.rows(f),[])

    def test_provider_unknown_retains_original_exposure_without_result_or_retry(self):
        f,p=self.fixture('provider-unknown');raw,receipt,binding=self.send(f,'Explicit original selected item')
        class Unknown(FakeProvider):
            def stream(self,*args,**kwargs):
                self.calls+=1;raise ProviderUnknown('controlled original registered model uncertainty');yield
        model=Unknown();result=f.run(model)[0]
        self.assertEqual((result.status,model.calls),('unknown',1));self.assertEqual(self.rows(f),[])
        self.assertEqual(f.run(model),[]);self.assertEqual(model.calls,1)

if __name__=='__main__':unittest.main()
