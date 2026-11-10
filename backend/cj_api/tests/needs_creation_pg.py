"""#354 actual unpatched run_once/CLI creation and original C confirm/read flow."""
import base64,json,os,sys,subprocess,time
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import psycopg
import local_history_pg as harness
from cj_api.local_app import LocalDatabase,create_local_app,load_confirmation_signer,scope_for,ISSUER
from cj_api.local_plan_model import NeedsPlanFakeProvider
from cj_api.composition import CompositionUnavailable
from cj_agent.provider import FakeProvider,ProviderUnknown
from cj_trip.domain import packed
from cj_trip.local_needs_app import create_local_needs_app
from cj_trip.local_manual_app import create_local_manual_app
from cj_trip.local_structured_read import create_local_structured_read_app
from cj_agent.draft import trip_scope_for
sys.path[:0]=[str(harness.ROOT/'scripts'),str(harness.ROOT/'backend/draft/tests')]
import dev_auth,run_worker
from registered_host_support import RegisteredHost


def fixed(key,start,end,locked):
    def known(value):return dict(state='known',value=value)
    def event(clock):return dict(date=known('2026-11-02'),time=known(clock),timezone=known('Asia/Shanghai'),place=dict(state='unknown'))
    return dict(item_id=key,kind='appointment',description='explicit original '+key,applies_to=['self'],locked=known(locked),booking_status=known('booked'),start=event(start),end=event(end))


def check_assembly_run_credential(auth,host,database,setup,pair):
    from datetime import datetime,timedelta,timezone
    from types import SimpleNamespace
    import httpx
    from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL
    from cj_agent.worker import RunWorker
    from cj_api.real_services import RealServices,RealTools
    from cj_auth.admission import AdmissionChecker
    from cj_draft.needs_publisher import SYSTEM
    from cj_memory.typed_runtime import TypedRuntimeConfiguration
    from cj_usage.authorization_budget import AuthorizationBudget
    from test_m4_real_services import KEY,NOW,sse,turn_sse

    profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,
        semantic_resolved=True)},extents=['long_term'],context_ids=[])
    collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at='2099-11-30T23:59:59+08:00',profiles=dict.fromkeys(pair,profile)),travel_contexts={s:[] for s in pair})
    memory=TypedRuntimeConfiguration.from_bytes(packed(dict(version='local-memory-run.2',collection=collection,
        selections={s:dict(subject='self',slots=['pace'],max_bytes=1000) for s in pair})))
    scopes=frozenset(scope_for(ISSUER,s) for s in pair)
    offset=0

    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):
            return datetime.now(tz)+timedelta(seconds=offset)

    def clock():return Clock.now(timezone.utc).timestamp()

    initialize=AdmissionChecker.__init__
    def checker(instance,verifier,access):
        initialize(instance,verifier,access,clock=clock)

    original_step=RunWorker._step
    def after_draft_receipt(worker,binding,invoke,effect=None,*,draft=False):
        nonlocal offset
        if draft and effect is not None:offset=301
        return original_step(worker,binding,invoke,effect,draft=draft)

    for subject,enabled in zip(pair,(False,True)):
        offset=0
        original,_=setup(subject)
        receipt=original['receipt']
        def response(request):
            body=json.loads(request.content)
            if body.get('tools'):
                wire=turn_sse(compact=True)
                response_id=subject+'-answer'
            else:
                plan=''.join(NeedsPlanFakeProvider().stream(body['messages'][1:],system=SYSTEM))
                wire=sse().replace(json.dumps('{"zh":"待核实。","en":"Needs verification."}'),json.dumps(plan))
                response_id=subject+'-draft'
            return httpx.Response(200,stream=httpx.ByteStream(wire.replace('chatcmpl-synthetic',response_id).encode()))
        budget=AuthorizationBudget(auth.parent/(subject+'-budget'),clock=lambda:NOW)
        model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),budget,transport=httpx.MockTransport(response))
        services=RealServices(model,KEY,frozenset(pair))
        db=database(subject)
        options=dict(memory_configuration_for_scope=lambda _:memory,tools_configuration=RealTools(services),
            real_services=services,account_admission=True,hk_assembly_scopes=scopes,
            hk_assembly_run_credential_scopes=scopes if enabled else frozenset())
        with patch('jwt.api_jwt.datetime',Clock),patch.object(AdmissionChecker,'__init__',checker), \
                patch.object(dev_auth,'time',SimpleNamespace(time=clock)),patch.object(RunWorker,'_step',after_draft_receipt):
            outcome,=run_worker.run_once(db,model,auth,**options)
            assert run_worker.run_once(db,model,auth,**options)==[]
        assert offset==301 and outcome.run_id==receipt['run_id']
        assert (outcome.status,outcome.proposal_id)==(
            ('completed','p-'+receipt['run_id']) if enabled else ('context_invalid',None))
        attempts=budget.inspect()
        assert [row['state'] for row in attempts]==['RECEIVED','RECEIVED']
        ledger=host.ledger(subject)
        assert all(ledger.attempts[row['attempt_id']].receipt is not None for row in attempts)
        with db.connect(scope_for(ISSUER,subject)) as connection:
            assert connection.execute('SELECT acknowledged FROM cj_message_delivery WHERE run_id=%s',
                (receipt['run_id'],)).fetchone()==(True,)
    print('PASS #674 opt-in original assembly draft publishes after 301s with its original Meter and ACK; default fails closed')


