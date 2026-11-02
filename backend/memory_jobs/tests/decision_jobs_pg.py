"""Actual accepted/modified Trip + signed MSG3 + genuine source/Trip/Memory locks."""
from contextlib import contextmanager
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json,sys,unittest
import psycopg
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/trip/tests'),str(ROOT/'scripts')]
import manual_pg as manual
import dev_auth,message_trip_profile,local_run_context
from cj_api.local_app import create_local_app,LocalDatabase,scope_for,ISSUER
from cj_agent.provider import FakeProvider
from cj_message.source import SourceQuery
from cj_memory.manual import ManualPolicy
from cj_memory.domain import CommitUnknown
from cj_memory_jobs.collection_app import create_decision_collection_app
from cj_memory_jobs.decision_command import VERSION as JOB_VERSION
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.source_policy import SourcePolicy
from cj_memory_jobs.decision_input import prepared,DATA_VERSION
from cj_memory_jobs.codec import Unavailable
from cj_memory_jobs.codec import SourceV2,InvalidInput
from cj_memory_jobs.decision_batch import encoded as batch_encoded,decoded as batch_decoded
from cj_memory_jobs.decision_output import parse_output,decode_output,VERSION as OUTPUT_VERSION
from cj_memory_jobs.extraction import InvalidExtraction
from cj_trip.decision_lease import DecisionAuthority
from cj_trip.decision_source import DecisionQuery
from cj_trip.domain import Denied,packed
from cj_usage.background_exit import ModelInput
from cj_memory_jobs.decision_service import DecisionCollectionAdapter
from cj_run.background import BackgroundJobsV2
from cj_run.background_store import JobRequest
from cj_api.local_cleanup import Configuration
from cj_memory_withdrawal.account_cleanup import account_hooks
import run_worker,migrate


