"""B388 actual source seam; test C adapter bridge is not the C map producer."""
import base64,json,os,sys,time
from pathlib import Path
from datetime import timedelta
from fastapi.testclient import TestClient
import local_history_pg as harness
from registered_host_support import RegisteredHost
from cj_api.local_app import LocalDatabase,create_local_app,scope_for,ISSUER
from cj_api.local_place_draft import LocalPlaceDraftTools
from cj_api.local_tools import LocalTools,TOOL_SYSTEM,SyntheticToolModel
from cj_api.local_plan_model import NeedsPlanFakeProvider
from cj_api.composition import CompositionUnavailable
from cj_place.draft_source import PlaceDraftConfiguration,PUBLISHER_ABI,PlaceSourceUnavailable,PlaceSourceBatch
from cj_place.local_draft_source import LocalDraftPlaceProducer
from cj_place.models import FieldState,Outcome
from cj_trip.domain import packed
from cj_draft.needs_publisher import NeedsDraftPublisher,SYSTEM
from cj_draft.needs_local import publisher as base_factory
from cj_trip.structured import validate_document
sys.path.insert(0,str(harness.ROOT/'scripts'))
import dev_auth,run_worker


class Producer(NeedsDraftPublisher):
    def __init__(self,base,source,version,observed,hook):
        super().__init__(base.repository,base.source,clock=base.clock)
        self.place_sources,self.content_version,self.observed,self.hook=source,version,observed,hook
    def sources_for(self,binding):
        capture=super().sources_for(binding)
        if self.hook=='no-capture':return capture
        self.batch=self.place_sources.capture(binding)
        self.observed.append((binding,self.batch));return capture
    def build_plan(self,raw,capture):
        content,candidate,report=super().build_plan(raw,capture)
        if self.content_version=='structured.1':
            doc=json.loads(content);doc['content_version']='structured.1';validate_document(doc);content=packed(doc)
        return content,candidate,report
    def publish_for_message(self,binding,original,current,reply,capture,*,before_publish=None):
        if self.hook and self.hook!='no-capture':self.hook(self,binding)
        self.place_sources.check(binding,self.batch)
        return super().publish_for_message(binding,original,current,reply,capture,before_publish=before_publish)


class Adapter:
    abi=PUBLISHER_ABI
    def __init__(self,version,hook=None):self.version,self.hook=version,hook;self.observed=[]
    def bind(self,database,checker,message_context,token_supplier,scope,*,place_sources):
        return Producer(base_factory(database,checker,message_context,token_supplier,scope),place_sources,self.version,self.observed,self.hook)


class Model(SyntheticToolModel):
    def __init__(self,hook=None):super().__init__();self.hook=hook;self.source_seen=False
    def stream(self,messages,system=None):
        if system==SYSTEM:
            self.source_seen=True
            yield ''
            if self.hook:self.hook()
            yield from NeedsPlanFakeProvider.stream(self,messages,system)
        else:yield from super().stream(messages,system)


