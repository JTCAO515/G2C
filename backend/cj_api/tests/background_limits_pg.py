"""Actual one-step/no-tool and output/time limits through the same Meter core."""
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
from cj_run.background import BackgroundJobs
from cj_run.background_store import JobRequest
ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT/'scripts'),str(Path(__file__).parent)]
from background_jobs_pg import ExtractFake
import dev_auth,local_run_context,run_worker


def exercise(root,path):
    for case in ('step','output','time','publication-time'):
        work=root/case;work.mkdir();auth=work/'auth';subject='bg-limit-'+case;dev_auth.init(auth,[subject])
        now=int(time.time());document=dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
            meter=dict(unit='provider_call',budget=10,period_start=now-60,period_end=now+3600,max_steps=1,max_tools=1,max_output=10000,max_seconds=10),
            output_limits=dict(model=2000,tool=2000,memory=1 if case=='output' else 2000)))
        quota=work/'quota.json';quota.write_text(json.dumps(document));context=load_run_context(quota)
        local_run_context.provision_budget(path,context,subject);database=LocalDatabase(path,run_context=context)
        token=dev_auth.token(auth,subject,30);headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
        with TestClient(create_local_app(conninfo_path=path,auth_dir=auth,run_context=context)) as client:
            head=client.put('/v1/conversations',params={'conversation_id':'limit'},headers=headers).json()
            sent=client.post('/v1/messages',content=json.dumps(dict(version='MESSAGE-send.1',conversation_id='limit',message_id='m0',text='No spicy food',
                trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0)).encode(),headers=headers)
            assert sent.status_code==200
        normal=FakeProvider();run_worker.run_once(database,normal,auth);assert normal.calls==1
        slots=frozenset({'diet.spicy'});extraction=CollectionPolicy(frozenset({'self'}),slots,10,4096,lambda entry:True,lambda entry,rows:any(entry.text==row.text for row in rows))
        memory=ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:True,lambda command,raw:True)
        app=create_collection_app(conninfo_path=path,auth_dir=auth,resolve_collection=lambda p:(extraction,memory,lambda entry:(None,None)),run_context=context)
        host=app.state.memory_history;c=host.service
        c.apply_consent(token,json.dumps(dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='limit',expected_generation=head['generation'],expected_epoch=0,expected_source_version=0)).encode())
        source=dict(conversation_id='limit',generation=head['generation'],epoch=0,after=0,through=1,source_version=1,withdrawal_epoch=1,mode='incremental')
        c.enqueue(token,json.dumps(dict(version='MEMORY-JOBS@1',job_id='job',attempt_id='attempt',source=source)).encode());c.transition(token,'job','attempt','inflight')
        prepared=c.prepare_model_input_v2(token,'job','attempt',max_payload_bytes=262144);tick=[time.time()]
        class Timed(ExtractFake):
            def stream(self,messages,system=None):
                if case=='time':tick[0]+=10
                yield from super().stream(messages,system)
        class Adapter(FilteredCollectionAdapter):
            def __init__(self,collection):
                super().__init__(collection);self.actual_publish=self.publication_policy;self.publication_policy=self.publish
            def publish(self,*args,**kwargs):
                policy=self.actual_publish(*args,**kwargs)
                if case=='publication-time':tick[0]+=10
                return policy
        jobs=BackgroundJobs(database=host.database,boundary=host.boundary,collection=Adapter(c),max_payload_bytes=262144,clock=lambda:tick[0])
        original=jobs.prepare(token,JobRequest('job','attempt',SourceQuery(**source),None,prepared));model=Timed()
        results=run_worker.run_once(database,model,auth,background_jobs=LocalBackgroundHost(jobs,auth))
        wanted='completed' if case=='step' else 'budget_exhausted'
        assert len(results)==1 and results[0].status==wanted and model.calls==1,(case,results)
        with psycopg.connect(**json.loads(path.read_text())) as conn:
            ledger=conn.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=(SELECT ledger_scope FROM cj_run_background_job WHERE run_id=%s)',(original['run_id'],)).fetchone()[0]
            run=ledger['runs'][original['run_id']];attempt=ledger['attempts'][original['meter_attempt_id']]
            assert run['steps']==1 and run['tools']==0 and attempt['command']['kind']=='memory'
            if case in ('output','time'):assert attempt['state']=='unknown' and attempt['receipt'] is None
            else:assert attempt['state']=='settled' and attempt['receipt']['actual']==1
            owner=scope_for(ISSUER,subject)
            assert conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(owner,)).fetchone()[0]==(1 if case=='step' else 0)
        assert run_worker.run_once(database,model,auth,background_jobs=LocalBackgroundHost(jobs,auth))==[] and model.calls==1
    print('PASS PROTOTYPE actual step=1/tools=0, memory output overrun, in-flight clock limit and source-preparation publication deadline; no canonical output past any limit, original UNKNOWN/settled financial states retained')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='bg-limits-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
