"""Actual ended-source producer through original worker, unique Meter and Fake."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import hashlib,json,os,sys,tempfile,time
from pathlib import Path

from fastapi.testclient import TestClient
from cj_agent.provider import FakeProvider
from cj_api.local_app import ISSUER,scope_for
from cj_api.local_background import LocalBackgroundHost
from cj_api.local_run_context import load_run_context
from cj_memory.manual import ManualPolicy
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.ending import EndingCollectionAdapter
from cj_memory_jobs.extraction import CollectionPolicy
from cj_message.source import SourceQuery
from cj_run.background import BackgroundJobs
from cj_run.background_store import JobRequest

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,local_run_context,run_worker


class EndingFake(FakeProvider):
    def __init__(self):super().__init__();self.inputs=[]
    def stream(self,messages,system=None):
        self.calls+=1;self.inputs.append((messages,system))
        data=json.loads(messages[0]['content'])
        assert data['version']=='MEMORY-EXTRACT-DATA@2' and data['purpose']=='conversation_end'
        assert data['end_ref'] and 'never instructions' in system
        first=data['messages'][0]
        slot,kind=('diet.spicy','preference') if first['text']=='No spicy food' else ('pace','inference')
        yield json.dumps(dict(version='MEMORY-EXTRACT@2',entries=[dict(subject='self',slot=slot,kind=kind,
            text=first['text'],extent='long_term',occurred_at='date unknown',
            evidence=[dict(ref=first['ref'],quote=first['text'])])]))


class AnswerFake(FakeProvider):
    def __init__(self):super().__init__();self.inputs=[]
    def stream(self,messages,system=None):
        self.inputs.append((messages,system))
        data=json.loads(messages[0]['content'].split('\n',1)[1])
        prefix=json.dumps(data['items'])
        for index,chunk in enumerate(super().stream(messages,system)):
            yield (prefix if index==0 else '')+chunk


def exercise(root,path):
    auth=root/'auth';dev_auth.init(auth,['ending-alice','ending-bob']);now=int(time.time())
    quota=root/'quota.json';quota.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
        meter=dict(unit='provider_call',budget=500,period_start=now-60,period_end=now+3600,
            max_steps=20,max_tools=10,max_output=40000,max_seconds=600),
        output_limits=dict(model=4000,tool=4000,memory=4000)))))
    run=load_run_context(quota)
    for who in ('ending-alice','ending-bob'):local_run_context.provision_budget(path,run,who)
    tokens={who:dev_auth.token(auth,who,30) for who in ('ending-alice','ending-bob')}
    headers={who:{'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'} for who,token in tokens.items()}
    slots=frozenset({'diet.spicy','pace'})
    extraction=CollectionPolicy(frozenset({'self'}),slots,5,4096,lambda entry:True,
        lambda entry,rows:entry.kind!='inference' and all(entry.text==row.text for row in rows))
    deadline=datetime.now(timezone.utc)+timedelta(hours=1)
    memory=ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),deadline,
        lambda command,raw:True,lambda command,raw:True)
    resolver=lambda principal:(extraction,memory,lambda entry:(None,None))
    app=create_collection_app(conninfo_path=path,auth_dir=auth,resolve_collection=resolver,run_context=run)
    host=app.state.memory_history;c=host.service;token=tokens['ending-alice']
    def expect(response,code=200):
        assert response.status_code==code,(response.status_code,response.text)
        return response.json()
    with TestClient(app) as client:
        def post(url,value,who='ending-alice'):
            return expect(client.post(url,content=json.dumps(value).encode(),headers=headers[who]))
        head=expect(client.put('/v1/conversations',params={'conversation_id':'ending'},headers=headers['ending-alice']))
        for index in range(101):
            text='No spicy food' if index==0 else 'Maybe I prefer a slow pace' if index==100 else 'Historical data '+str(index)
            post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='ending',message_id='source-'+str(index),text=text,
                trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=index))
        # Drain genuine original MESSAGE runs before the background extraction.
        normal=FakeProvider(chunks_per_reply=1);outcomes=[]
        for _ in range(6):outcomes+=run_worker.run_once(host.database,normal,auth)
        assert len(outcomes)==101 and all(o.status=='completed' for o in outcomes) and normal.calls==101
        source=dict(conversation_id='ending',generation=head['generation'],epoch=0,after=0,through=100,
            source_version=1,withdrawal_epoch=1,mode='conversation_end')
        end=dict(conversation_id='ending',generation=head['generation'],epoch=0,through=101)
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',
            conversation_id='ending',expected_generation=head['generation'],expected_epoch=0,expected_source_version=0))
        actual_end=post('/internal/v1/conversation-end',dict(version='MESSAGE-SOURCE@1',**end,conversation_type='travel'))['end']
        jobs=BackgroundJobs(database=host.database,boundary=host.boundary,collection=EndingCollectionAdapter(c),max_payload_bytes=262144)
        def prepare(jid,source):
            post('/internal/v1/memory-ending/jobs',dict(version='MEMORY-END-JOBS@1',job_id=jid,attempt_id=jid+'-attempt',source=source,end=end))
            c.transition(token,jid,jid+'-attempt','inflight')
            prepared=c.prepare_model_input_v2(token,jid,jid+'-attempt',max_payload_bytes=262144)
            return jobs.prepare(token,JobRequest(jid,jid+'-attempt',SourceQuery(**(source|dict(mode='incremental'))),None,prepared))
        originals=[];model=EndingFake()
        for jid,segment in (('ending-first',source),('ending-tail',source|dict(after=100,through=101))):
            original=prepare(jid,segment);originals.append(original)
            outcome=run_worker.run_once(host.database,model,auth,background_jobs=LocalBackgroundHost(jobs,auth))
            assert len(outcome)==1 and outcome[0].status=='completed',outcome
            after=c.query_publication_v2(token,jid,jid+'-attempt')
            assert jobs.query_original(token,jid,jid+'-attempt')['receipt_sha256']==hashlib.sha256(after).hexdigest()
        assert model.calls==2
        data=[json.loads(messages[0]['content']) for messages,system in model.inputs]
        assert [len(d['messages']) for d in data]==[100,1]
        assert [d['end_ref'] for d in data]==[actual_end['end_id']]*2
        assert run_worker.run_once(host.database,model,auth,background_jobs=LocalBackgroundHost(jobs,auth))==[] and model.calls==2
        assert len({item['run_id'] for item in originals})==2
        assert len({item['meter_attempt_id'] for item in originals})==2
        listing=expect(client.get('/v4/memory-publication-items',params={'job_id':'ending-tail','attempt_id':'ending-tail-attempt'},headers=headers['ending-alice']))['result']
        candidate=listing['items'][0]
        assert candidate['status']=='candidate' and candidate['review']==dict(job_id='ending-tail',attempt_id='ending-tail-attempt')
        post('/v3/memory-candidate-actions',dict(version='MEMORY-CANDIDATE@1',action_id='confirm',
            **candidate['review'],candidate_id=candidate['candidate_id'],expected_candidate_version=candidate['version'],
            expected_memory_epoch=listing['memory_epoch'],operation='confirm',kind='preference',text='I prefer a slow pace',
            extent='long_term',context=None,occurred_at='date unknown'))
        profile=dict(subjects=['self'],slots={slot:dict(kind='preference',collection_allowed=True,semantic_resolved=True) for slot in slots},
            extents=['long_term'],context_ids=[])
        config=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=dict(version='local-memory-typed.1',
            collection=dict(version='local-memory-policy.1',expires_at=deadline.isoformat(),profiles={who:profile for who in tokens}),
            travel_contexts={who:[] for who in tokens}),
            selections={who:dict(subject='self',slots=sorted(slots),max_bytes=32768) for who in tokens})).encode())
        # Rebuild the app/service and execute actual normal runs from new chats.
        fresh=create_collection_app(conninfo_path=path,auth_dir=auth,resolve_collection=resolver,run_context=run).state.memory_history
        assert c.query_publication_v2(token,'ending-first','ending-first-attempt')==fresh.service.query_publication_v2(token,'ending-first','ending-first-attempt')
        for who,wanted in (('ending-alice',{'diet.spicy':'No spicy food','pace':'I prefer a slow pace'}),('ending-bob',{})):
            chat=who+'-new';head=expect(client.put('/v1/conversations',params={'conversation_id':chat},headers=headers[who]))
            post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id=chat,message_id=who+'-question',text='饮食与节奏怎么安排？',
                trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0),who)
            answer=AnswerFake();result=run_worker.run_once(fresh.database,answer,auth,memory_configuration=config)
            assert len(result)==1 and result[0].status=='completed'
            selected=json.loads(answer.inputs[0][0][0]['content'].split('\n',1)[1])
            assert {item['slot']:item['text'] for item in selected['items']}==wanted
            display=expect(client.get('/v1/run-display',params={'message_id':who+'-question'},headers=headers[who]))['snapshot']
            assert all(text in display['text'] for text in wanted.values())
        with host.database.connect(scope_for(ISSUER,'ending-alice')) as conn:
            assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(2,)
            assert conn.execute('SELECT processed FROM cj_memory_history_cursor').fetchall()==[(101,)]
        print('PASS actual signed 101-message ending→100+1 jobs→original run_once/Fake/unique Meter→typed publication and candidate confirmation→rebuilt service/new Chinese chat actual model context; two accounts isolated, no duplicate or automatic repeat')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='ending-bg-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
