"""Actual automatic incremental poll -> original worker/Meter -> next context."""
from datetime import datetime,timedelta,timezone
import json,os,sys,tempfile,time
from pathlib import Path

from fastapi.testclient import TestClient
from cj_agent.provider import FakeProvider
from cj_api.local_app import ISSUER,scope_for
from cj_api.local_background import LocalBackgroundHost
from cj_api.local_run_context import load_run_context
from cj_memory.manual import ManualPolicy
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.producer import IncrementalProducer,ProducerHost
from cj_memory_jobs.worker_adapter import MemoryCollectionAdapterV2
from cj_run.background import BackgroundJobsV2
from cj_run.background_store import JobRequest

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,local_run_context,run_worker


class Observed(FakeProvider):
    def __init__(self):super().__init__(chunks_per_reply=1);self.answers=[];self.extractions=[]
    def stream(self,messages,system=None):
        if system is not None:
            self.calls+=1
            data=json.loads(messages[0]['content']);self.extractions.append(data)
            assert data['version']=='MEMORY-EXTRACT-DATA@2' and data['purpose']=='incremental'
            item=data['messages'][0]
            assert item['text']=='No spicy food'
            yield json.dumps(dict(version='MEMORY-EXTRACT@2',entries=[dict(subject='self',slot='diet.spicy',kind='preference',
                text=item['text'],extent='long_term',occurred_at='date unknown',evidence=[dict(ref=item['ref'],quote=item['text'])])]))
        else:
            data=json.loads(messages[0]['content'].split('\n',1)[1]);self.answers.append(data)
            for chunk in super().stream(messages,system):yield json.dumps(data['items'])+chunk


def exercise(root,path):
    auth=root/'auth';subjects=('poll-alice','poll-bob');dev_auth.init(auth,subjects);now=int(time.time())
    quota=root/'quota.json';quota.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
        meter=dict(unit='provider_call',budget=30,period_start=now-60,period_end=now+3600,
            max_steps=20,max_tools=10,max_output=40000,max_seconds=600),output_limits=dict(model=4000,tool=4000,memory=4000)))))
    run=load_run_context(quota)
    for who in subjects:local_run_context.provision_budget(path,run,who)
    tokens={who:dev_auth.token(auth,who,30) for who in subjects}
    headers={who:{'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'} for who,token in tokens.items()}
    slots=frozenset({'diet.spicy'});deadline=datetime.now(timezone.utc)+timedelta(hours=1)
    extraction=CollectionPolicy(frozenset({'self'}),slots,5,4096,lambda entry:True,
        lambda entry,rows:all(entry.text==row.text for row in rows))
    memory=ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),deadline,
        lambda command,raw:True,lambda command,raw:True)
    app=create_collection_app(conninfo_path=path,auth_dir=auth,run_context=run,
        resolve_collection=lambda principal:(extraction,memory,lambda entry:(None,None)))
    host=app.state.memory_history;c=host.service
    profile=dict(subjects=['self'],slots={'diet.spicy':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
        extents=['long_term'],context_ids=[])
    config=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=dict(version='local-memory-typed.1',
        collection=dict(version='local-memory-policy.1',expires_at=deadline.isoformat(),profiles={who:profile for who in subjects}),
        travel_contexts={who:[] for who in subjects}),
        selections={who:dict(subject='self',slots=['diet.spicy'],max_bytes=32768) for who in subjects})).encode())
    jobs=BackgroundJobsV2(database=host.database,boundary=host.boundary,collection=MemoryCollectionAdapterV2(c),max_payload_bytes=262144)
    originals=[]
    def submit(token,jid,attempt,query,prepared):
        result=jobs.prepare(token,JobRequest(jid,attempt,query,None,prepared));originals.append(result);return result
    intake=IncrementalProducer(c,submit,max_payload_bytes=262144)
    combined=ProducerHost(intake,lambda:[dev_auth.token(auth,who,5) for who in subjects],LocalBackgroundHost(jobs,auth))
    model=Observed()
    def expect(response):
        assert response.status_code==200,(response.status_code,response.text)
        return response.json()
    with TestClient(app) as client:
        def post(url,value,who):return expect(client.post(url,content=json.dumps(value).encode(),headers=headers[who]))
        def send(chat,mid,text,who):
            head=expect(client.put('/v1/conversations',params={'conversation_id':chat},headers=headers[who]))
            post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id=chat,message_id=mid,text=text,trip_id=None,
                creation_intent='none',expected_generation=head['generation'],expected_sequence=head['last_sequence']),who)
            return head
        head=send('source','fact','No spicy food','poll-alice')
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='source',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=0),'poll-alice')
        results=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
        assert len(results)==2 and all(result.status=='completed' for result in results),results
        assert model.calls==2 and len(model.extractions)==1 and len(originals)==1
        original=originals[0];jid,attempt=original['job_id'],original['attempt_id']
        assert jobs.query_original(tokens['poll-alice'],jid,attempt)['state']=='completed'
        assert json.loads(c.query_original(tokens['poll-alice'],jid,attempt))['processed_through']==1
        assert run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)==[] and model.calls==2
        for who,expected in (('poll-alice',{'diet.spicy':'No spicy food'}),('poll-bob',{})):
            send(who+'-new',who+'-question','饮食怎么安排？',who)
            results=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
            assert len(results)==1 and results[0].status=='completed',results
            assert {item['slot']:item['text'] for item in model.answers[-1]['items']}==expected
            display=expect(client.get('/v1/run-display',params={'message_id':who+'-question'},headers=headers[who]))['snapshot']
            assert all(text in display['text'] for text in expected.values())
        assert len(model.extractions)==1 and len(originals)==1
    with host.database.connect(scope_for(ISSUER,'poll-alice')) as conn:
        assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(1,)
    with host.database.connect(scope_for(ISSUER,'poll-bob')) as conn:
        assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(0,)
    print('PASS actual signed enabled source→automatic C incremental intake→original run_once/BG2/Fake/unique Meter→canonical preference→next Chinese chat actual model input and RUN display; Bob isolated, unenabled questions not extracted, repeat zero provider')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='producer-bg-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
