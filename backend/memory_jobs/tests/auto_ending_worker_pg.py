"""Actual metadata-driven automatic incremental/end scheduling, no end fabrication."""
from datetime import datetime,timedelta,timezone
import base64,json,os,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from cj_agent.provider import FakeProvider
from cj_api.local_app import ISSUER,scope_for
from cj_api.local_background import LocalBackgroundHost
from cj_api.local_run_context import load_run_context
from cj_memory.manual import ManualPolicy
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.ending import EndingCommand
from cj_memory_jobs.producer import ConversationProducer,ProducerHost
from cj_memory_jobs.worker_adapter import MemoryCollectionAdapterV2
from cj_run.background import BackgroundJobsV2
from cj_run.background_store import JobRequest

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,local_run_context,run_worker


class Model(FakeProvider):
    def __init__(self):super().__init__(chunks_per_reply=1);self.extractions=[];self.answers=[]
    def stream(self,messages,system=None):
        if system is None:
            data=json.loads(messages[0]['content'].split('\n',1)[1]);self.answers.append(data)
            for chunk in super().stream(messages,system):yield json.dumps(data['items'])+chunk
        else:
            self.calls+=1;data=json.loads(messages[0]['content']);self.extractions.append(data)
            assert data['version']=='MEMORY-EXTRACT-DATA@2'
            item=data['messages'][0]
            slot,kind=('diet.spicy','preference') if item['text']=='No spicy food' else ('pace','inference')
            assert item['text'] in ('No spicy food','Maybe I prefer a slow pace')
            yield json.dumps(dict(version='MEMORY-EXTRACT@2',entries=[dict(subject='self',slot=slot,kind=kind,
                text=item['text'],extent='long_term',occurred_at='date unknown',evidence=[dict(ref=item['ref'],quote=item['text'])])]))


