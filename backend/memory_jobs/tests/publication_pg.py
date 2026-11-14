"""L1 supplied-output publication/decisions; actual worker/Meter remains separate."""
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import ISSUER,scope_for
from cj_memory.manual import ManualPolicy
from cj_memory.postgres import Repository
from cj_memory.domain import Conflict as MemoryConflict
from cj_memory.domain import Service as MemoryService
from cj_auth.interfaces import AdmissionStatus
from cj_message.domain import HistoryMessage
from cj_message.travel_reference import MessageContextAuthority
from cj_message.source import SourceQuery
from cj_memory_jobs.extraction import Evidence
from cj_memory_jobs.codec import Conflict
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.publication_store import PublicationTransaction
from cj_memory_jobs.collection import CollectionService
from cj_memory_jobs.service import OperationWithheld

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth
import migrate
import pg_suites


def exercise(conninfo,auth):
    dev_auth.init(auth,['alice','bob'])
    tokens={s:dev_auth.token(auth,s,30) for s in ('alice','bob')}
    headers={s:{'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'} for s,token in tokens.items()}
    slots=frozenset({'diet.spicy','pace.inferred','experience.visit'})
    policy=CollectionPolicy(frozenset({'self','companion:one'}),slots,10,4096,
        lambda entry:entry.slot in slots,
        lambda entry,rows:entry.kind!='inference' and any(entry.text==row.text for row in rows))
    memory_policy=ManualPolicy(policy.subjects,slots,frozenset({'long_term','current'}),frozenset(),
        datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:command.slot in slots,lambda command,raw:True)
    def resolve(principal):
        if principal.subject not in tokens:raise AssertionError('fixture identity not approved')
        return policy,memory_policy,lambda entry:(None,None)
    app=create_collection_app(conninfo_path=conninfo,auth_dir=auth,resolve_collection=resolve)
    host=app.state.memory_history;service=host.service
    scope=scope_for(ISSUER,'alice')
    def expected(response,status=200):
        assert response.status_code==status,(response.status_code,response.text)
        return response.json()
    def lose_commit_after(prefix):
        class Cursor:
            def __init__(self,cursor,connection):self.cursor,self.connection=cursor,connection
            def execute(self,sql,params=None):
                self.cursor.execute(sql,params)
                if sql.startswith(prefix):self.connection.lost=True
                return self
            @property
            def rowcount(self):return self.cursor.rowcount
            def fetchone(self):return self.cursor.fetchone()
            def fetchall(self):return self.cursor.fetchall()
            def close(self):return self.cursor.close()
        class Connection:
            def __init__(self,connection):self.connection,self.lost=connection,False
            @property
            def autocommit(self):return self.connection.autocommit
            def cursor(self):return Cursor(self.connection.cursor(),self)
            def bind_scope(self,cursor):return self.connection.bind_scope(cursor)
            def rollback(self):return self.connection.rollback()
            def close(self):return self.connection.close()
            def commit(self):
                self.connection.commit()
                if self.lost:raise OSError('synthetic publication ACK loss')
        def repository(principal,scope):
            return Repository(lambda:Connection(host.database.connect(scope)),scope,typed_context=True,
                transaction_binder=lambda connection,cursor:connection.bind_scope(cursor))
        return repository
    with TestClient(app) as client:
        def post(path,value,actor='alice',status=200):
            raw=value if type(value) is bytes else json.dumps(value,ensure_ascii=False).encode()
            return expected(client.post(path,content=raw,headers=headers[actor]),status)
        head=expected(client.put('/v1/conversations',params={'conversation_id':'chat'},headers=headers['alice']))
        texts=['不吃辣 / I do not eat spicy food','Maybe a leisurely pace would suit me']
        for i,text in enumerate(texts):
            post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='chat',message_id=f'm{i}',text=text,
                trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=i))
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',
            conversation_id='chat',expected_generation=head['generation'],expected_epoch=0,expected_source_version=0))
        source=dict(conversation_id='chat',generation=head['generation'],epoch=0,after=0,through=2,
                    source_version=1,withdrawal_epoch=1,mode='incremental')
        post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id='job',attempt_id='attempt',source=source))
        calls=[];captured=[]
        query=SourceQuery(**source)
        def protected_processing(raw,query=query,*,digest=None):
            def stage(context):
                policy=service.processing_policy(context,tokens['alice'],'job','attempt',raw,
                    hashlib.sha256(raw).hexdigest() if digest is None else digest,max_payload_bytes=262144)
                def project(snapshot):
                    captured.append((policy,snapshot))
                    from threading import Thread
                    from cj_memory_jobs.codec import Unavailable as LifetimeUnavailable
                    denied=[]
                    def other_thread():
                        try:policy.with_input(snapshot,lambda raw:b'wrong-thread')
                        except LifetimeUnavailable:denied.append(True)
                    thread=Thread(target=other_thread);thread.start();thread.join(5)
                    assert not thread.is_alive() and denied==[True]
                    def checked(original):
                        calls.append(original)
                        return b'processing-fence-ready'
                    return policy.with_input(snapshot,checked)
                return context.with_enabled_source(query,policy,project)
            return host.boundary.with_history_context(tokens['alice'],stage)
        try:protected_processing(b'{}')
        except Conflict:pass
        else:raise AssertionError('pending C job entered the processing callback')
        assert calls==[]
        service.transition(tokens['alice'],'job','attempt','inflight')
        prepared_bytes=service.prepare_model_input(tokens['alice'],'job','attempt',max_payload_bytes=262144)
        prepared_input=json.loads(prepared_bytes)
        system,input_messages=prepared_input['system'],prepared_input['messages']
        source_data=json.loads(input_messages[0]['content'])
        assert [m['role'] for m in input_messages]==['user']
        assert [m['message_id'] for m in source_data['messages']]==['m0','m1']
        assert source_data['end'] is None and 'Historical text' in system
        assert protected_processing(prepared_bytes)==b'processing-fence-ready'
        assert calls==[prepared_bytes]
        processing_policy,snapshot=captured[-1]
        from cj_memory_jobs.codec import Unavailable as HistoryUnavailable
        try:processing_policy.with_input(snapshot,lambda raw:b'escaped')
        except HistoryUnavailable:pass
        else:raise AssertionError('expired processing policy retained authority')
        for changed in (prepared_bytes+b' ',prepared_bytes.replace(b'Historical text',b'Historical DATA')):
            try:protected_processing(changed)
            except Conflict:pass
            else:raise AssertionError('changed prepared bytes entered the processing callback')
        try:protected_processing(prepared_bytes,digest='0'*64)
        except Conflict:pass
        else:raise AssertionError('wrong original digest entered the processing callback')
        try:protected_processing(prepared_bytes,query=SourceQuery(**dict(source,through=1)))
        except Conflict:pass
        else:raise AssertionError('another interval entered the original processing callback')
        assert calls==[prepared_bytes]
        print('PASS actual protected processing policy: pending/changed bytes/digest/interval and expired lifetime deny the callback; same original inflight source admits exact bytes; no provider/Meter claim')
        from cj_message.travel import Selection as TravelSelection
        from cj_message.travel_reference import LeaseUnavailable,Denied as ContextDenied
        joint_travel=post('/v1/travel-context-actions',dict(version='TRAVEL-context-action.1',action_id='processing-travel',
            operation='create',travel_context=None))['receipt']['travel_context']
        joint_calls=[];leases=[]
        def joint_processing(selection):
            def stage(context):
                policy=service.processing_policy(context,tokens['alice'],'job','attempt',prepared_bytes,
                    hashlib.sha256(prepared_bytes).hexdigest(),max_payload_bytes=262144)
                def project(snapshot,lease):
                    leases.append(lease)
                    def checked(original):
                        lease.check()
                        assert lease.context==selection
                        joint_calls.append(original)
                        return b'joint-processing-fence-ready'
                    return policy.with_input(snapshot,checked)
                return context.with_enabled_source_and_travel(query,policy,selection,project)
            return host.boundary.with_history_context(tokens['alice'],stage)
        assert joint_processing(TravelSelection(joint_travel['id'],1))==b'joint-processing-fence-ready'
        assert joint_calls==[prepared_bytes]
        try:leases[-1].check()
        except LeaseUnavailable:pass
        else:raise AssertionError('joint Travel lease escaped its callback lifetime')
        try:joint_processing(TravelSelection(joint_travel['id'],2))
        except ContextDenied:pass
        else:raise AssertionError('stale Travel version entered processing')
        assert joint_calls==[prepared_bytes]
        print('PASS fixed SOURCE@2 candidate with real C processing policy and genuine Travel lease; stale selection/lifetime denied; callback is bounded local work, not provider execution')
        # Supplied synthetic output tests this boundary; no provider or metering claim.
        output=json.dumps(dict(version='MEMORY-EXTRACT@1',entries=[
            dict(subject='self',slot='diet.spicy',kind='preference',text=texts[0],extent='long_term',
                occurred_at='date unknown',evidence=[dict(message_id='m0',quote=texts[0])]),
            dict(subject='self',slot='pace.inferred',kind='inference',text='I may prefer a leisurely pace',
                extent='long_term',occurred_at='date unknown',evidence=[dict(message_id='m1',quote=texts[1])])
        ]),ensure_ascii=False).encode()
        uncertain=CollectionService(host.boundary,lose_commit_after('UPDATE cj_memory_history_job SET result_bytes='),resolve)
        try:uncertain.record_output(tokens['alice'],'job','attempt',output)
        except OperationWithheld as error:assert (error.operation_id,error.attempt_id)==('job','attempt')
        else:raise AssertionError('checkpoint ACK loss returned success')
        assert service.record_output(tokens['alice'],'job','attempt',output)
        try:protected_processing(prepared_bytes)
        except Conflict:pass
        else:raise AssertionError('checkpointed C job obtained another processing phase')
        assert calls==[prepared_bytes]
        uncertain=CollectionService(host.boundary,lose_commit_after('INSERT INTO cj_memory_operation'),resolve)
        try:uncertain.publish_output(tokens['alice'],'job','attempt')
        except OperationWithheld as error:assert (error.operation_id,error.attempt_id)==('job','attempt')
        else:raise AssertionError('atomic publication ACK loss returned success')
        result=json.loads(service.publish_output(tokens['alice'],'job','attempt'))
        assert [r['status'] for r in result['receipts']]==['active','candidate']
        assert json.loads(service.publish_output(tokens['alice'],'job','attempt'))==result
        listing=expected(client.get('/v3/memory-candidates',params={'job_id':'job','attempt_id':'attempt'},headers=headers['alice']))['result']
        pending=next(x for x in listing['candidates'] if x['status']=='candidate')
        assert pending['kind']=='inference'
        active=next(x for x in listing['candidates'] if x['status']=='active')
        with host.database.connect(scope) as conn:
            assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(2,)
            assert conn.execute('SELECT count(*) FROM cj_memory_history_origin').fetchone()==(2,)
        repository=service.resolve_repository(host.boundary.checker.check(tokens['alice']).principal,scope)
        with repository.transaction() as tx:
            selected=tx.effective('self',None)
            assert [x.command.slot for x in selected]==['diet.spicy']
        decision=dict(version='MEMORY-CANDIDATE@1',action_id='confirm',job_id='job',attempt_id='attempt',
            candidate_id=pending['candidate_id'],expected_candidate_version=pending['version'],
            expected_memory_epoch=listing['memory_epoch'],operation='confirm',kind='preference',
            text='I prefer a leisurely pace / 我喜欢轻松节奏',extent='long_term',context=None,occurred_at='date unknown')
        raw=json.dumps(decision,ensure_ascii=False).encode()+b'\n'
        uncertain_app=create_collection_app(conninfo_path=conninfo,auth_dir=auth,resolve_collection=resolve)
        uncertain_app.state.memory_history.service.resolve_repository=lose_commit_after('INSERT INTO cj_memory_history_candidate_action')
        with TestClient(uncertain_app) as unknown_client:
            unknown=expected(unknown_client.post('/v3/memory-candidate-actions',content=raw,headers=headers['alice']),503)
            assert unknown['error']['outcome']=='unknown' and unknown['error']['recovery']=='reconcile_original'
        saved=expected(client.get('/v3/memory-candidate-receipts',params={'action_id':'confirm'},headers=headers['alice']))['result']
        assert saved['receipt']['status']=='active' and saved['receipt']['version']==2
        assert saved['input_sha256']==hashlib.sha256(raw).hexdigest()
        assert post('/v3/memory-candidate-actions',raw)['result']==saved
        assert json.loads(service.publish_output(tokens['alice'],'job','attempt'))==result
        post('/v3/memory-candidate-actions',raw+b' ',status=409)
        post('/v3/memory-candidate-actions',dict(decision,action_id='stale',expected_memory_epoch=listing['memory_epoch']),status=409)
        expected(client.get('/v3/memory-candidate-receipts',params={'action_id':'confirm'},headers=headers['bob']),503)
        with repository.transaction() as tx:
            values={i.command.slot:i for i in tx.effective('self',None)}
            assert set(values)=={'diet.spicy','pace.inferred'}
            assert values['pace.inferred'].command.kind=='preference'
        fresh=create_collection_app(conninfo_path=conninfo,auth_dir=auth,resolve_collection=resolve)
        with TestClient(fresh) as restarted:
            assert expected(restarted.get('/v3/memory-candidate-receipts',params={'action_id':'confirm'},headers=headers['alice']))['result']==saved
        print('PASS signed API/runtime PG supplied-output publication: direct actual entry, inference excluded until explicit review, exact decision replay/conflict, two-account denial and reconstructed host')
        # Original automatic receipts stay historical; review cannot mutate their bytes.
        with repository.transaction() as tx:
            assert tx.operation(result['receipts'][1]['operation_id'])[1].status=='candidate'
        print('PASS original automatic receipt stays candidate after new confirmed source/version; current canonical context uses reviewed value')
        print('PASS actual checkpoint/publication/user-decision COMMIT ACK loss: original bytes/results recover with no new operation or provider resend')
        post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='chat',message_id='m2',
            text='Maybe I would enjoy a museum',trip_id=None,creation_intent='none',
            expected_generation=head['generation'],expected_sequence=2))
        next_source=dict(source,after=2,through=3)
        post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id='reject-job',attempt_id='reject-attempt',source=next_source))
        service.transition(tokens['alice'],'reject-job','reject-attempt','inflight')
        proposed=json.dumps(dict(version='MEMORY-EXTRACT@1',entries=[dict(subject='self',slot='experience.visit',kind='inference',
            text='May enjoy museums',extent='long_term',occurred_at='date unknown',
            evidence=[dict(message_id='m2',quote='Maybe I would enjoy a museum')])])).encode()
        service.record_output(tokens['alice'],'reject-job','reject-attempt',proposed)
        service.publish_output(tokens['alice'],'reject-job','reject-attempt')
        view=expected(client.get('/v3/memory-candidates',params={'job_id':'reject-job','attempt_id':'reject-attempt'},headers=headers['alice']))['result']
        candidate=view['candidates'][0]
        with repository.transaction() as tx:
            expired_source=tx.detail(candidate['candidate_id']).command.source_id
        # Initialization-side clock simulation only reduces an existing source's
        # validity; it does not grant collection or bypass the runtime source gate.
        with psycopg.connect(**json.loads(conninfo.read_bytes())) as conn:
            conn.execute("UPDATE cj_memory_source SET expires_at=clock_timestamp()-interval '1 second' "
                         'WHERE scope=%s AND source_id=%s',(scope,expired_source))
        expired=dict(version='MEMORY-CANDIDATE@1',action_id='expired-confirm',job_id='reject-job',attempt_id='reject-attempt',
            candidate_id=candidate['candidate_id'],expected_candidate_version=candidate['version'],
            expected_memory_epoch=view['memory_epoch'],operation='confirm',kind='experience',
            text='Reviewed museum experience',extent='long_term',context=None,occurred_at='date unknown')
        post('/v3/memory-candidate-actions',expired,status=503)
        reject=dict(version='MEMORY-CANDIDATE@1',action_id='reject',job_id='reject-job',attempt_id='reject-attempt',
            candidate_id=candidate['candidate_id'],expected_candidate_version=candidate['version'],
            expected_memory_epoch=view['memory_epoch'],operation='reject')
        rejected=post('/v3/memory-candidate-actions',reject)['result']
        assert rejected['receipt']['status']=='rejected'
        assert post('/v3/memory-candidate-actions',reject)['result']==rejected
        with repository.transaction() as tx:
            assert 'experience.visit' not in {x.command.slot for x in tx.effective('self',None)}
            assert tx.detail(candidate['candidate_id']).status=='withdrawn'
        # A completed original is only a historical replay; it cannot undo rejection.
        service.publish_output(tokens['alice'],'reject-job','reject-attempt')
        with repository.transaction() as tx:
            assert tx.detail(candidate['candidate_id']).status=='withdrawn'
        print('PASS expired candidate cannot confirm but can be explicitly rejected; rejection/no-response never enters context and replay cannot reactivate it')
        post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='chat',message_id='m3',
            text='I now prefer spicy food',trip_id=None,creation_intent='none',
            expected_generation=head['generation'],expected_sequence=3))
        conflict_source=dict(source,after=3,through=4)
        post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id='conflict-job',attempt_id='conflict-attempt',source=conflict_source))
        service.transition(tokens['alice'],'conflict-job','conflict-attempt','inflight')
        changed=json.dumps(dict(version='MEMORY-EXTRACT@1',entries=[dict(subject='self',slot='diet.spicy',kind='preference',
            text='I now prefer spicy food',extent='long_term',occurred_at='date unknown',
            evidence=[dict(message_id='m3',quote='I now prefer spicy food')])])).encode()
        service.record_output(tokens['alice'],'conflict-job','conflict-attempt',changed)
        try:service.publish_output(tokens['alice'],'conflict-job','conflict-attempt')
        except MemoryConflict:pass
        else:raise AssertionError('automatic extraction overwrote a current canonical slot')
        try:service.record_output(tokens['alice'],'conflict-job','conflict-attempt',changed+b' ')
        except Conflict:pass
        else:raise AssertionError('original result bytes were replaced')
        with repository.transaction() as memory:
            tx=PublicationTransaction(memory);tx.require_live()
            original,stored=tx.output('conflict-job','conflict-attempt')
            assert stored==changed and original[0].state=='inflight'
            assert memory.detail(active['candidate_id']).command.text==texts[0]
        print('PASS real canonical-slot conflict rolls back publication, preserves original output checkpoint and leaves the current user value intact; no provider resend path')
        # Existing typed manual inference is a valid setup candidate. This checks
        # the explicit user-decision path, not automatic current extraction.
        travel=post('/v1/travel-context-actions',dict(version='TRAVEL-context-action.1',action_id='current-create',
            operation='create',travel_context=None))['receipt']['travel_context']
        memory_policy=replace(memory_policy,context_ids=frozenset({travel['id']}))
        principal=host.boundary.checker.check(tokens['alice']).principal
        def admit():
            current=host.boundary.checker.check(tokens['alice'])
            if current.status is not AdmissionStatus.ALLOWED or current.principal!=principal:
                raise AssertionError('fixture current identity unavailable')
            return current.principal
        authority=MessageContextAuthority(host.database.message_repository(scope),admit)
        canonical=MemoryService(repository,manual_policy=memory_policy)
        current_raw=json.dumps(dict(version='MEMORY-manual.2',operation_id='typed-candidate-op',item_id='typed-candidate',
            subject='self',slot='pace.inferred',kind='inference',text='Maybe slow pace for this trip',extent='current',
            context=dict(kind='travel',id=travel['id'],expected_version=1),occurred_at='date unknown')).encode()
        def guarded(stage):return admit(),scope
        canonical.with_operation(guarded,lambda operation:json.dumps(operation.save_manual_typed(current_raw,authority).__dict__).encode())
        original=host.boundary.with_history_context(tokens['alice'],lambda context:context.query_message('m1'))
        original_message=HistoryMessage(original.receipt,original.raw,json.loads(original.raw)['text'])
        with repository.transaction() as memory:
            tx=PublicationTransaction(memory);tx.require_live()
            current_item=memory.detail('typed-candidate')
            tx.origin(current_item.command,'job','attempt',(original_message,),
                      (Evidence('m1',original_message.text),))
        current_view=expected(client.get('/v3/memory-candidates',params={'job_id':'job','attempt_id':'attempt'},headers=headers['alice']))['result']
        reviewed=dict(version='MEMORY-CANDIDATE@1',action_id='typed-confirm',job_id='job',attempt_id='attempt',
            candidate_id='typed-candidate',expected_candidate_version=1,expected_memory_epoch=current_view['memory_epoch'],
            operation='confirm',kind='preference',text='Slow pace for this trip',extent='current',
            context=dict(kind='travel',id=travel['id'],expected_version=1),occurred_at='date unknown')
        post('/v1/travel-context-actions',dict(version='TRAVEL-context-action.1',action_id='current-advance',operation='advance',
            travel_context=dict(id=travel['id'],expected_version=1)))
        post('/v3/memory-candidate-actions',reviewed,status=503)
        reviewed['context']['expected_version']=2
        class TravelLostAck:
            def __init__(self,connection):self.connection=connection
            @property
            def autocommit(self):return self.connection.autocommit
            def cursor(self):return self.connection.cursor()
            def bind_scope(self,cursor):return self.connection.bind_scope(cursor)
            def rollback(self):return self.connection.rollback()
            def close(self):return self.connection.close()
            def commit(self):
                self.connection.commit()
                raise OSError('synthetic outer Travel ACK loss after candidate commit')
        lease_ack_app=create_collection_app(conninfo_path=conninfo,auth_dir=auth,resolve_collection=resolve)
        lease_ack_host=lease_ack_app.state.memory_history
        def lost_travel_repository(principal):
            own=scope_for(principal.issuer,principal.subject)
            repo=lease_ack_host.database.message_repository(own)
            connect=repo.connect
            repo.connect=lambda:TravelLostAck(connect())
            return repo
        lease_ack_host.boundary.resolve_repository=lost_travel_repository
        with TestClient(lease_ack_app) as uncertain_client:
            response=expected(uncertain_client.post('/v3/memory-candidate-actions',
                content=json.dumps(reviewed).encode(),headers=headers['alice']),503)
            assert response['error']['outcome']=='unknown' and response['error']['recovery']=='reconcile_original'
        typed_saved=post('/v3/memory-candidate-actions',reviewed)['result']
        assert typed_saved['receipt']['status']=='active'
        with repository.transaction() as memory:
            saved_item=memory.detail('typed-candidate')
            assert (saved_item.command.context_kind,saved_item.command.context_id,saved_item.command.context_version)==('travel',travel['id'],2)
        post('/v1/travel-context-actions',dict(version='TRAVEL-context-action.1',action_id='current-deactivate',operation='deactivate',
            travel_context=dict(id=travel['id'],expected_version=2)))
        assert post('/v3/memory-candidate-actions',reviewed)['result']==typed_saved
        post('/v3/memory-candidate-actions',dict(reviewed,action_id='typed-again'),status=503)
        print('PASS actual typed current user confirmation: stale travel refused, real M/T lease version accepted, original replay never reactivates retired travel; automatic current extraction UNRUN')
        # An actual immutable end signal selects a separate summary cursor. The
        # same source entries reuse their canonical receipts, preserving review.
        ending=dict(version='MESSAGE-SOURCE@1',conversation_id='chat',generation=head['generation'],
                    epoch=0,through=4,conversation_type='travel')
        ended=post('/internal/v1/conversation-end',ending)['end']
        assert post('/internal/v1/conversation-end',ending)['end']==ended
        end_source=dict(source,through=4,mode='conversation_end')
        post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id='end-job',attempt_id='end-attempt',source=end_source))
        service.transition(tokens['alice'],'end-job','end-attempt','inflight')
        summary_input=json.loads(service.prepare_model_input(tokens['alice'],'end-job','end-attempt',max_payload_bytes=262144))
        summary_messages=summary_input['messages']
        summary_data=json.loads(summary_messages[0]['content'])
        assert summary_data['purpose']=='conversation_end' and summary_data['end']==ended
        # Already-reviewed candidates are deliberately not re-proposed by this
        # supplied summary. New attempts including them conflict, never replace.
        end_output=json.dumps(dict(version='MEMORY-EXTRACT@1',entries=[json.loads(output)['entries'][0]]),ensure_ascii=False).encode()
        service.record_output(tokens['alice'],'end-job','end-attempt',end_output)
        end_result=json.loads(service.publish_output(tokens['alice'],'end-job','end-attempt'))
        assert end_result['receipts']==result['receipts'][:1]
        with repository.transaction() as memory:
            assert memory.detail(pending['candidate_id']).command.text==decision['text']
            assert memory.detail(pending['candidate_id']).status=='active'
        try:service.prepare_model_input(tokens['alice'],'end-job','end-attempt',max_payload_bytes=262144)
        except Conflict:pass
        else:raise AssertionError('completed summary granted a new input phase')
        print('PASS actual protected model-data preparation and stable end ID; separate summary cursor reuses same-source receipts and cannot overwrite reviewed memory; actual summary worker/Meter UNRUN')
        # Renewing history consent is not permission to undo a user's review.
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='summary-disable',operation='disable',
            conversation_id='chat',expected_generation=head['generation'],expected_epoch=0,expected_source_version=1))
        renewed=post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='summary-enable',operation='enable',
            conversation_id='chat',expected_generation=head['generation'],expected_epoch=0,expected_source_version=2))['result']
        late_source=dict(end_source,source_version=renewed['source_version'],withdrawal_epoch=renewed['withdrawal_epoch'])
        post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id='late-summary',attempt_id='late-attempt',source=late_source))
        service.transition(tokens['alice'],'late-summary','late-attempt','inflight')
        service.record_output(tokens['alice'],'late-summary','late-attempt',output)
        try:service.publish_output(tokens['alice'],'late-summary','late-attempt')
        except Conflict:pass
        else:raise AssertionError('fresh consent undid the explicit candidate review')
        with repository.transaction() as memory:
            tx=PublicationTransaction(memory);tx.require_live()
            assert tx.output('late-summary','late-attempt')[1]==output
            assert memory.detail(pending['candidate_id']).command.text==decision['text']
        try:service.prepare_model_input(tokens['alice'],'late-summary','late-attempt',max_payload_bytes=262144)
        except Conflict:pass
        else:raise AssertionError('stored late output granted a new input phase')
        print('PASS same-source summary after fresh consent cannot replace explicit user review; original output remains reconcilable without a new input/provider attempt')
        # Populate the other owner through the same public producer/review path.
        bob_scope=scope_for(ISSUER,'bob')
        bob_head=expected(client.put('/v1/conversations',params={'conversation_id':'chat'},headers=headers['bob']))
        post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='chat',message_id='b0',text='Maybe walk slowly',
            trip_id=None,creation_intent='none',expected_generation=bob_head['generation'],expected_sequence=0),actor='bob')
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',
            conversation_id='chat',expected_generation=bob_head['generation'],expected_epoch=0,expected_source_version=0),actor='bob')
        post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id='job',attempt_id='attempt',
            source=dict(source,generation=bob_head['generation'],through=1)),actor='bob')
        service.transition(tokens['bob'],'job','attempt','inflight')
        bob_output=json.dumps(dict(version='MEMORY-EXTRACT@1',entries=[dict(subject='self',slot='pace.inferred',kind='inference',
            text='Maybe walk slowly',extent='long_term',occurred_at='date unknown',
            evidence=[dict(message_id='b0',quote='Maybe walk slowly')])])).encode()
        service.record_output(tokens['bob'],'job','attempt',bob_output)
        service.publish_output(tokens['bob'],'job','attempt')
        bob_view=expected(client.get('/v3/memory-candidates',params={'job_id':'job','attempt_id':'attempt'},headers=headers['bob']))['result']
        bob_candidate=bob_view['candidates'][0]
        bob_reject=dict(version='MEMORY-CANDIDATE@1',action_id='reject',job_id='job',attempt_id='attempt',
            candidate_id=bob_candidate['candidate_id'],expected_candidate_version=1,
            expected_memory_epoch=bob_view['memory_epoch'],operation='reject')
        post('/v3/memory-candidate-actions',bob_reject,actor='bob')
        with host.database.connect(bob_scope) as conn:
            for table in ('cj_memory_history_candidate_action','cj_memory_history_origin'):
                assert conn.execute(f'SELECT count(*) FROM {table} WHERE scope=%s',(scope,)).fetchone()==(0,)
                assert conn.execute('SELECT has_table_privilege(current_user,%s,%s)',(table,'DELETE')).fetchone()==(False,)
            conn.execute('UPDATE cj_memory_history_job SET result_bytes=%s WHERE scope=%s',(b'{}',scope))
            assert conn.execute('SELECT result_bytes FROM cj_memory_history_job').fetchone()==(bob_output,)
        for sql,values in (
            ('INSERT INTO cj_memory_history_candidate_action(scope,action_id,candidate_id,job_id,attempt_id,operation,original_input,receipt,previous_source_id) '
             'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(scope,'forged','forged','job','attempt','reject',b'{}',b'{}','forged')),
            ('INSERT INTO cj_memory_history_origin(scope,source_id,item_id,job_id,attempt_id,origin_refs) VALUES(%s,%s,%s,%s,%s,%s::jsonb)',
             (scope,'forged','forged','job','attempt','[]'))):
            try:
                with host.database.connect(bob_scope) as conn:conn.execute(sql,values)
            except psycopg.errors.InsufficientPrivilege:pass
            else:raise AssertionError('runtime inserted another owner publication data')
        print('PASS actual new-table RLS: other-owner reads/writes denied and producer has no physical deletion privilege')
        from result_cases import exercise as result_cases
        result_cases(client,post,expected,host,repository,tokens['alice'],headers['alice'],scope,lose_commit_after)
        from cj_cleanup.core import Scope,encode,digest
        from cj_cleanup.coordinator import Coordinator
        from cj_cleanup.hooks_v1_1 import Selection
        from cj_cleanup.registry import freeze
        from cj_cleanup.store import Store
        from cj_memory_jobs.cleanup import CleanupHook,TARGET
        config=json.loads(conninfo.read_bytes())
        try:
            with psycopg.connect(**config,autocommit=True) as conn:
                conn.execute((ROOT/'backend/migrations/down/0037_memory_publication.down.sql').read_text())
        except psycopg.errors.RaiseException:
            with repository.transaction() as memory:
                tx=PublicationTransaction(memory);tx.require_live()
                assert tx.output('conflict-job','conflict-attempt')[1]==changed
        else:raise AssertionError('nonempty publication rollback erased output/decisions')
        principal=host.boundary.checker.check(tokens['alice']).principal
        subject=digest(encode(asdict(Scope.from_principal('local',principal))))
        def cleanup_guard(stage):
            current=host.boundary.checker.check(tokens['alice'])
            if current.status is not AdmissionStatus.ALLOWED or current.principal!=principal:
                raise AssertionError('fixture cleanup admission unavailable')
        store=Store(lambda:psycopg.connect(**dict(config,user='cj_local_cleanup')),subject,cleanup_guard)
        hook=CleanupHook(store,scope)
        # Domain-only fixture exercises every actual provided table, not global #27 completion.
        metadata=encode(dict(version='publication-test.1',stores=[dict(id=TARGET,
            cleanup_protocol='CLEANUP@1.1',objects=list(hook.content_tables)+['cj_memory_history_fence'])]))
        manifest=freeze(metadata,(TARGET,),versions=('CLEANUP@1.1',))
        coordinator=Coordinator(store,lambda:manifest,{TARGET:hook})
        plan={TARGET:dict(domain_scope=scope,selection={'kind':'account'})}
        coordinator.create('erase-publication',digest(encode(plan)),'account',plan)
        request=coordinator.request('erase-publication',TARGET,scope,Selection('account'))
        assert coordinator.advance(request)['status']=='complete'
        with host.database.connect(scope) as conn:
            for table in hook.content_tables:
                assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()==(0,)
            assert conn.execute('SELECT erased FROM cj_memory_history_fence').fetchone()==(True,)
        with host.database.connect(bob_scope) as conn:
            for table in ('cj_memory_history_candidate_action','cj_memory_history_origin'):
                assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()==(1,)
            assert conn.execute('SELECT result_bytes FROM cj_memory_history_job').fetchone()==(bob_output,)
        # Clean up the independently populated second owner using its own original intent.
        bob_principal=host.boundary.checker.check(tokens['bob']).principal
        bob_subject=digest(encode(asdict(Scope.from_principal('local',bob_principal))))
        bob_store=Store(lambda:psycopg.connect(**dict(config,user='cj_local_cleanup')),bob_subject,lambda stage:None)
        bob_coordinator=Coordinator(bob_store,lambda:manifest,{TARGET:CleanupHook(bob_store,bob_scope)})
        bob_plan={TARGET:dict(domain_scope=bob_scope,selection={'kind':'account'})}
        bob_coordinator.create('erase-bob-publication',digest(encode(bob_plan)),'account',bob_plan)
        bob_request=bob_coordinator.request('erase-bob-publication',TARGET,bob_scope,Selection('account'))
        assert bob_coordinator.advance(bob_request)['status']=='complete'
        print('PASS same-domain actual cleanup erases new output checkpoints, origin map and candidate-action bytes with existing task data; hashed fence retained')
        # Actual B prepare/confirmation persists retirement before any canonical
        # Memory hook. This is a consumer gate check, not whole-account cleanup.
        from cj_cleanup.gateway_store import GatewayStore
        captured=Store(lambda:psycopg.connect(**dict(config,user='cj_local_cleanup')),subject,lambda stage:None)
        metadata=GatewayStore(captured)
        device=metadata.register_device('retire-device',digest(b'retire-device'),'local-device',digest(b'local-state'))
        prepared=metadata.prepare('retire-prepare',digest(b'retire-prepare'),manifest,plan,device['binding_id'])
        confirmation=digest(b'explicit-fixture-account-confirmation')
        captured_coordinator=Coordinator(captured,lambda:manifest,{TARGET:CleanupHook(captured,scope)})
        captured_coordinator.create(prepared.operation_id,confirmation,'account',plan)
        metadata.confirm(prepared.operation_id,confirmation,manifest,owner_scope=scope,namespaces=(scope,),
                         check_admission=lambda:cleanup_guard('account_confirmation'))
        with psycopg.connect(**config) as conn:
            assert conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(scope,)).fetchone()[0]>0
        denied=expected(client.get('/v3/memory-candidates',params={'job_id':'job','attempt_id':'attempt'},headers=headers['alice']),403)
        assert denied['error']['code']=='ACCESS_DENIED'
        post('/v3/memory-candidate-actions',raw,status=403)
        from cj_memory_jobs.local_app import create_local_history_app
        with TestClient(create_local_history_app(conninfo_path=conninfo,auth_dir=auth)) as history_client:
            expected(history_client.get('/v3/memory-history-settings',params={'conversation_id':'chat'},headers=headers['alice']),403)
        assert host.boundary.checker.check(tokens['bob']).status is AdmissionStatus.ALLOWED
        with patch.object(host.database,'connect',side_effect=RuntimeError('synthetic account lookup unavailable')):
            unknown=expected(client.get('/v3/memory-history-settings',params={'conversation_id':'chat'},headers=headers['bob']),503)
            assert unknown['error']['code']=='ACCESS_UNKNOWN' and unknown['error']['outcome']=='unknown'
        print('PASS C collection uses runtime-only ACCOUNT-ADMISSION@2: actual original retirement denies the same token before canonical erasure; other owner allowed and lookup failure UNKNOWN, without fallback')


