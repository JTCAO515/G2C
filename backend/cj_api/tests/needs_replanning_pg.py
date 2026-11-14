"""#378 source2 through unpatched formal run_once/CLI and original signed APIs."""
import base64,json,os,sys,subprocess
from pathlib import Path
from fastapi.testclient import TestClient
import local_history_pg as harness
from registered_host_support import RegisteredHost
from needs_creation_pg import fixed
from cj_api.local_app import LocalDatabase,create_local_app,load_confirmation_signer,load_history_configuration,scope_for,ISSUER
from cj_api.local_plan_model import NeedsPlanFakeProvider,CurrentTripPlanFakeProvider
from cj_trip.local_needs_app import create_local_needs_app
from cj_trip.domain import packed
from cj_draft.needs_publisher import SYSTEM
sys.path.insert(0,str(harness.ROOT/'scripts'))
import dev_auth,run_worker


def exercise(auth,conninfo):
    demo='m4-synthetic-698-demo'
    subjects=['program','cli','invalid','stale','absent','foreign','unknown','changed-needs','changed-selection','cancel-queued','cancel-flight',demo];host=RegisteredHost(auth,conninfo,{s:(30,2,30000) for s in subjects})
    for s in subjects:dev_auth.activate_travel(conninfo,s,host.profiles[s][1],'MESSAGE-TRAVEL-CONSUMER@1')
    signer=load_confirmation_signer(auth)
    def app(s):return create_local_app(conninfo_path=conninfo,auth_dir=auth,run_context=host.profiles[s][1],travel_context=True,needs_profile='manual-v1',confirmation_signer=signer,history_configuration=load_history_configuration(auth))
    def db(s,*,needs_context=False):return LocalDatabase(conninfo,run_context=host.profiles[s][1],travel_context=True,needs_context=needs_context)
    def needs(s):return create_local_needs_app(conninfo_path=conninfo,auth_dir=auth,run_context=host.profiles[s][1],confirmation_signer=signer)
    def post(c,s,path,raw):return c.post(path,content=raw,headers={**host.headers[s],'Content-Type':'application/octet-stream'})
    namespaces={}
    def source(s):
        with TestClient(app(s)) as c:
            harness.expect(post(c,s,'/v1/needs-actions',packed(dict(action_id='source',needs_id='visit',expected_version=0,source=dict(kind='manual',text='Explicit source'),changes=dict(fixed_items=[fixed('a','09:00','10:00',True),fixed('b','11:00','12:00',False)])))))
            namespaces[s]=harness.expect(post(c,s,'/v1/travel-context-actions',packed(dict(version='TRAVEL-context-action.1',action_id='namespace',operation='create',travel_context=None))))['receipt']['travel_context']
    def send(s,key):
        with TestClient(app(s)) as c:
            h=harness.expect(c.put('/v1/conversations',params=dict(conversation_id=key),headers=host.headers[s]))
            raw=packed(dict(version='MESSAGE-send.2',conversation_id=key,message_id=key,text='Explicit replanning / 明确重新规划',trip_id=None,creation_intent='consider_trip',expected_generation=h['generation'],expected_sequence=0,travel_context=dict(id=namespaces[s]['id'],expected_version=1),needs_reference=dict(id='visit',expected_version=1)))
            return harness.expect(post(c,s,'/v2/messages',raw))['receipt'],raw
    def discover(c,s,r):return harness.expect(c.get('/v1/trip-needs-discovery',params=dict(message_id=r['message_id'],run_id=r['run_id']),headers=host.headers[s]))['discovery']
    def accept(c,s,d,aid):
        p=d['proposal'];raw=packed(dict(version='TRIP-needs-action.1',action_id=aid,kind='accept',proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash']))
        r=harness.expect(post(c,s,'/v1/trip-needs-actions',raw))['receipt']
        assert harness.expect(post(c,s,'/v1/trip-needs-actions',raw))['receipt']==r
        harness.expect(post(c,'foreign','/v1/trip-needs-actions',raw),503)
        return r
    def read(c,s,tid):return harness.expect(c.get('/v4/trip-structured',params=dict(trip_id=tid),headers=host.headers[s]))['trip']
    def original(s,receipt,raw):
        with TestClient(app(s)) as c:
            status=harness.expect(c.get('/v2/message-send-status',params=dict(conversation_id=receipt['conversation_id'],message_id=receipt['message_id']),headers=host.headers[s]))
            assert status['receipt']==receipt and status['reference']['input_sha256']==receipt['input_sha256']
            page=harness.expect(c.get('/v2/message-history',params=dict(conversation_id=receipt['conversation_id'],limit=10),headers=host.headers[s]))
            assert page['messages'][0]['receipt']==receipt and base64.b64decode(page['messages'][0]['original_utf8_base64'])==raw
            assert harness.expect(post(c,s,'/v2/messages',raw))['receipt']==receipt
    def no_basis(s,receipt):
        with db(s).connect(scope_for(ISSUER,s)) as c:
            assert c.execute('SELECT count(*) FROM cj_trip_needs_basis WHERE run_id=%s',(receipt['run_id'],)).fetchone()[0]==0
    def cancel(s,receipt):
        with TestClient(app(s)) as c:
            value=harness.expect(c.post('/v2/run-cancellations',json=dict(version='RUN-cancel.2',message_id=receipt['message_id']),headers=host.headers[s]))
            assert value['status']=='cancelled' and value['run_id']==receipt['run_id']
            return value
    def save(c,s,trip,key,*,fix=False,text=False):
        import hashlib
        changes=[dict(item_id='b',field='fixed',value=dict(state='known',value=True))] if fix else [dict(item_id='b',field='text',value='Explicit manually fixed choice')] if text else []
        raw=packed(dict(version='TRIP-needs-edit.1',needs_reference=dict(id='visit',expected_version=1),edit=dict(version='TRIP-manual-edit.2',request_id=key,trip_id=trip['trip_id'],expected_version=trip['version'],original_hash=hashlib.sha256(packed(trip['content'])).hexdigest(),title=None if fix or text else 'Actual intervening manual title',order=None,changes=changes)))
        prep=harness.expect(post(c,s,'/v1/trip-needs-edits',raw))['preparation']
        action=packed(dict(version='TRIP-needs-save.1',action_id='save-'+key,proposal_id=prep['proposal_id'],candidate_hash=prep['candidate_hash']))
        r=harness.expect(post(c,s,'/v1/trip-needs-saves',action))['receipt'];assert r['committed_version']==trip['version']+1
        return read(c,s,trip['trip_id'])
    def setup(s):
        source(s);receipt,_=send(s,'creation');model=NeedsPlanFakeProvider()
        assert run_worker.run_once(db(s),model,auth,draft_profile='needs-structured.1')[0].status=='completed' and model.calls==2
        with TestClient(needs(s)) as c:
            d=discover(c,s,receipt);assert d['source_profile']=='TRIP-source-input.1'
            first=accept(c,s,d,'adopt-original');trip=read(c,s,first['trip_id'])
            edited=save(c,s,trip,'edit-original',text=True)
            current=save(c,s,edited,'fixed-original',fix=True)
            assert current['version']==3 and current['content']['items'][1]['fixed']==dict(state='known',value=True)
            return current

    def check_demo_replanning():
        import httpx
        from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL
        from cj_api.real_services import RealServices,RealTools
        from cj_memory.typed_runtime import TypedRuntimeConfiguration
        from cj_usage.authorization_budget import AuthorizationBudget
        from test_m4_real_services import KEY,NOW,sse

        profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,
            semantic_resolved=True)},extents=['long_term'],context_ids=[])
        collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
            expires_at='2099-11-30T23:59:59+08:00',profiles={demo:profile}),travel_contexts={demo:[]})
        memory=TypedRuntimeConfiguration.from_bytes(packed(dict(version='local-memory-run.2',collection=collection,
            selections={demo:dict(subject='self',slots=['pace'],max_bytes=1000)})))
        owner=scope_for(ISSUER,demo); scopes=frozenset({owner}); database=db(demo,needs_context=True)
        draft_inputs=[]

        def response(request):
            body=json.loads(request.content)
            if body.get('tools'):
                phase='answer'
                answer='A fictional plan is ready for review.'
            else:
                phase='draft'
                original=json.loads(body['messages'][-1]['content'])
                draft_inputs.append(original)
                messages=body['messages'][1:]
                if original.get('current_trip') is not None:
                    planner=CurrentTripPlanFakeProvider()
                else:
                    planner=NeedsPlanFakeProvider()
                    messages[-1]=dict(role='system',content=json.dumps(dict(version='TRIP-source-input.1',fields=original['fields'])))
                answer=''.join(planner.stream(messages,system=SYSTEM))
            wire=sse().replace(json.dumps('{"zh":"待核实。","en":"Needs verification."}'),json.dumps(answer))
            wire=wire.replace('chatcmpl-synthetic',f'chatcmpl-demo-{len(draft_inputs)}-{phase}')
            return httpx.Response(200,stream=httpx.ByteStream(wire.encode()))

        budget=AuthorizationBudget(auth.parent/'demo-replanning-budget',clock=lambda:NOW)
        model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),budget,transport=httpx.MockTransport(response))
        services=RealServices(model,KEY,frozenset({demo}),demo_subjects=frozenset({demo}))
        options=dict(memory_configuration_for_scope=lambda _:memory,account_admission=True,real_services=services,
            tools_configuration=RealTools(services,buffered_streaming_subjects=frozenset({demo})))

        def run_planning(key,*,legacy=False):
            receipt,_=send(demo,key)
            selected={'hk_assembly_scopes':scopes} if legacy else {'hk_demo_scopes':scopes}
            outcome,=run_worker.run_once(database,model,auth,**options,**selected)
            assert outcome.status=='completed' and outcome.proposal_id=='p-'+receipt['run_id'],outcome
            assert run_worker.run_once(database,model,auth,**options,**selected)==[]
            return receipt,outcome.proposal_id

        source(demo)
        first,_=run_planning('demo-first')
        with TestClient(needs(demo)) as c:
            d=discover(c,demo,first)
            assert d['state']=='published' and d['planning_context'] is None
            assert draft_inputs[-1]['version']=='TRIP-source-input.2' and draft_inputs[-1]['current_trip'] is None
            accepted=accept(c,demo,d,'demo-adopt-first')
            current=save(c,demo,read(c,demo,accepted['trip_id']),'demo-edit-first')
            assert current['version']==2

        old,old_proposal=run_planning('demo-old-failed',legacy=True)
        assert draft_inputs[-1]['version']=='TRIP-source-input.1'
        with TestClient(needs(demo)) as c:
            original=harness.expect(c.get('/v2/trip-needs-proposals',params=dict(proposal_id=old_proposal),headers=host.headers[demo]))['proposal']
            conflict=harness.expect(c.get('/v1/trip-needs-discovery',params=dict(message_id=old['message_id'],run_id=old['run_id']),headers=host.headers[demo]),409)
            assert conflict['error']['code']=='TRIP_CONFLICT'
            action=packed(dict(version='TRIP-needs-action.1',action_id='demo-old-accept',kind='accept',proposal_id=old_proposal,candidate_hash=original['candidate_hash']))
            assert harness.expect(post(c,demo,'/v1/trip-needs-actions',action),409)['error']['code']=='TRIP_CONFLICT'

        fresh,_=run_planning('demo-replan')
        with TestClient(needs(demo)) as c:
            d=discover(c,demo,fresh)
            assert d['state']=='published' and d['source_profile']=='TRIP-source-input.2'
            assert (d['planning_context']['trip_id'],d['planning_context']['version'])==(current['trip_id'],2)
            captured=draft_inputs[-1]['current_trip']
            assert (captured['trip_id'],captured['version'],captured['content'])==(current['trip_id'],2,current['content'])
            accepted=accept(c,demo,d,'demo-adopt-replan')
            assert accepted['committed_version']==1 and accepted['trip_id']!=current['trip_id']
            assert read(c,demo,current['trip_id'])==current
            assert harness.expect(c.get('/v2/trip-needs-proposals',params=dict(proposal_id=old_proposal),headers=host.headers[demo]))['proposal']==original
            assert harness.expect(c.get('/v1/trip-needs-action-receipts',params=dict(action_id='demo-old-accept'),headers=host.headers[demo]))['receipt'] is None
        assert model.calls==6 and [a['state'] for a in budget.inspect()]==['RECEIVED']*6
        print('PASS #698 Demo first plan and same NEEDS Trip v2 replan through registered Meter, original discovery and accept; legacy pending conflict retained')

    check_demo_replanning()
    for s in ('program','cli'):
        old=setup(s);r,raw=send(s,'replanning')
        from cj_trip.planning_context import read_current
        from cj_trip.postgres import Repository
        from cj_agent.draft import trip_scope_for
        from cj_message.needs_binding import needs_scope_for
        owner=scope_for(ISSUER,s)
        captured=read_current(Repository(lambda:db(s).connect(owner),trip_scope_for(owner),structured=True),needs_scope_for(owner),'visit')
        if s=='program':
            model=CurrentTripPlanFakeProvider();outcome=run_worker.run_once(db(s),model,auth,draft_profile='needs-current-trip.1')[0]
            assert outcome.status=='completed' and outcome.proposal_id and model.calls==2
        else:
            result=subprocess.run([sys.executable,'-B',str(harness.ROOT/'scripts/run_worker.py'),'--conninfo-json',str(conninfo),'--auth-dir',str(auth),'--run-context',str(host.profiles[s][0]),'--travel-context','message-travel.1','--draft-profile','needs-current-trip.1','--once'],capture_output=True,text=True,env=dict(os.environ,CJ_ENV='local'),timeout=60)
            assert result.returncode==0,(result.stdout,result.stderr)
            assert 'local_provider_calls=2' in result.stdout and 'proposal=' in result.stdout
        with db(s).connect(owner) as c:
            rows=c.execute("SELECT input_bytes FROM cj_run_metered_operation WHERE run_id=%s AND registration_id='model.draft'",(r['run_id'],)).fetchall()
            assert len(rows)==1
            invocation=json.loads(bytes(rows[0][0]));source_input=json.loads(invocation['messages'][-1]['content'])
            assert invocation['system']==SYSTEM and source_input['version']=='TRIP-source-input.2'
            assert source_input['current_trip']==dict(trip_id=captured.trip.trip_id,version=captured.trip.version,content=json.loads(captured.trip.content),proposed_fields=json.loads(captured.proposed))
        with TestClient(needs(s)) as c:
            import hashlib
            d=discover(c,s,r);assert d['source_profile']=='TRIP-source-input.2'
            assert d['planning_context']==dict(trip_id=old['trip_id'],version=old['version'],content_sha256=hashlib.sha256(packed(old['content'])).hexdigest())
            assert d['proposal']['content']['items'][1]==old['content']['items'][1]
            accepted=accept(c,s,d,'adopt-replan');assert accepted['trip_id']!=old['trip_id'] and accepted['committed_version']==1
            assert read(c,s,old['trip_id'])==old
            assert read(c,s,accepted['trip_id'])['content']['items'][1]==old['content']['items'][1]
            recovered=harness.expect(c.get('/v1/trip-needs-action-receipts',params=dict(action_id='adopt-replan'),headers=host.headers[s]))['receipt'];assert recovered==accepted
        original(s,r,raw)
        assert run_worker.run_once(db(s),CurrentTripPlanFakeProvider(),auth,draft_profile='needs-current-trip.1')==[]
    source('absent');send('absent','no-current')
    model=CurrentTripPlanFakeProvider();outcome=run_worker.run_once(db('absent'),model,auth,draft_profile='needs-current-trip.1')[0]
    assert outcome.proposal_id is None and model.calls==1
    old=setup('invalid');r,_=send('invalid','break-fixed')
    class Invalid(CurrentTripPlanFakeProvider):
        def stream(self,messages,system=None):
            for chunk in super().stream(messages,system):
                if system==SYSTEM:
                    value=json.loads(chunk);value['items'][1]['text']='Model overwrote fixed';yield packed(value).decode()
                else:yield chunk
    model=Invalid();outcome=run_worker.run_once(db('invalid'),model,auth,draft_profile='needs-current-trip.1')[0]
    assert outcome.proposal_id is None and model.calls==2
    with TestClient(needs('invalid')) as c:assert read(c,'invalid',old['trip_id'])==old and discover(c,'invalid',r)['state']=='no_candidate'
    old=setup('stale');r,_=send('stale','old-context')
    class Stale(CurrentTripPlanFakeProvider):
        def stream(self,messages,system=None):
            for chunk in super().stream(messages,system):
                if system==SYSTEM:
                    yield ''
                    with TestClient(needs('stale')) as c:save(c,'stale',old,'intervening')
                yield chunk
    model=Stale();outcome=run_worker.run_once(db('stale'),model,auth,draft_profile='needs-current-trip.1')[0]
    assert outcome.proposal_id is None and outcome.status in ('unknown','context_invalid') and model.calls==2
    old=setup('unknown');r,_=send('unknown','unknown-original')
    from cj_agent.provider import ProviderUnknown
    class Unknown(CurrentTripPlanFakeProvider):
        def stream(self,messages,system=None):
            if system==SYSTEM:
                self.calls+=1;raise ProviderUnknown('controlled original source2 draft exposure');yield
            yield from super().stream(messages,system)
    model=Unknown();outcome=run_worker.run_once(db('unknown'),model,auth,draft_profile='needs-current-trip.1')[0]
    assert outcome.proposal_id is None and model.calls==2
    with TestClient(needs('unknown')) as c:assert discover(c,'unknown',r)['state']=='unknown' and read(c,'unknown',old['trip_id'])==old
    assert run_worker.run_once(db('unknown'),model,auth,draft_profile='needs-current-trip.1')==[] and model.calls==2
    old=setup('changed-needs');r,raw=send('changed-needs','needs-currentness')
    class ChangedNeeds(CurrentTripPlanFakeProvider):
        def stream(self,messages,system=None):
            for chunk in super().stream(messages,system):
                if system==SYSTEM:
                    yield ''
                    with TestClient(app('changed-needs')) as c:
                        harness.expect(post(c,'changed-needs','/v1/needs-actions',packed(dict(action_id='correct-needs',needs_id='visit',expected_version=1,source=dict(kind='manual',text='Explicit correction'),changes=dict(party_size=dict(state='known',value=2))))))
                yield chunk
    model=ChangedNeeds();outcome=run_worker.run_once(db('changed-needs'),model,auth,draft_profile='needs-current-trip.1')[0]
    assert outcome.proposal_id is None and outcome.status in ('unknown','context_invalid') and model.calls==2
    no_basis('changed-needs',r);original('changed-needs',r,raw)
    with TestClient(needs('changed-needs')) as c:assert read(c,'changed-needs',old['trip_id'])==old
    old=setup('changed-selection');first,_=send('changed-selection','selection-candidate')
    assert run_worker.run_once(db('changed-selection'),CurrentTripPlanFakeProvider(),auth,draft_profile='needs-current-trip.1')[0].proposal_id
    with TestClient(needs('changed-selection')) as c:pending=discover(c,'changed-selection',first)
    r,raw=send('changed-selection','selection-currentness')
    class ChangedSelection(CurrentTripPlanFakeProvider):
        def stream(self,messages,system=None):
            for chunk in super().stream(messages,system):
                if system==SYSTEM:
                    yield ''
                    with TestClient(needs('changed-selection')) as c:
                        selected=accept(c,'changed-selection',pending,'select-new-plan')
                        assert selected['trip_id']!=old['trip_id'] and read(c,'changed-selection',old['trip_id'])==old
                yield chunk
    model=ChangedSelection();outcome=run_worker.run_once(db('changed-selection'),model,auth,draft_profile='needs-current-trip.1')[0]
    assert outcome.proposal_id is None and outcome.status in ('unknown','context_invalid') and model.calls==2
    no_basis('changed-selection',r);original('changed-selection',r,raw)
    for s in ('cancel-queued','cancel-flight'):
        old=setup(s);r,raw=send(s,'cancel-original')
        class Cancelling(CurrentTripPlanFakeProvider):
            def stream(self,messages,system=None):
                for chunk in super().stream(messages,system):
                    if system==SYSTEM:
                        yield '';cancel(s,r)
                    yield chunk
        model=Cancelling()
        if s=='cancel-queued':cancel(s,r)
        outcome=run_worker.run_once(db(s),model,auth,draft_profile='needs-current-trip.1')[0]
        assert outcome.status=='cancelled' and outcome.proposal_id is None and model.calls==(0 if s=='cancel-queued' else 2)
        before=model.calls;assert run_worker.run_once(db(s),model,auth,draft_profile='needs-current-trip.1')==[] and model.calls==before
        no_basis(s,r);original(s,r,raw)
        with TestClient(needs(s)) as c:assert read(c,s,old['trip_id'])==old
    # The draft's accepted Trip is appended after the first answer model. B must
    # augment C's original capture at this actual second-model boundary.
    from datetime import datetime,timedelta,timezone
    from unittest.mock import patch
    from cj_memory.typed_api import create_local_typed_app
    from cj_memory.typed_local import TypedConfiguration
    from cj_memory.typed_runtime import TypedRuntimeConfiguration
    from cj_api.local_memory_history import read_original_digest
    deadline=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
                 extents=['long_term'],context_ids=[])
    typed=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=deadline,
               profiles={'program':profile}),travel_contexts={'program':[]})
    configuration=TypedRuntimeConfiguration.from_bytes(packed(dict(version='local-memory-run.2',collection=typed,
                    selections={'program':dict(subject='self',slots=['pace'],max_bytes=32768)})))
    with TestClient(create_local_typed_app(conninfo_path=conninfo,auth_dir=auth,configuration=TypedConfiguration.from_bytes(packed(typed)))) as c:
        manual=packed(dict(version='MEMORY-manual.2',operation_id='history-memory',item_id='history-memory',subject='self',slot='pace',
            kind='preference',text='Keep a slow pace',extent='long_term',context=None,occurred_at='date unknown'))
        harness.expect(post(c,'program','/v2/memories',manual))
    r,raw=send('program','memory-source2')
    model=CurrentTripPlanFakeProvider()
    with patch('cj_api.local_memory_history.read_original_digest',wraps=read_original_digest) as reads:
        outcome=run_worker.run_once(db('program'),model,auth,memory_configuration=configuration,draft_profile='needs-current-trip.1')[0]
    assert outcome.status=='completed' and outcome.proposal_id and model.calls==2,outcome
    assert reads.call_count==1,reads.call_args_list
    assert reads.call_args.args[4].trip_id and reads.call_args.args[4].content_sha256
    with db('program').connect(scope_for(ISSUER,'program')) as c:
        rows=c.execute("SELECT input_bytes FROM cj_run_metered_operation WHERE run_id=%s AND registration_id='model.draft'",(r['run_id'],)).fetchall()
        invocation=json.loads(bytes(rows[0][0]));assert json.loads(invocation['messages'][-1]['content'])['current_trip'] is not None
        assert 'Keep a slow pace' in invocation['messages'][0]['content']
    original('program',r,raw)
    print('PASS real source2 second model augments original C History Memory via genuine accepted-decision fence; original capture retained, two real Meter/Fake calls and publication completed')
    print('PASS378 actual signed API/restricted PG/unpatched run_once+CLI/Meter/C source2, original discovery/Signer/act/receipt/bytes, local fixed retention/new Trip vs original context; missing/stale/fixed/owner/NEEDS/selection/cancel/UNKNOWN negatives')

if __name__=='__main__':harness.exercise=exercise;harness.main()