def exercise(auth,conninfo):
    subjects=['one','two','stale','clock','config','copy','timeout','foreign','old','changed-needs','cancelled','no-coordinate','no-results','no-capture']
    host=RegisteredHost(auth,conninfo,{s:(12,2,30000) for s in subjects})
    for s in subjects:dev_auth.activate_travel(conninfo,s,host.profiles[s][1],'MESSAGE-TRAVEL-CONSUMER@1')
    def db(s):return LocalDatabase(conninfo,run_context=host.profiles[s][1],travel_context=True)
    def app(s):return create_local_app(conninfo_path=conninfo,auth_dir=auth,run_context=host.profiles[s][1],travel_context=True,needs_profile='manual-v1')
    def setup(s,text='合成酒店'):
        with TestClient(app(s)) as c:
            headers={**host.headers[s],'Content-Type':'application/octet-stream'}
            unknown=dict(state='unknown');event={k:unknown for k in ('date','time','timezone','place')}
            item=dict(item_id='a',kind='appointment',description='Explicit original plan',applies_to=['self'],locked=dict(state='known',value=False),booking_status=unknown,start=event,end=event)
            harness.expect(c.post('/v1/needs-actions',content=packed(dict(action_id='source',needs_id='visit',expected_version=0,source=dict(kind='manual',text='Explicit source'),changes=dict(fixed_items=[item]))),headers=headers))
            ns=harness.expect(c.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id='namespace',operation='create',travel_context=None)),headers=headers))['receipt']['travel_context']
            chat=harness.expect(c.put('/v1/conversations',params=dict(conversation_id=s),headers=host.headers[s]))
            raw=packed(dict(version='MESSAGE-send.2',conversation_id=s,message_id='message-'+s,text=text,trip_id=None,creation_intent='consider_trip',expected_generation=chat['generation'],expected_sequence=0,travel_context=dict(id=ns['id'],expected_version=1),needs_reference=dict(id='visit',expected_version=1)))
            return harness.expect(c.post('/v2/messages',content=raw,headers=headers))['receipt'],raw
    def run(s,tools,adapter,model):return run_worker.run_once(db(s),model,auth,tools_configuration=tools,place_draft_configuration=PlaceDraftConfiguration(adapter))
    for s,version in [('one','structured.1'),('two','structured.2')]:
        receipt,raw=setup(s);tools=LocalPlaceDraftTools();adapter=Adapter(version);model=Model()
        outcome=run(s,tools,adapter,model)[0]
        assert outcome.status=='completed' and outcome.proposal_id and model.source_seen and model.calls==3
        assert tools.place.invocations==tools.place.transport_calls==1
        binding,batch=adapter.observed[0];assert batch.binding==binding and binding.run_id==receipt['run_id']
        assert len(batch.observations)==1;observation=batch.observations[0]
        assert observation.config is tools.place.config and observation.config.max_age_seconds==60
        places=observation.result.places;assert len(places)==2 and places[0].name_zh==places[1].name_zh
        assert [p.provider_id for p in places]==['SYNTH_EAST','SYNTH_WEST']
        assert [p.coordinate.value.raw for p in places]==['116.100000,39.100000','116.200000,39.200000']
        assert all(p.coordinate.value.crs=='GCJ-02' for p in places)
        with db(s).connect(scope_for(ISSUER,s)) as c:
            assert c.execute('SELECT count(*) FROM cj_run_metered_operation WHERE run_id=%s',(receipt['run_id'],)).fetchone()[0]==4
            result=c.execute('SELECT content FROM cj_trip_proposal WHERE proposal_id=%s',(outcome.proposal_id,)).fetchone()
            assert json.loads(bytes(result[0]))['content_version']==version
            assert c.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0]==0
        for view,b in [(tools.source_for(scope_for(ISSUER,'foreign')),binding)]:
            try:view.capture(b)
            except PlaceSourceUnavailable:pass
            else:raise AssertionError('foreign capture accepted')
        try:tools.source_for(binding.scope).check(binding,batch)
        except PlaceSourceUnavailable:pass
        else:raise AssertionError('expired publication handle accepted')
        assert run(s,tools,adapter,model)==[] and model.calls==3 and tools.place.invocations==1
    for s in ('stale','clock','config','copy','changed-needs','cancelled','no-capture'):
        receipt,raw=setup(s);tools=LocalPlaceDraftTools();clock=tools.place.clock
        def mutate():
            if s=='stale':tools.place.clock=lambda:clock()+timedelta(seconds=120)
            elif s=='clock':tools.place.clock=lambda:clock()-timedelta(seconds=1)
            elif s=='config':
                from dataclasses import replace
                tools.place.config=replace(tools.place.config,max_age_seconds=61)
            elif s=='changed-needs':
                with TestClient(app(s)) as c:harness.expect(c.post('/v1/needs-actions',content=packed(dict(action_id='correct',needs_id='visit',expected_version=1,source=dict(kind='manual',text='Correction'),changes=dict(party_size=dict(state='known',value=2)))),headers={**host.headers[s],'Content-Type':'application/octet-stream'}))
            elif s=='cancelled':
                with TestClient(app(s)) as c:harness.expect(c.post('/v2/run-cancellations',json=dict(version='RUN-cancel.2',message_id=receipt['message_id']),headers=host.headers[s]))
        def copied(producer,binding):
            if s=='copy':producer.place_sources.check(binding,PlaceSourceBatch(binding,producer.batch.observations))
        adapter=Adapter('structured.2','no-capture' if s=='no-capture' else copied);model=Model(mutate)
        outcome=run(s,tools,adapter,model)[0];assert outcome.proposal_id is None
        assert outcome.status in ('unknown','context_invalid','cancelled')
        assert tools.place.invocations==1
        assert run(s,tools,adapter,model)==[]
    receipt,raw=setup('timeout','SYNTH_TIMEOUT');tools=LocalPlaceDraftTools();adapter=Adapter('structured.2');model=Model()
    outcome=run('timeout',tools,adapter,model)[0];assert outcome.status=='unknown' and outcome.proposal_id is None and not adapter.observed
    assert tools.place.invocations==1 and model.calls==1
    assert run('timeout',tools,adapter,model)==[] and tools.place.invocations==1
    old_receipt,_=setup('old');model=Model()
    try:run('old',LocalTools(),Adapter('structured.2'),model)
    except CompositionUnavailable:pass
    else:raise AssertionError('old tools silently upgraded')
    assert model.calls==0
    try:run_worker.run_once(db('old'),model,auth,tools_configuration=LocalTools(),draft_profile='needs-structured.1')
    except CompositionUnavailable:pass
    else:raise AssertionError('old mutually-exclusive profiles were relaxed')
    assert model.calls==0
    with TestClient(app('old')) as c:
        harness.expect(c.post('/v2/run-cancellations',json=dict(version='RUN-cancel.2',message_id=old_receipt['message_id']),headers=host.headers['old']))
    old_model=SyntheticToolModel()
    assert run_worker.run_once(db('old'),old_model,auth,tools_configuration=LocalTools())[0].status=='cancelled'
    assert old_model.calls==0
    for s in ('no-coordinate','no-results'):
        receipt,raw=setup(s,'SYNTH_MISSING' if s=='no-results' else '合成酒店')
        tools=LocalPlaceDraftTools()
        if s=='no-coordinate':
            class MissingCoordinate(LocalDraftPlaceProducer):
                def _response(self,query):return 200,dict(status='1',info='OK',infocode='10000',count='1',pois=[dict(id='SYNTH_NOC',name='合成酒店',address=[],location=[])])
            original=tools.place;tools.place=MissingCoordinate(original.config,clock=original.clock)
        adapter=Adapter('structured.2');model=Model();outcome=run(s,tools,adapter,model)[0]
        observation=adapter.observed[0][1].observations[0]
        if s=='no-coordinate':assert observation.result.places[0].coordinate.state is FieldState.EMPTY_ARRAY and observation.result.places[0].coordinate.value is None
        else:assert observation.result.outcome is Outcome.NO_RESULTS and not observation.result.places
        assert tools.place.invocations==1 and model.calls==3,(s,outcome.status,model.calls,tools.place.invocations)
    print('PASS388 B actual typed PLACE/source Config/binding/capture/model/publish fence, structured1+2 formalrun_once bridges, original Meter counts, old-profile/owner/stale/config/copy/NEEDS/cancel/UNKNOWN negatives; bridge not C producer/map acceptance')

if __name__=='__main__':harness.exercise=exercise;harness.main()
