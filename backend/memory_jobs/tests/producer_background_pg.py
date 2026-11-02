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
from cj_memory_jobs.codec import Conflict,Unavailable
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
            records=(('diet.spicy','preference','No spicy food'),('mobility.fact','fact','My height is 170 cm'),
                     ('experience.visit','experience','I visited a synthetic museum'))
            by_text={text:(slot,kind) for slot,kind,text in records}
            yield json.dumps(dict(version='MEMORY-EXTRACT@2',entries=[dict(subject='self',slot=slot,kind=kind,
                text=item['text'],extent='long_term',occurred_at='date unknown',evidence=[dict(ref=item['ref'],quote=item['text'])])
                for item in data['messages'] if item['text'] in by_text for slot,kind in [by_text[item['text']]]]))
        else:
            data=json.loads(messages[0]['content'].split('\n',1)[1]);self.answers.append(data)
            for chunk in super().stream(messages,system):yield json.dumps(data['items'])+chunk


def exercise(root,path,*,multi_only=False):
    subjects=('poll-multi',) if multi_only else ('poll-alice','poll-bob','poll-multi')
    auth=root/'auth';dev_auth.init(auth,subjects);now=int(time.time())
    quota=root/'quota.json';quota.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
        meter=dict(unit='provider_call',budget=30,period_start=now-60,period_end=now+3600,
            max_steps=20,max_tools=10,max_output=40000,max_seconds=600),output_limits=dict(model=4000,tool=4000,memory=4000)))))
    run=load_run_context(quota)
    for who in subjects:local_run_context.provision_budget(path,run,who)
    tokens={who:dev_auth.token(auth,who,30) for who in subjects}
    headers={who:{'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'} for who,token in tokens.items()}
    kinds={'diet.spicy':'preference','mobility.fact':'fact','experience.visit':'experience'}
    slots=frozenset(kinds);deadline=datetime.now(timezone.utc)+timedelta(hours=1)
    extraction=CollectionPolicy(frozenset({'self'}),slots,5,4096,lambda entry:True,
        lambda entry,rows:all(entry.text==row.text for row in rows))
    memory=ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),deadline,
        lambda command,raw:True,lambda command,raw:True)
    app=create_collection_app(conninfo_path=path,auth_dir=auth,run_context=run,
        resolve_collection=lambda principal:(extraction,memory,lambda entry:(None,None)))
    host=app.state.memory_history;c=host.service
    profile=dict(subjects=['self'],slots={slot:dict(kind=kind,collection_allowed=True,semantic_resolved=True) for slot,kind in kinds.items()},
        extents=['long_term'],context_ids=[])
    definition=dict(version='local-memory-run.2',collection=dict(version='local-memory-typed.1',
        collection=dict(version='local-memory-policy.1',expires_at=deadline.isoformat(),profiles={who:profile for who in subjects}),
        travel_contexts={who:[] for who in subjects}),
        selections={who:dict(subject='self',slots=['diet.spicy'],max_bytes=32768) for who in subjects})
    config=TypedRuntimeConfiguration.from_bytes(json.dumps(definition).encode())
    jobs=BackgroundJobsV2(database=host.database,boundary=host.boundary,collection=MemoryCollectionAdapterV2(c),max_payload_bytes=262144)
    originals=[]
    def submit(token,jid,attempt,query,prepared):
        result=jobs.prepare(token,JobRequest(jid,attempt,query,None,prepared));originals.append(result);return result
    intake=IncrementalProducer(c,submit,max_payload_bytes=262144,max_conversations=100)
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
        def multiple_sources():
            a=send('multi-a','multi-pref','No spicy food','poll-multi')
            b=send('multi-b','multi-height','My height is 170 cm','poll-multi')
            for chat,head in (('multi-a',a),('multi-b',b)):
                post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable-'+chat,operation='enable',
                    conversation_id=chat,expected_generation=head['generation'],expected_epoch=0,expected_source_version=0),'poll-multi')
            before=model.calls
            assert len(intake.poll(tokens['poll-multi']))==1
            assert intake.poll(tokens['poll-multi'])==(), 'a queued original must block another preparation at the same basis'
            racing=json.dumps(dict(version='MEMORY-JOBS@1',job_id='racing-job',attempt_id='racing-attempt',source=dict(
                conversation_id='multi-b',generation=b['generation'],epoch=0,after=0,through=1,
                source_version=1,withdrawal_epoch=1,mode='incremental'))).encode()
            try:c.enqueue_serialized(tokens['poll-multi'],racing)
            except Conflict:pass
            else:raise AssertionError('atomic automatic enqueue admitted a second original at the same basis')
            try:c.query_original(tokens['poll-multi'],'racing-job','racing-attempt')
            except Unavailable:pass
            else:raise AssertionError('denied racing original was persisted')
            first=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
            assert len(first)==3 and all(result.status=='completed' for result in first),first
            second=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
            assert len(second)==1 and second[0].status=='completed',second
            assert model.calls-before==4
            assert run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)==[]
            with host.database.connect(scope_for(ISSUER,'poll-multi')) as conn:
                assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(2,)
                assert conn.execute("SELECT count(*) FROM cj_memory_history_job WHERE state='unknown'").fetchone()==(0,)
            print('PASS two enabled same-owner sources advance sequentially across actual canonical epoch changes, one new job per poll, zero automatic repeat')
        if multi_only:
            multiple_sources()
            return
        head=send('source','fact','No spicy food','poll-alice')
        send('source','height','My height is 170 cm','poll-alice')
        send('source','visit','I visited a synthetic museum','poll-alice')
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='source',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=0),'poll-alice')
        results=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
        assert len(results)==4 and all(result.status=='completed' for result in results),results
        assert model.calls==4 and len(model.extractions)==1 and len(originals)==1
        original=originals[0];jid,attempt=original['job_id'],original['attempt_id']
        assert jobs.query_original(tokens['poll-alice'],jid,attempt)['state']=='completed'
        assert json.loads(c.query_original(tokens['poll-alice'],jid,attempt))['processed_through']==3
        assert run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)==[] and model.calls==4
        send('source','same-next','How should I plan food next?','poll-alice')
        results=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
        assert len(results)==2 and all(result.status=='completed' for result in results),results
        assert {item['slot']:item['text'] for item in model.answers[-1]['items']}=={'diet.spicy':'No spicy food'}
        assert len(model.extractions)==2 and len(originals)==2
        # The ordinary question is eligible historical data but yields no new
        # entries. This is an actual metered empty extraction, unlike the
        # all-withheld/no-model path; it cannot duplicate an active preference.
        second=originals[1]
        assert json.loads(c.query_publication_v2(tokens['poll-alice'],second['job_id'],second['attempt_id']))['receipts']==[]
        assert run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)==[]
        for who,expected in (('poll-alice',{'diet.spicy':'No spicy food'}),('poll-bob',{})):
            send(who+'-new',who+'-question','饮食怎么安排？',who)
            results=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
            assert len(results)==1 and results[0].status=='completed',results
            assert {item['slot']:item['text'] for item in model.answers[-1]['items']}==expected
            display=expect(client.get('/v1/run-display',params={'message_id':who+'-question'},headers=headers[who]))['snapshot']
            assert all(text in display['text'] for text in expected.values())
        for slot,question,text in (('mobility.fact','What height have I saved?','My height is 170 cm'),
                                   ('mobility.fact','我保存的身高是多少？','My height is 170 cm'),
                                   ('experience.visit','Which museum did I visit?','I visited a synthetic museum')):
            selected=json.loads(json.dumps(definition))
            for value in selected['selections'].values():value['slots']=[slot]
            chosen=TypedRuntimeConfiguration.from_bytes(json.dumps(selected).encode())
            mid='question-'+str(len(model.answers))
            send(mid,mid,question,'poll-alice')
            results=run_worker.run_once(host.database,model,auth,memory_configuration=chosen,background_jobs=combined)
            assert len(results)==1 and results[0].status=='completed'
            assert {item['slot']:item['text'] for item in model.answers[-1]['items']}=={slot:text}
        assert len(model.extractions)==2 and len(originals)==2
        multiple_sources()
    with host.database.connect(scope_for(ISSUER,'poll-alice')) as conn:
        assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(3,)
    with host.database.connect(scope_for(ISSUER,'poll-bob')) as conn:
        assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(0,)
    print('PASS actual signed enabled source→automatic C intake→original run_once/BG2/Fake/unique Meter→independent preference/fact/experience→bounded relevant new-chat English/Chinese actual model input and RUN display; Bob isolated, unenabled questions not extracted, repeat zero provider')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='producer-bg-') as folder:
        exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']),multi_only=os.environ.get('CJ_MEMORY_MULTI_ONLY')=='1')
