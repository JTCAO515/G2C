"""Actual signed API/registered Fake PLACE/run_once -> source-bound Trip lifecycle."""
import base64,json,sys,unittest
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/agent/tests'),str(ROOT/'backend/cj_api/tests'),str(ROOT/'backend/memory/tests'),str(ROOT/'backend/manual_edit/tests'),str(ROOT/'scripts')]
from e2e_local import Harness,CONNINFO
from registered_host_support import RegisteredHost
from cj_api.local_app import LocalDatabase,create_local_app,load_confirmation_signer,load_history_configuration,ISSUER,scope_for
from cj_api.local_tools import SyntheticToolModel
from cj_api.local_place_draft import LocalPlaceDraftTools
from cj_place.draft_source import PlaceDraftConfiguration
from cj_draft.place_local import PlaceDraftAdapter,SYSTEM
from cj_draft.place_plan import MODEL_VERSION
from cj_trip.local_needs_app import create_local_needs_app
from cj_trip.local_place_manual import create_local_place_manual_app
from cj_trip.local_structured_read import create_local_structured_read_app
from cj_trip.domain import packed
from cj_message.travel import ABI,Selection
import dev_auth,run_worker


class PlacePlanFake(SyntheticToolModel):
    def __init__(self,change=None,hook=None):super().__init__();self.change,self.hook=change,hook;self.inputs=[]
    def stream(self,messages,system=None):
        if system!=SYSTEM:yield from super().stream(messages,system);return
        self.calls+=1;yield ''
        source=json.loads(messages[-1]['content']);self.inputs.append(source)
        items=[]
        for original in source['fields']['fixed_items']:
            schedule={edge:{key:deepcopy(original[edge][key]) for key in ('date','time','timezone')} for edge in ('start','end')}
            for event in schedule.values():event['utc_offset']=dict(state='unknown')
            items.append(dict(id=original['item_id'],text=original['description'],verification='pending',evidence=[],schedule=schedule,
                fixed=original['locked'],source_category='user_provided',source_refs=[]))
        refs={}
        for row,choice in zip([v for v in items if v['fixed']==dict(state='known',value=False)],source['place_choices']):
            row.update(text=choice['place']['name_zh'],source_category='unknown');refs[row['id']]=choice['choice_id']
        value=dict(version=MODEL_VERSION,title='同名地点 / distinct actual source identities',items=items,proposed_subjects={},place_refs=refs)
        if self.change:self.change(value)
        if self.hook:self.hook()
        yield packed(value).decode()