def exercise_demo_candidates(conninfo, auth):
    from cj_api.local_account_admission_v2 import subject_digest
    from cj_memory_jobs.codec import Unavailable
    from cj_memory_jobs.demo_candidates import DemoCandidates
    from cj_memory_jobs.publication_result import VERSION_DEMO
    from cj_memory_withdrawal.erasure_command import ErasureCommand
    from cj_memory_withdrawal.erasure_evidence import parse_original
    from cj_memory_withdrawal.erasure_store import freeze

    actors = ('demo-alice', 'demo-bob')
    dev_auth.init(auth, actors)
    tokens = {actor:dev_auth.token(auth,actor,30) for actor in actors}
    slots = frozenset({'travel.pace', 'seating', 'experience'})
    extraction = CollectionPolicy(frozenset({'self'}),slots,4,500,lambda entry:True,lambda entry,rows:True)
    memory_policy = ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),
        datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:True,lambda command,raw:True)
    app = create_collection_app(conninfo_path=conninfo,auth_dir=auth,
        resolve_collection=lambda principal:(extraction,memory_policy,lambda entry:(None,None)))
    host = app.state.memory_history
    service = host.service
    demo = DemoCandidates(service,frozenset(actors))
    other_demo = DemoCandidates(service,frozenset({'demo-bob'}))
    owner = tokens['demo-alice']
    headers = {'Authorization':'Bearer '+owner,'Content-Type':'application/octet-stream'}
    digest = lambda raw:hashlib.sha256(raw).hexdigest()
    chat = 'demo-candidate-chat'
    publications = {}
    with TestClient(app) as client:
        def post(path, value):
            response = client.post(path,content=json.dumps(value,ensure_ascii=False).encode(),headers=headers)
            assert response.status_code == 200,(response.status_code,response.text)
            return response.json()
        head = client.put('/v1/conversations',params={'conversation_id':chat},headers=headers).json()
        other = client.put('/v1/conversations',params={'conversation_id':chat},
            headers={'Authorization':'Bearer '+tokens['demo-bob']})
        assert other.status_code == 200,(other.status_code,other.text)
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='demo-enable',operation='enable',
            conversation_id=chat,expected_generation=head['generation'],expected_epoch=0,expected_source_version=0))

        def current(receipt, *, token=owner, run=None, service=demo):
            return json.loads(host.boundary.with_history_context(token,lambda context:service.current(
                context,token,receipt['message_id'],run or receipt['run_id'])))

        def collect(index, slot, text, *, kind='preference', extent='long_term', extra=False, expected=1):
            mid,jid,aid = f'demo-message-{index}',f'demo-job-{index}',f'demo-attempt-{index}'
            receipt = post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id=chat,message_id=mid,
                text=text,trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=index))['receipt']
            source = dict(conversation_id=chat,generation=head['generation'],epoch=0,after=index,through=index+1,
                          source_version=1,withdrawal_epoch=1,mode='incremental')
            post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id=jid,attempt_id=aid,source=source))
            service.transition(owner,jid,aid,'inflight')
            prepared = service.prepare_model_input_v2(owner,jid,aid,max_payload_bytes=8192)
            message, = json.loads(json.loads(prepared)['messages'][0]['content'])['messages']
            entry = dict(subject='self',slot=slot,kind=kind,text=text,extent=extent,occurred_at='date unknown',
                         evidence=[dict(ref=message['ref'],quote=text)])
            entries = [entry,dict(entry,slot='experience',kind='experience')] if extra else [entry]
            result = json.dumps(dict(version='MEMORY-EXTRACT@2',entries=entries),ensure_ascii=False).encode()
            bound = dict(message_id=mid,run_id=receipt['run_id'],max_payload_bytes=8192)
            def publish(context):
                processing = demo.processing_policy(context,owner,jid,aid,prepared,digest(prepared),**bound)
                assert context.with_enabled_source(SourceQuery(**source),processing,
                    lambda snapshot:processing.with_input(snapshot,lambda raw:digest(raw).encode())) == digest(prepared).encode()
                policy = demo.publication_policy(context,owner,jid,aid,prepared,digest(prepared),
                    result,digest(result),before_commit=lambda:None,**bound)
                return context.with_enabled_source(SourceQuery(**source),policy,policy.apply_original_result)
            raw = host.boundary.with_history_context(owner,publish)
            original = json.loads(raw)
            assert original['version'] == VERSION_DEMO and original['model_output_sha256'] == digest(result)
            assert [row['status'] for row in original['receipts']] == ['candidate'] * expected
            recovered = host.boundary.with_history_context(owner,lambda context:demo.query_publication_in_context(
                context,owner,jid,aid,message_id=mid,run_id=receipt['run_id']))
            assert recovered == raw
            publications[jid] = raw
            try:host.boundary.with_history_context(owner,lambda context:service.query_publication_v2_in_context(context,owner,jid,aid))
            except Unavailable:pass
            else:raise AssertionError('old publication version consumed a Demo receipt')
            return receipt

        first = collect(0,'travel.pace','I prefer no more than two sights a day',extra=True)
        second = collect(1,'seating','I usually prefer window seats')
        temporary = collect(2,'seating','For today only, I need an aisle seat',extent='current',expected=0)
        assert current(temporary)['candidates'] == []
        first_read,second_read = current(first),current(second)
        first_card, = first_read['candidates']
        second_card, = second_read['candidates']
        assert first_card['slot'] == 'travel.pace' and second_card['slot'] == 'seating'
        for token,run in ((tokens['demo-bob'],None),(owner,second['run_id'])):
            try:current(first,token=token,run=run)
            except Unavailable:pass
            else:raise AssertionError('other Demo owner or wrong RUN retrieved the candidate')
        try:current(first,service=other_demo)
        except Unavailable:pass
        else:raise AssertionError('unselected owner retrieved a Demo candidate')
        with host.database.connect(scope_for(ISSUER,'demo-alice')) as conn:
            assert conn.execute('SELECT status FROM cj_memory_item ORDER BY status').fetchall() == [('candidate',),('candidate',)]
        for index,receipt in enumerate((first,second)):
            projected = current(receipt)
            candidate, = projected['candidates']
            action = dict(version='MEMORY-CANDIDATE@1',action_id=f'demo-user-choice-{index}',**candidate['review'],
                candidate_id=candidate['candidate_id'],expected_candidate_version=candidate['version'],
                expected_memory_epoch=projected['memory_epoch'],operation='confirm' if index == 0 else 'reject')
            if index == 0:
                action.update({key:candidate[key] for key in ('kind','text','extent','context','occurred_at')})
            original = post('/v3/memory-candidate-actions',action)['result']
            assert post('/v3/memory-candidate-actions',action)['result'] == original
            assert original['receipt']['status'] == ('active' if index == 0 else 'rejected')
            assert current(receipt)['candidates'] == []
        with host.database.connect(scope_for(ISSUER,'demo-alice')) as conn:
            assert conn.execute("SELECT slot FROM cj_memory_item WHERE status='active'").fetchall() == [('travel.pace',)]
        def erase(context):
            repository,principal,guard = service._binding(context,owner)
            with repository.transaction() as memory:
                active, = memory.effective('self',None)
                assert active.command.item_id == first_card['candidate_id'] and active.version == 2
                command = ErasureCommand.parse(json.dumps(dict(version='MEMORY-ERASURE@1',action_id='demo-erase',
                    item_id=active.command.item_id,expected_version=active.version,derived_range='owned_trip_derived_scope')).encode())
                original = freeze(memory,command,subject_digest(principal),max_sources=1000,max_jobs=1000,max_bytes=1_000_000)
                evidence, = memory.cur.execute('SELECT evidence FROM cj_memory_erasure_manifest WHERE scope=%s AND action_id=%s',
                    (memory.scope,command.action_id)).fetchone()
                jobs = parse_original(bytes(evidence),json.loads(original),digest(original))['jobs']
                assert [(job['job_id'],job['publication_utf8'].encode()) for job in jobs] == [('demo-job-0',publications['demo-job-0'])]
                assert memory.effective('self',None) == []
                guard('demo_original_erasure_freeze')
                return b'original Demo publication frozen'
        assert host.boundary.with_history_context(owner,erase) == b'original Demo publication frozen'
        print('PASS actual Demo single-source input fence, mixed and empty candidate-only publication, exact recovery, explicit confirm and dismiss')
        print('PASS original Demo Pub4 proof is frozen unchanged and the removed item leaves canonical context')