class DecisionInputChecks(manual.ManualChecks):
    def test_real_modified_trip_and_committed_discussion_feed_bounded_data(self):
        # ManualChecks.setUp already used the original worker/Fake, user accept
        # and signed structured initialization, producing accepted Trip version2.
        local_run_context.provision_budget(Path(manual.CONNINFO),self.run_context,'alice')
        dev_auth.activate_travel(Path(manual.CONNINFO),'alice',self.run_context,'MESSAGE-TRAVEL-CONSUMER@1')
        self.assertEqual(message_trip_profile.activate(Path(manual.CONNINFO),'alice',self.run_context,'MESSAGE-TRIP-CONSUMER@1'),'activated')
        app=create_local_app(conninfo_path=manual.CONNINFO,auth_dir=self.auth,run_context=self.run_context,
            travel_context=True,trip_context=True)
        headers={**self.headers('alice'),'Content-Type':'application/octet-stream'};token=headers['Authorization'][7:]
        with TestClient(app) as client:
            head=client.put('/v1/conversations',params={'conversation_id':'decision-source'},headers=headers).json()
            raw=packed(dict(version='MESSAGE-send.3',conversation_id='decision-source',message_id='selected-decision',
                text='Discuss the plan I accepted, without claiming I visited it',trip_id=None,creation_intent='none',
                expected_generation=head['generation'],expected_sequence=0,travel_context=None,needs_reference=None,
                trip_context=dict(id=self.trip_id,expected_version=self.base_version,day=None,item_id=None)))
            response=client.post('/v3/messages',content=raw,headers=headers)
            self.assertEqual(response.status_code,200,response.text)
            copy_head=client.put('/v1/conversations',params={'conversation_id':'decision-copy'},headers=headers).json()
            copied=json.loads(raw);copied.update(conversation_id='decision-copy',message_id='decision-copy-message',expected_generation=copy_head['generation'])
            response=client.post('/v3/messages',content=packed(copied),headers=headers)
            self.assertEqual(response.status_code,200,response.text)
            budget_head=client.put('/v1/conversations',params={'conversation_id':'decision-tail'},headers=headers).json()
            copied.update(conversation_id='decision-tail',message_id='decision-tail-message',expected_generation=budget_head['generation'])
            response=client.post('/v3/messages',content=packed(copied),headers=headers)
            self.assertEqual(response.status_code,200,response.text)
        normal=run_worker.run_once(LocalDatabase(manual.CONNINFO,run_context=self.run_context,travel_context=True,trip_context=True),FakeProvider(),self.auth)
        self.assertEqual(len(normal),3);self.assertTrue(all(value.status=='completed' for value in normal),normal)
        extraction=CollectionPolicy(frozenset({'self'}),frozenset({'planning.choice'}),5,4096,lambda entry:True,lambda entry,rows:False)
        policy=ManualPolicy(extraction.subjects,extraction.slots,frozenset({'long_term'}),frozenset(),
            datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:True,lambda command,raw:True)
        collection_app=create_decision_collection_app(conninfo_path=manual.CONNINFO,auth_dir=self.auth,run_context=self.run_context,
            resolve_collection=lambda principal:(extraction,policy,lambda entry:(None,None)))
        collection=collection_app.state.memory_history
        collection.service.apply_consent(token,packed(dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',
            conversation_id='decision-source',expected_generation=head['generation'],expected_epoch=0,expected_source_version=0)))
        query=SourceQuery('decision-source',head['generation'],0,0,1,1,1)
        authority=DecisionAuthority(self.decision_reader(),token)
        selected=DecisionQuery(self.trip_id,self.base_version,sha256(self.content).hexdigest())
        holder={}
        def read(context):
            repository,principal,guard=collection.service._binding(context,token)
            actual=SourcePolicy(repository,principal,guard)
            class Joined:
                @contextmanager
                def hold(self,who,scope,query):
                    with authority.hold(who,selected,max_source_bytes=4_000_000) as lease:
                        holder['lease']=lease
                        with actual.hold(who,scope,query) as permit:yield permit
            def project(snapshot):
                holder.update(snapshot=snapshot,tx=actual.transaction)
                source=SourceV2(snapshot.cursor,snapshot.source_version,snapshot.withdrawal_epoch)
                batch=batch_encoded(source,snapshot.messages,'incremental',holder['lease'].decision)
                decoded=batch_decoded(batch)
                self.assertEqual(decoded,(source,snapshot.messages,'incremental',holder['lease'].decision))
                self.assertEqual(batch_encoded(*decoded),batch)
                for changed in ('hash','field','version','document'):
                    value=json.loads(batch)
                    if changed=='hash':value['decision']['content_sha256']='0'*64
                    elif changed=='field':value['authority']=True
                    elif changed=='version':value['version']='CJ020-internal.2'
                    else:
                        value['decision']['content_utf8']='[]'
                        value['decision']['content_sha256']=sha256(b'[]').hexdigest()
                    with self.assertRaises(InvalidInput):batch_decoded(packed(value))
                result,count=prepared(actual.transaction,snapshot,holder['lease'],extraction,'incremental',max_payload_bytes=262144)
                self.assertEqual(count,1)
                data=json.loads(json.loads(result)['messages'][0]['content'])
                entry=dict(subject='self',slot='planning.choice',kind='experience',text='This is only a plan decision',
                    extent='long_term',occurred_at='date unknown',evidence=[dict(ref=data['trip_decisions'][0]['ref'],
                        quote=json.loads(self.content)['title'])])
                output=packed(dict(version=OUTPUT_VERSION,entries=[entry]))
                permissive=CollectionPolicy(extraction.subjects,extraction.slots,5,4096,lambda entry:True,lambda entry,rows:True)
                decoded_entries=parse_output(output,snapshot.messages,holder['lease'].decision,permissive,snapshot.scope)
                self.assertFalse(decoded_entries[0].direct_statement)
                self.assertEqual(decode_output(output,snapshot.messages,holder['lease'].decision,snapshot.scope),(decoded_entries[0].entry,))
                both=CollectionPolicy(extraction.subjects,frozenset({'planning.choice','message.statement'}),5,4096,
                    lambda entry:True,lambda entry,rows:True)
                statement=dict(entry,slot='message.statement',kind='fact',text=snapshot.messages[0].text,
                    evidence=[dict(ref=data['messages'][0]['ref'],quote=snapshot.messages[0].text)])
                mixed=parse_output(packed(dict(version=OUTPUT_VERSION,entries=[entry,statement])),snapshot.messages,
                    holder['lease'].decision,both,snapshot.scope)
                self.assertEqual([value.direct_statement for value in mixed],[False,True])
                forged=dict(statement,evidence=[dict(ref=data['messages'][0]['ref'],quote=json.loads(self.content)['title'])])
                with self.assertRaises(InvalidExtraction):parse_output(packed(dict(version=OUTPUT_VERSION,entries=[entry,forged])),
                    snapshot.messages,holder['lease'].decision,both,snapshot.scope)
                for change in ('quote','reference','owner'):
                    bad=json.loads(output)
                    if change=='quote':bad['entries'][0]['evidence'][0]['quote']='not in the accepted document'
                    elif change=='reference':bad['entries'][0]['evidence'][0]['ref']='trip-decision-v1:'+'0'*64
                    else:bad['entries'][0]['owner']='another-account'
                    with self.assertRaises(InvalidExtraction):parse_output(packed(bad),snapshot.messages,holder['lease'].decision,permissive,snapshot.scope)
                with self.assertRaises(Unavailable):prepared(actual.transaction,snapshot,holder['lease'],extraction,'incremental',max_payload_bytes=1)
                return result
            return context.with_enabled_source(query,Joined(),project)
        result=collection.boundary.with_history_context(token,read)
        model=ModelInput.parse(result);data=json.loads(model.messages[0][1])
        self.assertEqual(data['version'],DATA_VERSION)
        self.assertEqual(len(data['trip_decisions']),1)
        self.assertEqual(json.loads(data['trip_decisions'][0]['document']),json.loads(self.content))
        self.assertEqual(data['trip_decisions'][0]['anchor_ref'],data['messages'][0]['ref'])
        self.assertTrue(data['trip_decisions'][0]['ref'].startswith('trip-decision-v1:'))
        self.assertNotIn('trip_id',data['trip_decisions'][0])
        self.assertIn('never that a visit happened',model.system)
        with self.assertRaises(Denied):prepared(holder['tx'],holder['snapshot'],holder['lease'],extraction,'incremental',max_payload_bytes=262144)
        service=collection.service
        def publish(jid,attempt,query,end=None):
            raw=packed(dict(version=JOB_VERSION,job_id=jid,attempt_id=attempt,source=asdict(query),decision=asdict(selected),end=end))
            reader=query if end is None else replace(query,mode='incremental')
            with TestClient(collection_app) as client:
                if jid=='decision-job':
                    bad=json.loads(raw);bad['owner']='someone'
                    self.assertEqual(client.post('/internal/v1/memory-decision/jobs',content=packed(bad),headers=headers).status_code,400)
                    bad=json.loads(raw);bad['decision']['content_sha256']='0'*64
                    self.assertEqual(client.post('/internal/v1/memory-decision/jobs',content=packed(bad),headers=headers).status_code,409)
                response=client.post('/internal/v1/memory-decision/jobs',content=raw,headers=headers)
                self.assertEqual(response.status_code,200,response.text)
            service.begin_decision(token,jid,attempt)
            model_input=service.prepare_decision_input(token,jid,attempt,max_payload_bytes=262144)
            # An incompatible BG2 adapter fails before preparing any B original.
            if jid=='decision-job':
                wrong=BackgroundJobsV2(database=collection.database,boundary=collection.boundary,
                    collection=DecisionCollectionAdapter(service),max_payload_bytes=262144)
                with self.assertRaises(TypeError):wrong.prepare(token,JobRequest(jid,attempt,query,None,model_input))
                with collection.database.connect(scope_for(ISSUER,'alice')) as conn:
                    self.assertEqual(conn.execute('SELECT count(*) FROM cj_run_background_job').fetchone(),(0,))
            def process(context):
                holder=service.decision_processing_policy(context,token,jid,attempt,model_input,sha256(model_input).hexdigest(),max_payload_bytes=262144)
                return context.with_enabled_source(reader,holder,lambda snapshot:holder.with_input(snapshot,lambda actual:actual))
            self.assertEqual(service.boundary.with_history_context(token,process),model_input)
            data=json.loads(json.loads(model_input)['messages'][0]['content'])
            output=packed(dict(version=OUTPUT_VERSION,entries=[dict(subject='self',slot='planning.choice',kind='experience',
                text='This is only a plan decision',extent='long_term',occurred_at='date unknown',
                evidence=[dict(ref=data['trip_decisions'][0]['ref'],quote=json.loads(self.content)['title'])])]))
            tail=[]
            def commit(context):
                holder=service.decision_publication_policy(context,token,jid,attempt,model_input,sha256(model_input).hexdigest(),
                    output,sha256(output).hexdigest(),max_payload_bytes=262144,before_commit=lambda:tail.append(True))
                return context.with_enabled_source(reader,holder,lambda snapshot:holder.apply_original_result(snapshot))
            if jid=='decision-job':
                resolve=service.resolve_repository;lost=[False]
                class Cursor:
                    def __init__(self,base,owner):self.base,self.owner=base,owner
                    def __getattr__(self,name):return getattr(self.base,name)
                    def __enter__(self):self.base.__enter__();return self
                    def __exit__(self,*args):return self.base.__exit__(*args)
                    def execute(self,sql,*args,**kwargs):
                        result=self.base.execute(sql,*args,**kwargs)
                        if str(sql).startswith('INSERT INTO cj_memory_operation'):self.owner.wrote=True
                        return self
                class Connection:
                    def __init__(self,base):self.base,self.wrote=base,False
                    def __getattr__(self,name):return getattr(self.base,name)
                    def cursor(self):return Cursor(self.base.cursor(),self)
                    def commit(self):
                        self.base.commit()
                        if self.wrote and not lost[0]:lost[0]=True;raise OSError('synthetic decision Memory COMMIT ACK loss')
                def wrapped(principal,scope):
                    repository=resolve(principal,scope);connect=repository.connect
                    repository.connect=lambda:Connection(connect())
                    return repository
                with patch.object(service,'resolve_repository',wrapped),self.assertRaises(CommitUnknown):
                    service.boundary.with_history_context(token,commit)
                self.assertTrue(lost[0])
                service.apply_consent(token,packed(dict(version='MEMORY-HISTORY@1',action_id='off-after-ack',operation='disable',
                    conversation_id=query.conversation_id,expected_generation=query.generation,expected_epoch=0,expected_source_version=1)))
                result=service.query_decision_publication(token,jid,attempt)
            else:result=service.boundary.with_history_context(token,commit)
            self.assertEqual(tail,[True]);self.assertEqual(service.query_decision_publication(token,jid,attempt),result)
            return json.loads(result)
        first=publish('decision-job','decision-attempt',query)
        self.assertEqual(first['version'],'MEMORY-PUBLICATION-result@3')
        self.assertEqual(first['receipts'][0]['status'],'candidate')
        with collection.database.connect(scope_for(ISSUER,'alice')) as conn:
            origin=conn.execute('SELECT source_id,item_id,decision_source_sha256,origin_refs FROM cj_memory_history_origin').fetchone()
        with collection.database.connect(scope_for(ISSUER,'bob')) as conn:
            self.assertEqual(conn.execute('SELECT source_id FROM cj_memory_history_origin WHERE scope=%s',(scope_for(ISSUER,'alice'),)).fetchall(),[])
            self.assertEqual(conn.execute("UPDATE cj_memory_history_origin SET origin_refs='[]'::jsonb WHERE scope=%s",(scope_for(ISSUER,'alice'),)).rowcount,0)
        with self.assertRaises(psycopg.errors.InsufficientPrivilege),collection.database.connect(scope_for(ISSUER,'bob')) as conn:
            conn.execute('''INSERT INTO cj_memory_history_origin(scope,source_id,item_id,job_id,attempt_id,origin_refs,decision_source_sha256)
                VALUES(%s,%s,%s,'foreign-job','foreign-attempt',%s::jsonb,%s)''',
                (scope_for(ISSUER,'alice'),origin[0],origin[1],json.dumps(origin[3]),origin[2]))
        with psycopg.connect(**json.loads(Path(manual.CONNINFO).read_text()),autocommit=True) as conn:
            with self.assertRaises(psycopg.errors.RaiseException):conn.execute((ROOT/'backend/migrations/down/0042_memory_decision_source.down.sql').read_text())
            self.assertFalse(conn.execute("SELECT has_column_privilege('cj_m1_runtime','cj_memory_history_origin','decision_source_sha256','UPDATE')").fetchone()[0])
        service.apply_consent(token,packed(dict(version='MEMORY-HISTORY@1',action_id='enable-copy',operation='enable',
            conversation_id='decision-copy',expected_generation=copy_head['generation'],expected_epoch=0,expected_source_version=0)))
        copy_query=SourceQuery('decision-copy',copy_head['generation'],0,0,1,1,1)
        second=publish('copy-job','copy-attempt',copy_query)
        self.assertEqual(first['receipts'],second['receipts'])
        with TestClient(collection_app) as client:
            end=dict(conversation_id='decision-copy',generation=copy_head['generation'],epoch=0,through=1)
            response=client.post('/internal/v1/conversation-end',content=packed(dict(version='MESSAGE-SOURCE@1',conversation_type='travel',**end)),headers=headers)
            self.assertEqual(response.status_code,200,response.text)
        ended=publish('decision-ending','ending-attempt',replace(copy_query,mode='conversation_end'),end)
        self.assertEqual(ended['receipts'],first['receipts'])
        discovered=json.loads(service.discover_candidate_jobs(token,'decision-copy',''))
        self.assertEqual(discovered['jobs'],[dict(job_id='decision-job',attempt_id='decision-attempt')])
        with collection.database.connect(scope_for(ISSUER,'alice')) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_item').fetchone(),(1,))
            self.assertEqual(conn.execute('SELECT jsonb_array_length(origin_refs) FROM cj_memory_history_origin').fetchone(),(2,))
        with self.assertRaises(psycopg.errors.RaiseException),collection.database.connect(scope_for(ISSUER,'alice')) as conn:
            conn.execute("UPDATE cj_memory_history_origin SET origin_refs='[]'::jsonb")
        service.apply_consent(token,packed(dict(version='MEMORY-HISTORY@1',action_id='enable-tail',operation='enable',
            conversation_id='decision-tail',expected_generation=budget_head['generation'],expected_epoch=0,expected_source_version=0)))
        tail_query=SourceQuery('decision-tail',budget_head['generation'],0,0,1,1,1)
        raw=packed(dict(version=JOB_VERSION,job_id='tail-job',attempt_id='tail-attempt',source=asdict(tail_query),decision=asdict(selected),end=None))
        service.enqueue_decision(token,raw);service.begin_decision(token,'tail-job','tail-attempt')
        original=service.prepare_decision_input(token,'tail-job','tail-attempt',max_payload_bytes=262144)
        tail_data=json.loads(json.loads(original)['messages'][0]['content'])
        output=packed(dict(version=OUTPUT_VERSION,entries=[dict(subject='self',slot='planning.choice',kind='experience',
            text='This is only a plan decision',extent='long_term',occurred_at='date unknown',
            evidence=[dict(ref=tail_data['trip_decisions'][0]['ref'],quote=json.loads(self.content)['title'])])]))
        def deny():raise RuntimeError('synthetic original precommit budget denial')
        def denied(context):
            policy=service.decision_publication_policy(context,token,'tail-job','tail-attempt',original,sha256(original).hexdigest(),
                output,sha256(output).hexdigest(),max_payload_bytes=262144,before_commit=deny)
            return context.with_enabled_source(tail_query,policy,lambda snapshot:policy.apply_original_result(snapshot))
        with self.assertRaises(RuntimeError):service.boundary.with_history_context(token,denied)
        self.assertEqual(service.query_decision_publication(token,'tail-job','tail-attempt'),b'null')
        with collection.database.connect(scope_for(ISSUER,'alice')) as conn:
            self.assertEqual(conn.execute('SELECT result_bytes FROM cj_memory_history_job WHERE job_id=%s',('tail-job',)).fetchone(),(None,))
            self.assertEqual(conn.execute('SELECT jsonb_array_length(origin_refs) FROM cj_memory_history_origin').fetchone(),(2,))
        # The final HTTP bytes must still be inside the SAME identity lifetime.
        # JSON encoding is shared by old/new response placement, so this turns
        # red if the service guard finishes before the envelope is materialized.
        for operation in ('get','post'):
            invited=self.auth/'invited.json';before=invited.read_bytes();encode_json=json.dumps;revoked=[]
            def encoding(value,*args,**kwargs):
                if type(value) is dict and value.get('version')=='MEMORY-DECISION-response@1' and not revoked:
                    invited.write_text(encode_json([name for name in json.loads(before) if name!='alice']))
                    revoked.append(True)
                return encode_json(value,*args,**kwargs)
            try:
                with patch.object(json,'dumps',encoding),TestClient(collection_app) as client:
                    if operation=='get':response=client.get('/internal/v3/memory-decision/publications',
                        params={'job_id':'decision-job','attempt_id':'decision-attempt'},headers=headers)
                    else:
                        raw=packed(dict(version=JOB_VERSION,job_id='copy-job',attempt_id='copy-attempt',
                            source=asdict(copy_query),decision=asdict(selected),end=None))
                        response=client.post('/internal/v1/memory-decision/jobs',content=raw,headers=headers)
                self.assertEqual(revoked,[True]);self.assertNotEqual(response.status_code,200,response.text)
                self.assertNotIn('result',response.json());self.assertNotIn('receipts',response.text)
            finally:invited.write_bytes(before)
        candidates=json.loads(service.candidates(token,'decision-job','decision-attempt'))
        candidate=candidates['candidates'][0]
        service.apply_candidate(token,packed(dict(version='MEMORY-CANDIDATE@1',action_id='review-plan',job_id='decision-job',attempt_id='decision-attempt',
            candidate_id=candidate['candidate_id'],expected_candidate_version=1,expected_memory_epoch=candidates['memory_epoch'],operation='confirm',
            kind='preference',text='I prefer this planned pace',extent='long_term',context=None,occurred_at='date unknown')))
        self.assertEqual(json.loads(service.query_decision_publication(token,'decision-job','decision-attempt')),first)
        targets=('memory-derived','business/memory-management-actions','business/memory-authoritative','business/trip-authoritative','business/feedback-private-actions')
        registry=Path(self.tmp.name)/'decision-cleanup-registry.json'
        registry.write_bytes(packed(dict(version='decision-cleanup-component',stores=[dict(id='memory-derived',cleanup_protocol='CLEANUP@1.1'),
            dict(id='business',objects=[dict(id=name.split('/')[1],cleanup_protocol='CLEANUP@1.1') for name in targets[1:]])])))
        configuration=Configuration({'local':b'c-decision-cleanup-key-synthetic-only'},'local',3600,targets,registry,extra_hooks=account_hooks)
        cleanup=create_local_app(conninfo_path=manual.CONNINFO,auth_dir=self.auth,run_context=self.run_context,cleanup_configuration=configuration)
        with TestClient(cleanup) as client:
            def post(path,value):
                response=client.post(path,content=packed(value),headers=headers)
                self.assertEqual(response.status_code,200,response.text);return response.json()
            device=post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='decision-device',device_id='decision-device',state_ref='a'*64))
            operation=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='decision-cleanup',binding_id=device['binding_id']))
            result=post('/v1/account-cleanup-operations/'+operation['operation_id']+'/confirmation',dict(version='CLEANUP-API@1',
                registry_digest=operation['registry_digest'],confirmation='DELETE_ACCOUNT'))
            self.assertEqual(result['online_status'],'complete')
        with psycopg.connect(**json.loads(Path(manual.CONNINFO).read_text())) as conn:
            for table in ('cj_memory_history_job','cj_memory_history_origin','cj_memory_history_candidate_action','cj_memory_item','cj_memory_source'):
                self.assertEqual(conn.execute(f'SELECT count(*) FROM {table} WHERE scope=%s',(scope_for(ISSUER,'alice'),)).fetchone(),(0,),table)
        print('PASS actual accepted/modified Trip2 + completed original MSG3 worker + signed consent/durable job/Pub3/canonical candidate; cross-chat source reuse/first review, real C COMMIT ACK recovery after disable and tail rollback; explicit confirmation keeps original receipt, actual account hooks erase new Trip document/digest/refs. C-only supplied extraction output; new BG3/Meter extraction remains UNRUN')


if __name__=='__main__':
    unittest.main(defaultTest='DecisionInputChecks.test_real_modified_trip_and_committed_discussion_feed_bounded_data',verbosity=2)
