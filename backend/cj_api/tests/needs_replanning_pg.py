"""#378 source2 through unpatched formal run_once/CLI and original signed APIs."""
import json,os,sys,subprocess
from pathlib import Path
from fastapi.testclient import TestClient
import local_history_pg as harness
from registered_host_support import RegisteredHost
from needs_creation_pg import fixed
from cj_api.local_app import LocalDatabase,create_local_app,load_confirmation_signer
from cj_api.local_plan_model import NeedsPlanFakeProvider,CurrentTripPlanFakeProvider
from cj_trip.local_needs_app import create_local_needs_app
from cj_trip.domain import packed
from cj_draft.needs_publisher import SYSTEM
sys.path.insert(0,str(harness.ROOT/'scripts'))
import dev_auth,run_worker


def exercise(auth,conninfo):
    subjects=['program','cli','invalid','stale','absent','foreign','unknown'];host=RegisteredHost(auth,conninfo,{s:(30,2,30000) for s in subjects})
    for s in subjects:dev_auth.activate_travel(conninfo,s,host.profiles[s][1],'MESSAGE-TRAVEL-CONSUMER@1')
    signer=load_confirmation_signer(auth)
    def app(s):return create_local_app(conninfo_path=conninfo,auth_dir=auth,run_context=host.profiles[s][1],travel_context=True,needs_profile='manual-v1',confirmation_signer=signer)
    def db(s):return LocalDatabase(conninfo,run_context=host.profiles[s][1],travel_context=True)
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
    for s in ('program','cli'):
        old=setup(s);r,raw=send(s,'replanning')
        if s=='program':
            model=CurrentTripPlanFakeProvider();outcome=run_worker.run_once(db(s),model,auth,draft_profile='needs-current-trip.1')[0]
            assert outcome.status=='completed' and outcome.proposal_id and model.calls==2
        else:
            result=subprocess.run([sys.executable,'-B',str(harness.ROOT/'scripts/run_worker.py'),'--conninfo-json',str(conninfo),'--auth-dir',str(auth),'--run-context',str(host.profiles[s][0]),'--travel-context','message-travel.1','--draft-profile','needs-current-trip.1','--once'],capture_output=True,text=True,env=dict(os.environ,CJ_ENV='local'),timeout=60)
            assert result.returncode==0,(result.stdout,result.stderr)
            assert 'local_provider_calls=2' in result.stdout and 'proposal=' in result.stdout
        with TestClient(needs(s)) as c:
            import hashlib
            d=discover(c,s,r);assert d['source_profile']=='TRIP-source-input.2'
            assert d['planning_context']==dict(trip_id=old['trip_id'],version=old['version'],content_sha256=hashlib.sha256(packed(old['content'])).hexdigest())
            assert d['proposal']['content']['items'][1]==old['content']['items'][1]
            accepted=accept(c,s,d,'adopt-replan');assert accepted['trip_id']!=old['trip_id'] and accepted['committed_version']==1
            assert read(c,s,old['trip_id'])==old
            assert read(c,s,accepted['trip_id'])['content']['items'][1]==old['content']['items'][1]
            recovered=harness.expect(c.get('/v1/trip-needs-action-receipts',params=dict(action_id='adopt-replan'),headers=host.headers[s]))['receipt'];assert recovered==accepted
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
    print('PASS378 actual signed API/restricted PG/unpatched run_once+CLI/Meter/C source2, original discovery/Signer/act/receipt, local fixed retention/new Trip vs original context; missing/stale/fixed/owner negatives')

if __name__=='__main__':harness.exercise=exercise;harness.main()