def exercise_lio_candidates(conninfo, auth):
    from cj_api.local_account_admission_v2 import subject_digest
    from cj_memory_jobs.codec import Unavailable
    from cj_memory_jobs.consent import EnqueueCommand
    from cj_memory_jobs.lio_candidates import LioCandidates
    from cj_memory_jobs.postgres import encode
    from cj_memory_jobs.publication_result import VERSION_DEMO
    from cj_memory_withdrawal.erasure_command import ErasureCommand
    from cj_memory_withdrawal.erasure_store import freeze
    from cj_message.auth_boundary import HistoryReadContext
    from cj_message.travel import ABI

    sys.path.insert(0, str(ROOT/'backend/cj_api/tests'))
    from registered_host_support import RegisteredHost

    actors = ('lio-alice', 'lio-bob')
    registered = RegisteredHost(auth, Path(conninfo), {actor:(12,2,30000) for actor in actors})
    run_context = registered.profiles[actors[0]][1]
    for actor in actors:
        dev_auth.activate_travel(Path(conninfo), actor, run_context, ABI, auth_dir=auth)
    pace, quiet = 'I always like a slow travel pace.', 'I always prefer a quiet entrance.'
    slots = frozenset({'travel.pace', 'quiet.entrance'})
    extraction = CollectionPolicy(frozenset({'self'}),slots,4,500,lambda entry:True,lambda entry,rows:True)
    memory_policy = ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),
        datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:True,lambda command,raw:True)
    app = create_collection_app(conninfo_path=conninfo,auth_dir=auth,run_context=run_context,
        resolve_collection=lambda principal:(extraction,memory_policy,lambda entry:(None,None)))
    host = app.state.memory_history
    service = host.service
    lio = LioCandidates(service, frozenset(actors))
    headers = {**registered.headers[actors[0]], 'Content-Type':'application/octet-stream'}
    token = headers['Authorization'][7:]
    other = registered.headers[actors[1]]['Authorization'][7:]
    selected = 'lio-middle'
    digest = lambda raw:hashlib.sha256(raw).hexdigest()

    def original(context, mid):
        # Stand-in only for B's LIO marker lookup. Travel, owner, original bytes
        # and active generation are still checked by the signed repository.
        if mid == selected:
            travel = context.query_travel_message(mid)
            return travel.stored if travel is not None else None
        return None

    with patch.object(HistoryReadContext,'query_lio_message',original,create=True),TestClient(app) as client:
        chat='lio-private-pub4'
        head=client.put('/v1/conversations',params={'conversation_id':chat},headers=headers)
        assert head.status_code==200,head.text
        for index,(mid,text) in enumerate((('lio-before','Tell me about a park.'),
                (selected,pace+' '+quiet),('lio-after','What is the weather?'))):
            command=dict(version='MESSAGE-send.2',message_id=mid,text=text,conversation_id=chat,trip_id=None,
                         creation_intent='none',expected_generation=head.json()['generation'],
                         expected_sequence=index,travel_context=None,needs_reference=None)
            response=client.post('/v2/messages',content=json.dumps(command).encode(),headers=headers)
            assert response.status_code==200,response.text
            if mid==selected:
                receipt=response.json()['receipt']

        def current():
            return service.boundary.with_history_context(token,lambda context:
                lio.current(context,token,selected,receipt['run_id']))

        assert current() is None
        prepared=json.loads(lio.prepare(token,selected,receipt['run_id'],max_payload_bytes=8192))
        jid,aid=prepared['job_id'],prepared['attempt_id']
        query=SourceQuery(**prepared['source'])
        assert (query.after,query.through,prepared['state'])==(1,2,'inflight')
        raw=prepared['prepared_input_utf8'].encode()
        turn,=json.loads(json.loads(raw)['messages'][0]['content'])['messages']
        assert turn['text']==pace+' '+quiet
        assert json.loads(lio.prepare(token,selected,receipt['run_id'],max_payload_bytes=8192))['prepared_input_utf8'] is None
        for subject,run in ((other,receipt['run_id']),(token,'other-run')):
            try:lio.prepare(subject,selected,run,max_payload_bytes=8192)
            except Unavailable:pass
            else:raise AssertionError('foreign owner or wrong original RUN scheduled')

        model=encode(dict(version='MEMORY-EXTRACT@2',entries=[dict(subject='self',slot=slot,
            kind='preference',text=text,extent='long_term',occurred_at='date unknown',
            evidence=[dict(ref=turn['ref'],quote=text)])
            for slot,text in (('travel.pace',pace),('quiet.entrance',quiet))]))
        params=dict(message_id=selected,run_id=receipt['run_id'],max_payload_bytes=8192)

        def publish(context):
            processing=lio.processing_policy(context,token,jid,aid,raw,digest(raw),**params)
            assert context.with_enabled_source(query,processing,
                lambda snapshot:processing.with_input(snapshot,lambda original:digest(original).encode()))==digest(raw).encode()
            result=lio.publication_policy(context,token,jid,aid,raw,digest(raw),model,digest(model),
                before_commit=lambda:None,**params)
            return context.with_enabled_source(query,result,result.apply_original_result)

        result=service.boundary.with_history_context(token,publish)
        assert json.loads(result)['version']==VERSION_DEMO
        assert [row['status'] for row in json.loads(result)['receipts']]==['candidate','candidate']
        assert service.boundary.with_history_context(token,lambda context:
            lio.query_publication_in_context(context,token,jid,aid,message_id=selected,run_id=receipt['run_id']))==result
        projected=json.loads(current())
        cards={card['slot']:card for card in projected['candidates']}
        card,sibling=cards['travel.pace'],cards['quiet.entrance']
        assert json.loads(service.current_conversation_candidates(token,chat,''))['candidates']==[]
        try:service.query_original(token,jid,aid)
        except Unavailable:pass
        else:raise AssertionError('old job reader consumed a Lio job')
        with host.database.connect(scope_for(ISSUER,actors[0])) as conn:
            assert conn.execute('SELECT status FROM cj_memory_item').fetchall()==[('candidate',),('candidate',)]
            assert conn.execute('SELECT count(*) FROM cj_memory_history_consent').fetchone()==(0,)
            original,=conn.execute('SELECT original_input FROM cj_memory_history_job WHERE job_id=%s',(jid,)).fetchone()
            assert EnqueueCommand.parse(bytes(original)).query==query

        choice=encode(dict(version='MEMORY-CANDIDATE@1',action_id='remember-lio-middle',**card['review'],
            candidate_id=card['candidate_id'],expected_candidate_version=card['version'],
            expected_memory_epoch=projected['memory_epoch'],operation='confirm',
            **{key:card[key] for key in ('kind','text','extent','context','occurred_at')}))
        accepted=service.apply_candidate(token,choice)
        assert json.loads(accepted)['receipt']['status']=='active' and service.apply_candidate(token,choice)==accepted
        assert json.loads(current())['candidates']==[sibling]

        def erase(context):
            repository,principal,guard=service._binding(context,token)
            with repository.transaction() as memory:
                active,=memory.effective('self',None)
                assert active.command.item_id==card['candidate_id']
                original=ErasureCommand.parse(encode(dict(version='MEMORY-ERASURE@1',action_id='erase-lio-middle',
                    item_id=active.command.item_id,expected_version=active.version,derived_range='owned_trip_derived_scope')))
                freeze(memory,original,subject_digest(principal),max_sources=1000,max_jobs=1000,max_bytes=1_000_000)
                assert memory.effective('self',None)==[]
                guard('lio_erasure')
                return b'null'
        service.boundary.with_history_context(token,erase)
        # Simulate removal of the exact shared payload after the canonical
        # freeze. The retained origin and pending sibling remain user-visible.
        with psycopg.connect(**json.loads(Path(conninfo).read_text())) as observer:
            assert observer.execute('DELETE FROM cj_memory_history_job WHERE scope=%s AND job_id=%s '
                'AND attempt_id=%s RETURNING job_id',(scope_for(ISSUER,actors[0]),jid,aid)).fetchone()==(jid,)
        assert json.loads(current())['candidates']==[sibling]
        assert json.loads(service.current_conversation_candidates(token,chat,''))['candidates']==[]
        print('PASS Lio protected middle Travel message, candidate-only Pub4, explicit save and sibling after erasure')


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='g2c-pub-auth-') as temp:
        with pg_suites.cluster('publication_candidate',port=55510,role='cj_pub_init',socket=f'/tmp/cj-pub-{os.getpid()}') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                migrations=migrate.load()
                migrate.up(conn,migrations,migrations[-1]['version'])
                migrate.down(conn,migrations,36)
                migrate.up(conn,migrations,migrations[-1]['version'])
            path=Path(temp)/'conninfo.json';path.write_text(json.dumps(config))
            exercise(path,Path(temp)/'auth')
            with psycopg.connect(**config,autocommit=True) as conn:
                # Isolate M37's post-erasure rollback. Later migrations have
                # their own nonempty guards for unrelated retained C scopes.
                decision=next(m for m in migrations if m['version']==42)
                conn.execute((ROOT/decision['down']).read_text())
                publication=next(m for m in migrations if m['version']==37)
                conn.execute((ROOT/publication['down']).read_text())
                assert conn.execute('SELECT count(*) FROM cj_memory_history_fence WHERE erased').fetchone()==(2,)
                conn.execute((ROOT/publication['file']).read_text())
                conn.execute((ROOT/decision['file']).read_text())
            print('PASS nonempty down refusal; post-erasure empty publication rollback preserves the existing opaque erasure fence')
            exercise_demo_candidates(path,Path(temp)/'demo-auth')
            exercise_lio_candidates(path,Path(temp)/'lio-auth')