def exercise(root,path):
    auth=root/'auth';actors=('auto-end-alice','auto-end-bob');dev_auth.init(auth,actors);now=int(time.time())
    quota=root/'quota.json';quota.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
        meter=dict(unit='provider_call',budget=500,period_start=now-60,period_end=now+3600,max_steps=20,max_tools=10,
            max_output=40000,max_seconds=600),output_limits=dict(model=4000,tool=4000,memory=4000)))))
    run=load_run_context(quota)
    for who in actors:local_run_context.provision_budget(path,run,who)
    tokens={who:dev_auth.token(auth,who,30) for who in actors}
    headers={who:{'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'} for who,token in tokens.items()}
    deadline=datetime.now(timezone.utc)+timedelta(hours=1);slots=frozenset({'diet.spicy','pace'})
    extraction=CollectionPolicy(frozenset({'self'}),slots,5,4096,lambda entry:True,
        lambda entry,rows:entry.kind!='inference' and all(entry.text==row.text for row in rows))
    policy=ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),deadline,
        lambda command,raw:True,lambda command,raw:True)
    resolver=lambda principal:(extraction,policy,lambda entry:(None,None))
    app=create_collection_app(conninfo_path=path,auth_dir=auth,run_context=run,resolve_collection=resolver)
    host=app.state.memory_history;c=host.service
    profile=dict(subjects=['self'],slots={slot:dict(kind='preference',collection_allowed=True,semantic_resolved=True) for slot in slots},
        extents=['long_term'],context_ids=[])
    config=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=dict(version='local-memory-typed.1',
        collection=dict(version='local-memory-policy.1',expires_at=deadline.isoformat(),profiles={who:profile for who in actors}),
        travel_contexts={who:[] for who in actors}),
        selections={who:dict(subject='self',slots=sorted(slots),max_bytes=32768) for who in actors})).encode())
    model=Model();armed={'published':False,'remaining':1}
    class AckAdapter(MemoryCollectionAdapterV2):
        def publication_policy(self,*args,**kwargs):
            actual=super().publication_policy(*args,**kwargs)
            class Held:
                def hold(self,*args,**kwargs):return actual.hold(*args,**kwargs)
                def apply_original_result(self,*args,**kwargs):
                    raw=actual.apply_original_result(*args,**kwargs)
                    if len(model.extractions)==4:armed['published']=True
                    return raw
            return Held()
    jobs=BackgroundJobsV2(database=host.database,boundary=host.boundary,collection=AckAdapter(c),max_payload_bytes=262144)
    originals=[]
    def submit(token,jid,attempt,query,prepared):
        result=jobs.prepare(token,JobRequest(jid,attempt,query,None,prepared));originals.append(result);return result
    producer=ConversationProducer(c,submit,max_payload_bytes=262144,max_conversations=100)
    combined=ProducerHost(producer,lambda:[dev_auth.token(auth,who,5) for who in actors],LocalBackgroundHost(jobs,auth))
    def ok(response):
        assert response.status_code==200,(response.status_code,response.text)
        return response.json()
    with TestClient(app) as client:
        def post(url,value,who='auto-end-alice'):return ok(client.post(url,content=json.dumps(value).encode(),headers=headers[who]))
        head=ok(client.put('/v1/conversations',params={'conversation_id':'long'},headers=headers['auto-end-alice']))
        for index in range(101):
            text='No spicy food' if index==0 else 'Maybe I prefer a slow pace' if index==100 else 'Historical data '+str(index)
            post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='long',message_id='m'+str(index),text=text,trip_id=None,
                creation_intent='none',expected_generation=head['generation'],expected_sequence=index))
        assert producer.poll(tokens['auto-end-alice'])==() and originals==[]
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='long',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=0))
        results=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
        assert all(result.status=='completed' for result in results),results
        assert [value['purpose'] for value in model.extractions]==['incremental']
        assert model.extractions[0]['end_ref'] is None and len(model.extractions[0]['messages'])==100
        assert producer.ending._plan(tokens['auto-end-alice'])==[]
        end=post('/internal/v1/conversation-end',dict(version='MESSAGE-SOURCE@1',conversation_id='long',generation=head['generation'],
            epoch=0,through=101,conversation_type='travel'))['end']
        original_resolver=host.boundary.resolve_repository
        class LostAck:
            def __init__(self,connection):self.connection=connection
            def __getattr__(self,name):return getattr(self.connection,name)
            def commit(self):
                self.connection.commit()
                if armed['published'] and armed['remaining']:
                    armed['remaining']-=1
                    raise OSError('synthetic automatic ending outer MESSAGE ACK loss')
        def resolver_with_lost_ack(principal):
            repository=original_resolver(principal);connect=repository.connect
            repository.connect=lambda:LostAck(connect())
            return repository
        saw_unknown=False
        with patch.object(host.boundary,'resolve_repository',resolver_with_lost_ack):
            for index in range(5):
                results=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
                if any(result.status=='unknown' for result in results):
                    assert len([result for result in results if result.status=='unknown'])==1 and len(model.extractions)==4
                    saw_unknown=True
                else:assert all(result.status=='completed' for result in results),results
                if index==0:
                    # Crash after the C pending commit, before original RUN
                    # preparation. Rebuilt intake must resume these exact bytes.
                    pending=producer.ending._plan(tokens['auto-end-alice'])
                    assert len(pending)==1
                    raw=base64.b64decode(pending[0],validate=True);command=EndingCommand.parse(raw)
                    c.enqueue_ending_serialized(tokens['auto-end-alice'],raw)
                    producer=ConversationProducer(c,submit,max_payload_bytes=262144,max_conversations=100)
                    assert producer.ending._plan(tokens['auto-end-alice'])==pending
                    combined=ProducerHost(producer,lambda:[dev_auth.token(auth,who,5) for who in actors],LocalBackgroundHost(jobs,auth))
                    assert json.loads(c.query_original(tokens['auto-end-alice'],command.job_id,command.attempt_id))['state']=='pending'
        assert saw_unknown and armed['remaining']==0
        assert [value['purpose'] for value in model.extractions]==['incremental','incremental','conversation_end','conversation_end']
        assert [len(value['messages']) for value in model.extractions]==[100,1,100,1]
        assert [value['end_ref'] for value in model.extractions[2:]]==[end['end_id']]*2
        assert len(originals)==4 and len({r['run_id'] for r in originals})==4
        assert run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)==[]
        assert len(model.extractions)==4
        last=originals[-1]
        assert jobs.query_original(tokens['auto-end-alice'],last['job_id'],last['attempt_id'])['state']=='unknown'
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='disable-after-ack',operation='disable',conversation_id='long',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=1))
        original_receipt=c.query_publication_v2(tokens['auto-end-alice'],last['job_id'],last['attempt_id'])
        reconciled=jobs.reconcile(tokens['auto-end-alice'],last['job_id'],last['attempt_id'])
        assert reconciled['state']=='completed' and reconciled['meter_attempt_id']==last['meter_attempt_id']
        assert c.query_publication_v2(tokens['auto-end-alice'],last['job_id'],last['attempt_id'])==original_receipt and len(model.extractions)==4
        listing=ok(client.get('/v4/memory-publication-items',params=dict(job_id=originals[-1]['job_id'],attempt_id=originals[-1]['attempt_id']),
            headers=headers['auto-end-alice']))['result']
        candidate=listing['items'][0]
        assert candidate['review']==dict(job_id=originals[1]['job_id'],attempt_id=originals[1]['attempt_id'])
        post('/v3/memory-candidate-actions',dict(version='MEMORY-CANDIDATE@1',action_id='confirm',**candidate['review'],
            candidate_id=candidate['candidate_id'],expected_candidate_version=1,expected_memory_epoch=listing['memory_epoch'],
            operation='confirm',kind='preference',text='I prefer a slow pace',extent='long_term',context=None,occurred_at='date unknown'))
        rebuilt=create_collection_app(conninfo_path=path,auth_dir=auth,run_context=run,resolve_collection=resolver).state.memory_history
        for who,expected in (('auto-end-alice',{'diet.spicy':'No spicy food','pace':'I prefer a slow pace'}),('auto-end-bob',{})):
            chat=who+'-new';current=ok(client.put('/v1/conversations',params={'conversation_id':chat},headers=headers[who]))
            post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id=chat,message_id=who+'-question',text='饮食和节奏怎么安排？',
                trip_id=None,creation_intent='none',expected_generation=current['generation'],expected_sequence=0),who)
            results=run_worker.run_once(rebuilt.database,model,auth,memory_configuration=config,background_jobs=combined)
            assert len(results)==1 and results[0].status=='completed',results
            assert {item['slot']:item['text'] for item in model.answers[-1]['items']}==expected
        assert len(model.extractions)==4
    with host.database.connect(scope_for(ISSUER,'auto-end-alice')) as conn:
        assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(2,)
        assert sorted(conn.execute('SELECT processed FROM cj_memory_history_cursor').fetchall())==[(101,),(101,)]
        origins=conn.execute('SELECT source_id,item_id,job_id,attempt_id FROM cj_memory_history_origin').fetchall()
        assert len(origins)==3 and len({row[1] for row in origins})==2,origins
        confirmed=[row for row in origins if row[0].startswith('candidate-confirm-v1:')]
        assert len(confirmed)==1 and confirmed[0][2:]==(originals[1]['job_id'],originals[1]['attempt_id'])
    print('PASS actual automatic open→incremental100, genuine end→incremental1/end100+1, rebuilt pending bytes, original worker/Meter/Fake, real outer ACK UNKNOWN→same-attempt reconcile after disable with zero resend, same-source review and rebuilt Chinese context/Bob isolation')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='auto-ending-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