def exercise(auth,conninfo):
    pair=('m4-synthetic-660-0123456789ab-zh','m4-synthetic-660-0123456789ab-en')
    subjects=['explicit','cli','legacy','stale','unknown','foreign',*pair]
    host=RegisteredHost(auth,conninfo,{s:(12,2,30000) for s in subjects})
    for s in subjects:dev_auth.activate_travel(conninfo,s,host.profiles[s][1],'MESSAGE-TRAVEL-CONSUMER@1')
    signer=load_confirmation_signer(auth);cfg=json.loads(conninfo.read_text())
    def database(s):return LocalDatabase(conninfo,run_context=host.profiles[s][1],travel_context=True,needs_context=True)
    def app(s):return create_local_app(conninfo_path=conninfo,auth_dir=auth,run_context=host.profiles[s][1],travel_context=True,needs_profile='manual-v1',confirmation_signer=signer)
    def setup(s):
        with TestClient(app(s)) as client:
            h=host.headers[s];typed={**h,'Content-Type':'application/octet-stream'}
            needs=packed(dict(action_id='source-'+s,needs_id='visit',expected_version=0,source=dict(kind='manual',text='explicit original constraints'),changes=dict(fixed_items=[fixed('a','09:00','10:00',True),fixed('b','11:00','12:00',False)])))
            harness.expect(client.post('/v1/needs-actions',content=needs,headers=typed))
            namespace=harness.expect(client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id='namespace',operation='create',travel_context=None)),headers=typed))['receipt']['travel_context']
            head=harness.expect(client.put('/v1/conversations',params=dict(conversation_id=s),headers=h))
            raw=packed(dict(version='MESSAGE-send.2',conversation_id=s,message_id='message-'+s,text='按明确条件安排 / use original constraints',trip_id=None,creation_intent='consider_trip',expected_generation=head['generation'],expected_sequence=0,travel_context=dict(id=namespace['id'],expected_version=1),needs_reference=dict(id='visit',expected_version=1)))
            return harness.expect(client.post('/v2/messages',content=raw,headers=typed)),raw
    def accept(s,outcome):
        context=host.profiles[s][1]
        with TestClient(create_local_needs_app(conninfo_path=conninfo,auth_dir=auth,run_context=context,confirmation_signer=signer)) as client:
            h=host.headers[s];detail=harness.expect(client.get('/v2/trip-needs-proposals',params=dict(proposal_id=outcome.proposal_id),headers=h))['proposal']
            original=packed(dict(version='TRIP-needs-action.1',action_id='accept-'+s,kind='accept',proposal_id=outcome.proposal_id,candidate_hash=detail['candidate_hash']))
            receipt=harness.expect(client.post('/v1/trip-needs-actions',content=original,headers={**h,'Content-Type':'application/octet-stream'}))['receipt']
            assert harness.expect(client.post('/v1/trip-needs-actions',content=original,headers={**h,'Content-Type':'application/octet-stream'}))['receipt']==receipt
            harness.expect(client.post('/v1/trip-needs-actions',content=original,headers={**host.headers['foreign'],'Content-Type':'application/octet-stream'}),503)
        with TestClient(create_local_structured_read_app(conninfo_path=conninfo,auth_dir=auth,run_context=context)) as client:
            listed=harness.expect(client.get('/v1/trip-structured-list',headers=host.headers[s]));assert listed['trips'][0]['trip_id']==receipt['trip_id']
            trip=harness.expect(client.get('/v5/trip-structured',params=dict(trip_id=receipt['trip_id']),headers=host.headers[s]))['trip']
            assert trip['version']==1 and trip['content']['content_version']=='structured.2'
            assert trip['content']['items'][0]['schedule']['start']['time']==dict(state='known',value='09:00')
            assert trip['content']['items'][0]['schedule']['start']['timezone']==dict(state='known',value='Asia/Shanghai')
            assert trip['content_sha256']==__import__('hashlib').sha256(packed(trip['content'])).hexdigest()
        with database(s).connect(scope_for(ISSUER,s)) as c:
            basis=c.execute('SELECT needs_id,needs_version,source_input FROM cj_trip_needs_basis WHERE scope=%s AND proposal_id=%s',(trip_scope_for(scope_for(ISSUER,s)),outcome.proposal_id)).fetchone()
            assert basis[:2]==('visit',1) and json.loads(bytes(basis[2]))['reference']['message_id']=='message-'+s
            assert c.execute('SELECT trip_id,trip_version FROM cj_trip_needs_current').fetchone()==(receipt['trip_id'],1)
        return trip
    # New explicit factory: no worker mutation or direct process invocation.
    original,raw=setup('explicit');model=NeedsPlanFakeProvider()
    outcomes=run_worker.run_once(database('explicit'),model,auth,draft_profile='needs-structured.1')
    assert outcomes[0].status=='completed' and outcomes[0].proposal_id and model.calls==2
    trip=accept('explicit',outcomes[0])
    assert run_worker.run_once(database('explicit'),model,auth,draft_profile='needs-structured.1')==[] and model.calls==2
    # Boot the hosted API on the private PG transport with the existing local cleanup login.
    from cj_api.local_cleanup import Configuration,Runtime as LocalCleanup
    from cj_memory.typed_local import TypedConfiguration
    sys.path.insert(0,str(harness.ROOT))
    from deploy.hk import configuration

    selected=frozenset({'explicit'})
    profile=dict(subjects=['self'],slots={'preference':dict(kind='preference',
        collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    policy=TypedConfiguration.from_bytes(packed(dict(version='local-memory-typed.1',
        collection=dict(version='local-memory-policy.1',expires_at='2099-11-30T23:59:59+08:00',
            profiles={'explicit':profile, 'cli':profile}),travel_contexts={'explicit':[], 'cli':[]})))
    cleanup=Configuration({'fixture':b'c'*32},'fixture',3600,('business/message',),
        harness.ROOT/'backend/storage-registry.json')
    path,context=host.profiles['explicit']
    db=database('explicit')
    runtime=configuration.Runtime(auth,context,path,[],typed_memory=policy,
        subjects=frozenset(host.subjects),typed_message_subjects=selected,assembly_subjects=selected,
        demo_subjects=frozenset({'cli'}))
    env=dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1',CJ_BETA_HISTORY_B64=base64.b64encode(b'h'*32).decode(),
        CJ_BETA_CONFIRMATION_B64=base64.b64encode(b'c'*32).decode())
    with patch.dict(os.environ,env),patch.object(configuration.Runtime,'database',return_value=db), \
            patch.object(configuration,'assembly_cleanup',return_value=cleanup), \
            patch('cj_api.supabase_cleanup.SupabaseCleanupRuntime',return_value=LocalCleanup(db,cleanup,scope_for)):
        composed=runtime.app()
    with TestClient(composed) as client:
        headers={**host.headers['explicit'],'Content-Type':'application/octet-stream'}
        foreign=host.headers['foreign']
        demo=host.headers['cli']
        erasure_path='/v1/memory-erasure-progress'
        erasure_query=dict(action_id='not-started')
        admitted=harness.expect(client.get(erasure_path,params=erasure_query,headers=demo),503)
        assert admitted['error']['code']=='ERASURE_UNAVAILABLE'
        harness.expect(client.get(erasure_path,params=erasure_query,headers=foreign),403)
        harness.expect(client.get('/v1/account-cleanup-preparations',params=erasure_query,headers=demo),403)
        stream=client.get('/v2/run-events',params={'message_id':'message-explicit'},headers=headers)
        assert stream.status_code==200 and b'"status":"completed"' in stream.content
        selection=dict(trip_id=trip['trip_id'])
        harness.expect(client.get('/v5/trip-structured',params=selection,headers=foreign),503)
        assert harness.expect(client.get('/v5/trip-structured',params=selection,headers=headers))['trip']==trip
        body=packed(dict(version='TRIP-needs-edit.1',needs_reference=dict(id='visit',expected_version=1),
            edit=dict(version='TRIP-manual-edit.2',request_id='assembly-edit',trip_id=trip['trip_id'],
                expected_version=1,original_hash=trip['content_sha256'],title='Assembly title',changes=[],order=None)))
        preparation=harness.expect(client.post('/v1/trip-needs-edits',content=body,headers=headers))['preparation']
        body=packed(dict(version='TRIP-needs-save.1',action_id='assembly-save',
            proposal_id=preparation['proposal_id'],candidate_hash=preparation['candidate_hash']))
        receipt=harness.expect(client.post('/v1/trip-needs-saves',content=body,headers=headers))['receipt']
        assert receipt['committed_version']==2
        result=harness.expect(client.get('/v5/trip-structured',params=selection,headers=headers))['trip']
        assert result['version']==2 and result['content']['title']=='Assembly title'
        assert harness.expect(client.get('/v1/trip-needs-action-receipts',
            params=dict(action_id='assembly-save'),headers=headers))['receipt']==receipt
        harness.expect(client.post('/v1/trip-source-initializations',content=b'',headers=headers),404)
        original=auth/'invited.json'
        saved=original.read_bytes()
        try:
            original.write_text(json.dumps(sorted(set(host.subjects)-selected)))
            harness.expect(client.get('/v5/trip-structured',params=selection,headers=headers),503)
            harness.expect(client.get('/v1/memory-erasure-progress',params={'action_id':'assembly-erase'},headers=headers),403)
            harness.expect(client.get('/v1/account-cleanup-preparations',params={'action_id':'assembly-cleanup'},headers=headers),403)
        finally:
            original.write_bytes(saved)
    # Actual CLI selects the source-compatible offline model; same source/B Meter.
    setup('cli')
    env=dict(os.environ,CJ_ENV='local')
    result=subprocess.run([sys.executable,'-B',str(harness.ROOT/'scripts/run_worker.py'),'--conninfo-json',str(conninfo),'--auth-dir',str(auth),'--run-context',str(host.profiles['cli'][0]),'--travel-context','message-travel.1','--draft-profile','needs-structured.1','--once'],env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert 'local_provider_calls=2' in result.stdout and 'proposal=p-' in result.stdout
    with database('cli').connect(scope_for(ISSUER,'cli')) as c:
        row=c.execute('SELECT run_id FROM cj_run_record').fetchone();pid='p-'+row[0]
    from types import SimpleNamespace
    accept('cli',SimpleNamespace(proposal_id=pid))
    # Default is still genuinely legacy with no source basis.
    setup('legacy');legacy_model=FakeProvider();legacy=run_worker.run_once(database('legacy'),legacy_model,auth)[0]
    assert legacy.status=='completed' and legacy.proposal_id and legacy_model.calls==2
    with TestClient(app('legacy')) as client:
        snapshot=harness.expect(client.get('/v1/trip-proposals',params=dict(proposal_id=legacy.proposal_id),headers=host.headers['legacy']))['proposal']
        assert snapshot['document'].get('content_version') is None
        prepared=harness.expect(client.post('/v1/trip-confirmations',json=dict(action_id='legacy-accept',kind='accept',proposal_id=legacy.proposal_id,candidate_hash=snapshot['candidate_hash']),headers=host.headers['legacy']))
        action=base64.b64decode(prepared['action_utf8_base64'])
        receipt=harness.expect(client.post('/v1/trip-actions',content=action,headers={**host.headers['legacy'],'Content-Type':'application/octet-stream'}))['receipt']
    with database('legacy').connect(scope_for(ISSUER,'legacy')) as c:
        assert c.execute('SELECT count(*) FROM cj_trip_needs_basis').fetchone()[0]==0
    # INITIALIZE's original protected-legacy rejection is C's deliberate source gate.
    with TestClient(create_local_manual_app(conninfo_path=conninfo,auth_dir=auth,run_context=host.profiles['legacy'][1],confirmation_signer=signer)) as client:
        old=snapshot['document'];unknown=dict(state='unknown');point={k:unknown for k in ('date','time','timezone','utc_offset')}
        initialize=packed(dict(version='TRIP-initialize.1',request_id='legacy-initialize',trip_id=receipt['trip_id'],expected_version=1,original_hash=__import__('hashlib').sha256(packed(old)).hexdigest(),items=[dict(id=v['id'],schedule=dict(start=point,end=point),fixed=unknown) for v in old['items']]))
        denied=harness.expect(client.post('/v1/trip-structured-initializations',content=initialize,headers={**host.headers['legacy'],'Content-Type':'application/octet-stream'}),503)
        assert denied['error']['code']=='TRIP_ACCESS_UNAVAILABLE'
    # Currentness in actual unpatched entry: changing NEEDS during model refuses publish.
    setup('stale')
    class Changed(NeedsPlanFakeProvider):
        def stream(self,messages,system=None):
            from cj_draft.needs_publisher import SYSTEM
            if system==SYSTEM:
                with TestClient(app('stale')) as client:harness.expect(client.post('/v1/needs-actions',content=packed(dict(action_id='advance',needs_id='visit',expected_version=1,source=dict(kind='manual',text='new explicit source'),changes=dict(party_size=dict(state='known',value=2)))),headers={**host.headers['stale'],'Content-Type':'application/octet-stream'}))
            yield from super().stream(messages,system)
    rejected=run_worker.run_once(database('stale'),Changed(),auth,draft_profile='needs-structured.1')[0];assert rejected.proposal_id is None and rejected.status=='context_invalid'
    setup('unknown')
    class Unknown(NeedsPlanFakeProvider):
        def stream(self,messages,system=None):self.calls+=1;raise ProviderUnknown('controlled outbound unknown');yield
    model=Unknown();assert run_worker.run_once(database('unknown'),model,auth,draft_profile='needs-structured.1')[0].status=='unknown' and model.calls==1
    assert run_worker.run_once(database('unknown'),model,auth,draft_profile='needs-structured.1')==[] and model.calls==1
    check_assembly_run_credential(auth,host,database,setup,pair)
    print('PASS354 unpatched run_once+CLI explicit C publisher/source prompt, registered Meter, original C confirm/act/adopt, structured list/detail and NEEDS basis; legacy/currentness/UNKNOWN negatives')
    print('INITIALIZE503 retained only for actual protected legacy source; root C manual_origin.ManualOrigin._run rejects cj_local_run_protection/NEEDS binding, no C file or budget gate modified')

if __name__=='__main__':harness.exercise=exercise;harness.main()