class PlaceChainChecks(unittest.TestCase):
    headers=Harness.headers;setUpClass=classmethod(Harness.setUpClass.__func__);tearDownClass=classmethod(Harness.tearDownClass.__func__)
    def fixture(self,key,version='structured.2',text='查询合成酒店并安排 / synthetic hotel plan'):
        subject='p21-'+key;host=RegisteredHost(self.auth/subject,Path(CONNINFO),{s:(30,4,30000) for s in (subject,'other-'+subject)})
        context=host.profiles[subject][1];dev_auth.activate_travel(Path(CONNINFO),subject,context,ABI)
        f=SimpleNamespace(subject=subject,host=host,context=context,signer=load_confirmation_signer(host.auth),headers=host.headers[subject],scope=scope_for(ISSUER,subject),version=version)
        f.database=LocalDatabase(CONNINFO,run_context=context,travel_context=True,needs_context=True)
        f.api=create_local_app(conninfo_path=CONNINFO,auth_dir=host.auth,run_context=context,travel_context=True,needs_profile='manual-v1',confirmation_signer=f.signer,history_configuration=load_history_configuration(host.auth))
        known=lambda v:dict(state='known',value=v)
        clocks=['09:00:00','10:00:00','11:00:00','12:00:00','13:00:00','14:00:00'] if version=='structured.1' else ['09:00','10:00','11:00','12:00','13:00','14:00']
        def event(t):return dict(date=known('2026-11-02'),time=known(t),timezone=known('Asia/Shanghai'),place=dict(state='unknown'))
        declarations=[dict(item_id=k,kind='appointment' if i==0 else 'intent',description='Explicit original '+k,applies_to=['self'],locked=known(i==0),booking_status=known('booked') if i==0 else dict(state='unknown'),start=event(clocks[2*i]),end=event(clocks[2*i+1])) for i,k in enumerate(('a','b','c'))]
        with f.database.connect(f.scope) as c:self.assertEqual(c.execute('SELECT current_user').fetchone(),('cj_m1_runtime',))
        with TestClient(f.api) as c:
            self.ok(self.post(c,f,'/v1/needs-actions',packed(dict(action_id='source',needs_id='visit',expected_version=0,source=dict(kind='manual',text='Explicit original constraints'),changes=dict(fixed_items=declarations)))))
            f.namespace=self.ok(self.post(c,f,'/v1/travel-context-actions',packed(dict(version='TRAVEL-context-action.1',action_id='namespace',operation='create',travel_context=None))))['receipt']['travel_context']
            head=self.ok(c.put('/v1/conversations',params={'conversation_id':'plan'},headers=f.headers))
            f.raw=packed(dict(version='MESSAGE-send.2',conversation_id='plan',message_id='plan',text=text,trip_id=None,creation_intent='consider_trip',expected_generation=head['generation'],expected_sequence=0,
                travel_context=dict(id=f.namespace['id'],expected_version=1),needs_reference=dict(id='visit',expected_version=1)))
            f.original=self.ok(self.post(c,f,'/v2/messages',f.raw))['receipt']
        f.tools=LocalPlaceDraftTools();f.configuration=PlaceDraftConfiguration(PlaceDraftAdapter(version))
        return f
    def ok(self,response,code=200):self.assertEqual(response.status_code,code,response.text);return response.json()
    def post(self,c,f,path,raw):return c.post(path,content=raw,headers={**f.headers,'Content-Type':'application/octet-stream'})
    def execute(self,f,model):return run_worker.run_once(f.database,model,f.host.auth,tools_configuration=f.tools,place_draft_configuration=f.configuration)
    def needs_host(self,f):return create_local_needs_app(conninfo_path=CONNINFO,auth_dir=f.host.auth,run_context=f.context,confirmation_signer=f.signer)
    def manual_host(self,f):return create_local_place_manual_app(conninfo_path=CONNINFO,auth_dir=f.host.auth,run_context=f.context,confirmation_signer=f.signer)
    def read(self,f,tid,headers=None):
        with TestClient(create_local_structured_read_app(conninfo_path=CONNINFO,auth_dir=f.host.auth,run_context=f.context)) as c:
            return self.ok(c.get('/v5/trip-structured',params={'trip_id':tid},headers=headers or f.headers))['trip']
    def generate(self,f,model):
        self.execute(f,model) # Never use Outcome or inferred prefix to discover a candidate.
        with TestClient(self.manual_host(f)) as c:
            d=self.ok(c.get('/v2/trip-needs-discovery',params=dict(message_id=f.original['message_id'],run_id=f.original['run_id']),headers=f.headers))['discovery']
            self.assertEqual(d['state'],'published');p=d['proposal']
            raw=packed(dict(version='TRIP-needs-action.1',action_id='adopt',kind='accept',proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash']))
        with TestClient(self.needs_host(f)) as c:
            r=self.ok(self.post(c,f,'/v1/trip-needs-actions',raw))['receipt']
            self.assertEqual(self.ok(self.post(c,f,'/v1/trip-needs-actions',raw))['receipt'],r)
        trip=self.read(f,r['trip_id']);self.assertEqual(trip['content'],p['content']);return trip
    def points(self,trip):
        document=trip['content'];values={}
        for item in document['items']:
            if item['source_category']!='queried':continue
            source=next(v for v in document['sources'] if v['id']==item['source_refs'][0])
            raw=base64.b64decode(source['snapshot_utf8_base64']);self.assertEqual(__import__('hashlib').sha256(raw).hexdigest(),source['snapshot_sha256'])
            record=json.loads(raw)['record'];self.assertEqual(item['text'],record['place']['name_zh'])
            self.assertEqual((item['verification'],item['evidence'],source['evidence_level']),('pending',[],'synthetic'))
            values[item['id']]=(source,record)
        return values
    def manual(self,f,trip,key,title=None):
        value=dict(version='TRIP-needs-edit.2',needs_reference=dict(id='visit',expected_version=1),edit=dict(version='TRIP-manual-edit.1' if f.version=='structured.1' else 'TRIP-manual-edit.2',request_id=key,
            trip_id=trip['trip_id'],expected_version=trip['version'],original_hash=trip['content_sha256'],title=title or 'New explicit title',changes=[],order=None))
        with TestClient(self.manual_host(f)) as c:
            p=self.ok(self.post(c,f,'/v2/trip-needs-edits',packed(value)))['preparation']
            raw=packed(dict(version='TRIP-needs-save.2',action_id='save-'+key,proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash']))
            r=self.ok(self.post(c,f,'/v2/trip-needs-saves',raw))['receipt']
            self.assertEqual(self.ok(self.post(c,f,'/v2/trip-needs-saves',raw))['receipt'],r)
        return self.read(f,r['trip_id'])
    def scoped_time(self,f,trip):
        from cj_memory.edit_runtime import EditRuntimeConfiguration
        from cj_draft.place_scoped import local_configuration
        from cj_trip.local_scoped_app import create_local_scoped_app
        from scoped_runtime_pg import limits,Model
        import message_edit_profile
        profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term','current'],context_ids=[])
        collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={f.subject:profile}),travel_contexts={f.subject:[f.namespace['id']]})
        memory=EditRuntimeConfiguration.from_bytes(packed(dict(version='local-memory-edit-run.1',collection=collection,selections={f.subject:dict(subject='self',slots=['pace'],max_bytes=8000)})))
        db,cfg=local_configuration(conninfo_path=CONNINFO,auth_dir=f.host.auth,run_context=f.context,memory=memory,credentials=lambda owner:f.headers['Authorization'][7:],confirmation=f.signer,limits=limits(),language='en')
        self.assertEqual(message_edit_profile.activate(CONNINFO,f.subject,f.context,cfg,Selection(f.namespace['id'],1)),'activated')
        api=create_local_app(conninfo_path=CONNINFO,auth_dir=f.host.auth,run_context=f.context,travel_context=True,edit_configuration=cfg)
        with TestClient(api) as c:
            head=self.ok(c.put('/v1/conversations',params={'conversation_id':'edit'},headers=f.headers))
            raw=packed(dict(version='MESSAGE-send.4',conversation_id='edit',message_id='edit',text='Change selected time only',trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0,
                modification_intent='propose_scoped_edit',trip_context=dict(id=trip['trip_id'],expected_version=trip['version'],content_sha256=trip['content_sha256'],day=None,item_ids=['b']),travel_context=dict(id=f.namespace['id'],expected_version=1),needs_reference=dict(id='visit',expected_version=1)))
            r=self.ok(self.post(c,f,'/v4/messages',raw))['receipt']
        schedule=deepcopy(trip['content']['items'][1]['schedule']);seconds=f.version=='structured.1'
        schedule['start']['time']['value']='11:05:00' if seconds else '11:05';schedule['end']['time']['value']='12:05:00' if seconds else '12:05'
        model=Model(lambda d:d.update(changes=[dict(item_id='b',field='schedule',value=schedule)]))
        run_worker.run_once(db,model,f.host.auth);self.assertEqual(model.calls,1)
        with TestClient(create_local_scoped_app(database=db,configuration=cfg)) as c:
            d=self.ok(c.get('/v1/trip-scoped-discovery',params=dict(message_id=r['message_id'],run_id=r['run_id']),headers=f.headers))['discovery'];p=d['proposal']
            self.assertIsNotNone(p)
            action=packed(dict(version='TRIP-scoped-action.1',action_id='accept-time',kind='accept',proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash']))
            receipt=self.ok(self.post(c,f,'/v1/trip-scoped-actions',action))['receipt']
        return self.read(f,receipt['trip_id'])

    def test_both_formats_tool_to_adoption_v5_manual_and_scoped_preserve_exact_place_sources(self):
        for version in ('structured.1','structured.2'):
            with self.subTest(version=version):
                f=self.fixture(version,version);model=PlacePlanFake();trip=self.generate(f,model)
                self.assertEqual((model.calls,f.tools.place.invocations,f.tools.place.transport_calls),(3,1,1))
                self.assertEqual(trip['content']['content_version'],version);points=self.points(trip)
                self.assertEqual([points[k][1]['place']['provider_id'] for k in ('b','c')],['SYNTH_EAST','SYNTH_WEST'])
                self.assertEqual(points['b'][1]['place']['coordinate']['value'],dict(raw='116.100000,39.100000',longitude='116.100000',latitude='39.100000',crs='GCJ-02'))
                self.assertEqual(points['c'][1]['place']['coordinate']['value']['raw'],'116.200000,39.200000')
                self.assertIsNone(self.read(f,trip['trip_id'],f.host.headers['other-'+f.subject]))
                changed=self.manual(f,trip,'title-only');self.assertEqual(changed['version'],2);self.assertEqual(self.points(changed),points)
                changed=self.scoped_time(f,changed);self.assertEqual(changed['version'],3);self.assertEqual(self.points(changed),points)

    def test_optional_no_result_remains_unknown_without_default_point(self):
        f=self.fixture('no-results',text='SYNTH_MISSING');model=PlacePlanFake();trip=self.generate(f,model)
        self.assertEqual(self.points(trip),{});self.assertEqual(trip['content']['sources'],[])
        self.assertTrue(all(not v['source_refs'] for v in trip['content']['items']))
        self.assertEqual((model.calls,f.tools.place.invocations),(3,1))

    def test_optional_absent_coordinate_is_real_typed_missing_not_default_zero(self):
        from cj_place.local_draft_source import LocalDraftPlaceProducer
        f=self.fixture('missing-coordinate')
        class Missing(LocalDraftPlaceProducer):
            def _response(self,query):return 200,dict(status='1',info='OK',infocode='10000',count='1',pois=[dict(id='SYNTH_NO_COORD',name='合成未知坐标')])
        f.tools.place=Missing(f.tools.place.config,clock=f.tools.place.clock)
        model=PlacePlanFake();trip=self.generate(f,model);points=self.points(trip)
        self.assertEqual(points['b'][1]['place']['provider_id'],'SYNTH_NO_COORD')
        self.assertEqual(points['b'][1]['place']['coordinate'],dict(state='missing',value=None))
        self.assertEqual((model.calls,f.tools.place.invocations,f.tools.place.transport_calls),(3,1,1))

    def test_original_source_stale_config_cancel_and_needs_change_leave_no_candidate(self):
        from dataclasses import replace
        from cj_run.core import Binding
        for mode in ('stale','config','cancel','needs'):
            f=self.fixture('fence-'+mode)
            def change():
                if mode=='stale':f.tools.place.clock=lambda:datetime.now(timezone.utc)+timedelta(seconds=61)
                elif mode=='config':f.tools.place.config=replace(f.tools.place.config,max_age_seconds=f.tools.place.config.max_age_seconds+1)
                elif mode=='cancel':
                    with TestClient(f.api) as c:self.ok(c.post('/v2/run-cancellations',json=dict(version='RUN-cancel.2',message_id='plan'),headers=f.headers))
                else:
                    with TestClient(f.api) as c:self.ok(self.post(c,f,'/v1/needs-actions',packed(dict(action_id='correct',needs_id='visit',expected_version=1,
                        source=dict(kind='manual',text='Explicit changed source'),changes=dict(party_size=dict(state='known',value=3))))))
            model=PlacePlanFake(hook=change);self.execute(f,model)
            r=f.original;binding=Binding(f.scope,r['conversation_id'],r['generation'],r['message_id'],r['run_id'],r['sequence'])
            state=f.database.run_repository(f.scope).recover(binding).state
            self.assertEqual(state.effects,())
            with f.database.connect(f.scope) as c:
                self.assertEqual(c.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0],0)
            before=(model.calls,f.tools.place.invocations)
            self.assertEqual(self.execute(f,model),[]);self.assertEqual((model.calls,f.tools.place.invocations),before)

    def test_manual_v2_wrong_owner_old_version_and_original_receipt_recovery(self):
        f=self.fixture('manual-recovery','structured.1');trip=self.generate(f,PlacePlanFake());points=self.points(trip)
        value=dict(version='TRIP-needs-edit.2',needs_reference=dict(id='visit',expected_version=1),edit=dict(version='TRIP-manual-edit.1',request_id='original-edit',trip_id=trip['trip_id'],
            expected_version=trip['version'],original_hash=trip['content_sha256'],title='Explicit second title',changes=[],order=None))
        with TestClient(self.manual_host(f)) as c:
            raw=packed(value);p=self.ok(self.post(c,f,'/v2/trip-needs-edits',raw))['preparation']
            wrong=c.post('/v2/trip-needs-edits',content=raw,headers={**f.host.headers['other-'+f.subject],'Content-Type':'application/octet-stream'});self.ok(wrong,503)
            save=packed(dict(version='TRIP-needs-save.2',action_id='original-save',proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash']))
            receipt=self.ok(self.post(c,f,'/v2/trip-needs-saves',save))['receipt']
            self.assertEqual(self.ok(self.post(c,f,'/v2/trip-needs-saves',save))['receipt'],receipt)
            value['edit']['request_id']='stale-edit'
            self.ok(self.post(c,f,'/v2/trip-needs-edits',packed(value)),409)
        with TestClient(self.needs_host(f)) as c:
            recovered=self.ok(c.get('/v1/trip-needs-action-receipts',params={'action_id':'original-save'},headers=f.headers))['receipt']
            self.assertEqual(recovered,receipt)
            # New preparation must not be emitted under the old manual.1 route.
            self.ok(c.get('/v1/trip-needs-edits',params={'request_id':'original-edit'},headers=f.headers),503)
        self.assertEqual(self.points(self.read(f,receipt['trip_id'])),points)

    def test_model_source_forgery_and_wrong_choice_have_zero_formal_writes(self):
        for key,change in [('source-upload',lambda d:d.update(sources=[])),('wrong-choice',lambda d:d['place_refs'].update(b='not-an-issued-choice'))]:
            f=self.fixture(key);model=PlacePlanFake(change);self.execute(f,model)
            with f.database.connect(f.scope) as c:
                self.assertEqual(c.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0],0)
            self.assertEqual((model.calls,f.tools.place.invocations),(3,1))


if __name__=='__main__':unittest.main(verbosity=2)
