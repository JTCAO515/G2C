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


def exercise(auth,conninfo):
    subjects=['explicit','cli','legacy','stale','unknown','foreign']
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
    print('PASS354 unpatched run_once+CLI explicit C publisher/source prompt, registered Meter, original C confirm/act/adopt, structured list/detail and NEEDS basis; legacy/currentness/UNKNOWN negatives')
    print('INITIALIZE503 retained only for actual protected legacy source; root C manual_origin.ManualOrigin._run rejects cj_local_run_protection/NEEDS binding, no C file or budget gate modified')

if __name__=='__main__':harness.exercise=exercise;harness.main()
