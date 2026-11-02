"""Prototype registered current-Memory extraction through the genuine joint lease."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json,os,sys,tempfile,time
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import LocalDatabase,create_local_app,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.local_background import LocalBackgroundHost,FilteredCollectionAdapter
from cj_agent.provider import FakeProvider
from cj_memory.manual import ManualPolicy
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.collection_app import create_collection_app
from cj_message.source import SourceQuery
from cj_message.travel import ABI as TRAVEL_ABI,Selection
from cj_run.background import BackgroundJobs
from cj_run.background_store import JobRequest
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,local_run_context,run_worker


class CurrentFake(FakeProvider):
    def stream(self,messages,system=None):
        self.calls+=1;value=json.loads(messages[0]['content'])
        assert value['version']=='MEMORY-EXTRACT-DATA@2'
        message=value['messages'][0];assert set(message)=={'ref','text'}
        yield json.dumps(dict(version='MEMORY-EXTRACT@2',entries=[dict(subject='self',slot='mobility',kind='preference',
            text=message['text'],extent='current',occurred_at='date unknown',evidence=[dict(ref=message['ref'],quote=message['text'])])]))


def exercise(root,path):
    auth=root/'auth';dev_auth.init(auth,['bg-current']);now=int(time.time())
    quota=root/'quota.json';quota.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
        meter=dict(unit='provider_call',budget=10,period_start=now-60,period_end=now+3600,max_steps=10,max_tools=5,max_output=20000,max_seconds=600),output_limits=dict(model=3000,tool=3000,memory=3000)))))
    context=load_run_context(quota);local_run_context.provision_budget(path,context,'bg-current')
    dev_auth.activate_travel(path,'bg-current',context,TRAVEL_ABI)
    database=LocalDatabase(path,run_context=context,travel_context=True);token=dev_auth.token(auth,'bg-current',30)
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
    app=create_local_app(conninfo_path=path,auth_dir=auth,run_context=context,travel_context=True)
    with TestClient(app) as client:
        def post(url,value):
            response=client.post(url,content=json.dumps(value).encode(),headers=headers)
            assert response.status_code==200,('current HTTP status',response.status_code)
            return response.json()
        travel=post('/v1/travel-context-actions',dict(version='TRAVEL-context-action.1',action_id='travel',operation='create',travel_context=None))['receipt']['travel_context']
        head=client.put('/v1/conversations',params={'conversation_id':'current'},headers=headers).json()
        for index,text in enumerate(('This trip avoid stairs','This trip use a slow pace')):
            post('/v2/messages',dict(version='MESSAGE-send.2',conversation_id='current',message_id='typed-'+str(index),text=text,trip_id=None,
                creation_intent='none',expected_generation=head['generation'],expected_sequence=index,needs_reference=None,
                travel_context=dict(id=travel['id'],expected_version=travel['version'])))
        normal=FakeProvider();run_worker.run_once(database,normal,auth);assert normal.calls==2
        slots=frozenset({'mobility'});policy=CollectionPolicy(frozenset({'self'}),slots,10,4096,lambda entry:True,lambda entry,rows:any(entry.text==row.text for row in rows))
        memory=ManualPolicy(policy.subjects,slots,frozenset({'current'}),frozenset({travel['id']}),datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:True,lambda command,raw:True)
        c_app=create_collection_app(conninfo_path=path,auth_dir=auth,resolve_collection=lambda p:(policy,memory,lambda entry:(None,None)),run_context=context)
        host=c_app.state.memory_history;c=host.service
        c.apply_consent(token,json.dumps(dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='current',expected_generation=head['generation'],expected_epoch=0,expected_source_version=0)).encode())
        jobs=BackgroundJobs(database=host.database,boundary=host.boundary,collection=FilteredCollectionAdapter(c),max_payload_bytes=262144)
        source=dict(conversation_id='current',generation=head['generation'],epoch=0,after=0,through=1,source_version=1,withdrawal_epoch=1,mode='incremental')
        def prepare(jid,query):
            c.enqueue(token,json.dumps(dict(version='MEMORY-JOBS@1',job_id=jid,attempt_id=jid+'-attempt',source=query)).encode())
            c.transition(token,jid,jid+'-attempt','inflight')
            prepared=c.prepare_model_input_v2(token,jid,jid+'-attempt',max_payload_bytes=262144)
            return jobs.prepare(token,JobRequest(jid,jid+'-attempt',SourceQuery(**query),Selection(travel['id'],travel['version']),prepared))
        original=prepare('current-job',source);model=CurrentFake()
        result=run_worker.run_once(database,model,auth,background_jobs=LocalBackgroundHost(jobs,auth))
        assert len(result)==1 and result[0].status=='completed' and model.calls==1,result
        with psycopg.connect(**json.loads(path.read_text())) as conn:
            owner=scope_for(ISSUER,'bg-current')
            assert conn.execute("SELECT context_kind,context_id,status FROM cj_memory_item WHERE scope=%s",(owner,)).fetchall()==[('travel',travel['id'],'active')]
        stale=prepare('stale-job',source|dict(after=1,through=2))
        post('/v1/travel-context-actions',dict(version='TRAVEL-context-action.1',action_id='advance',operation='advance',travel_context=dict(id=travel['id'],expected_version=travel['version'])))
        stale_model=CurrentFake();outcome=run_worker.run_once(database,stale_model,auth,background_jobs=LocalBackgroundHost(jobs,auth))
        assert len(outcome)==1 and outcome[0].status=='unknown' and stale_model.calls==0
        assert jobs.query_original(token,'stale-job','stale-job-attempt')['meter_attempt_id']==stale['meter_attempt_id']
        assert run_worker.run_once(database,stale_model,auth,background_jobs=LocalBackgroundHost(jobs,auth))==[] and stale_model.calls==0
        print('PASS PROTOTYPE actual send.2/current Travel→joint source→one filtered Fake/Meter→canonical current Memory; stale Travel prevents even first model/claim and cannot redispatch; main acceptance UNRUN')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='bg-current-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
