"""Actual C original-publication adapter cases within publication_pg's private PG."""
import hashlib
import json

from cj_memory.domain import CommitUnknown as MemoryCommitUnknown
from cj_message.domain import CommitUnknown as MessageCommitUnknown,Unavailable as MessageUnavailable
from cj_message.source import SourceQuery
from cj_memory_jobs.codec import Conflict,Unavailable
from cj_memory_jobs.collection import CollectionService
from cj_memory_jobs.publication_store import PublicationTransaction


def exercise(client,post,expected,host,repository,token,headers,scope,lose_commit_after):
    service=host.service
    def create(chat,text):
        head=expected(client.put('/v1/conversations',params={'conversation_id':chat},headers=headers))
        mid=chat+'-msg';job=chat+'-job';attempt=chat+'-attempt'
        post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id=chat,message_id=mid,text=text,
            trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0))
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id=chat+'-enable',operation='enable',
            conversation_id=chat,expected_generation=head['generation'],expected_epoch=0,expected_source_version=0))
        source=dict(conversation_id=chat,generation=head['generation'],epoch=0,after=0,through=1,
                    source_version=1,withdrawal_epoch=1,mode='incremental')
        post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id=job,attempt_id=attempt,source=source))
        service.transition(token,job,attempt,'inflight')
        prepared=service.prepare_model_input(token,job,attempt,max_payload_bytes=262144)
        return job,attempt,SourceQuery(**source),prepared,mid,head

    def output(mid,text,*,slot='diet.spicy',kind='preference',extent='long_term'):
        return json.dumps(dict(version='MEMORY-EXTRACT@1',entries=[dict(subject='companion:one',slot=slot,kind=kind,
            text=text,extent=extent,occurred_at='date unknown',evidence=[dict(message_id=mid,quote=text)])]),ensure_ascii=False).encode()

    def publish(data,raw,*,collection=service,selection=None,caught=False):
        job,attempt,query,prepared,_,_=data
        def stage(context):
            policy=collection.publication_policy(context,token,job,attempt,prepared,hashlib.sha256(prepared).hexdigest(),
                raw,hashlib.sha256(raw).hexdigest(),max_payload_bytes=262144)
            def project(snapshot,lease=None):
                if not caught:return policy.apply_original_result(snapshot,lease)
                try:policy.apply_original_result(snapshot,lease)
                except Unavailable:return b'caught-publication-error'
                raise AssertionError('expected a current-source refusal')
            if selection is None:return context.with_enabled_source(query,policy,project)
            return context.with_enabled_source_and_travel(query,policy,selection,project)
        return host.boundary.with_history_context(token,stage)

    data=create('result-original','My companion avoids spicy food / 同伴不吃辣')
    raw=output(data[4],'My companion avoids spicy food / 同伴不吃辣')
    uncertain=CollectionService(host.boundary,lose_commit_after('INSERT INTO cj_memory_operation'),service.resolve_collection)
    try:publish(data,raw,collection=uncertain)
    except MemoryCommitUnknown:pass
    else:raise AssertionError('publication C COMMIT ACK loss reported success')
    original=json.loads(service.query_publication(token,*data[:2]))
    assert original['version']=='MEMORY-PUBLICATION-result@1' and original['receipts'][0]['status']=='active'
    assert original['prepared_input_sha256']==hashlib.sha256(data[3]).hexdigest()
    assert original['model_output_sha256']==hashlib.sha256(raw).hexdigest()
    reply=expected(client.get('/v3/memory-publication-receipts',params={'job_id':data[0],'attempt_id':data[1]},headers=headers))
    assert reply['result']==original
    post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='result-original-disable',operation='disable',
        conversation_id='result-original',expected_generation=data[5]['generation'],expected_epoch=0,expected_source_version=1))
    reopened=CollectionService(host.boundary,service.resolve_repository,service.resolve_collection)
    assert json.loads(reopened.query_publication(token,*data[:2]))==original
    # Persistent data is a boundary: truncating the receipt vector cannot turn
    # a real original publication into a successful empty result.
    with host.database.connect(scope) as conn:
        saved=conn.execute('SELECT candidate FROM cj_memory_history_job WHERE job_id=%s',(data[0],)).fetchone()[0]
        changed=dict(original,receipts=[])
        conn.execute('UPDATE cj_memory_history_job SET candidate=%s WHERE job_id=%s',(json.dumps(changed).encode(),data[0]))
    expected(client.get('/v3/memory-publication-receipts',params={'job_id':data[0],'attempt_id':data[1]},headers=headers),503)
    with host.database.connect(scope) as conn:
        conn.execute('UPDATE cj_memory_history_job SET candidate=%s WHERE job_id=%s',(saved,data[0]))
    assert json.loads(service.query_publication(token,*data[:2]))==original
    print('PASS original typed publication receipt survives C ACK loss, source withdrawal and reconstructed service; actual canonical operations and model entry count are checked, corruption fails closed')

    data2=create('result-outer','No qualifying memory')
    empty=json.dumps(dict(version='MEMORY-EXTRACT@1',entries=[])).encode()
    class LostOuter:
        def __init__(self,connection):self.connection=connection
        @property
        def autocommit(self):return self.connection.autocommit
        def cursor(self):return self.connection.cursor()
        def bind_scope(self,cursor):return self.connection.bind_scope(cursor)
        def rollback(self):return self.connection.rollback()
        def close(self):return self.connection.close()
        def commit(self):
            self.connection.commit()
            raise OSError('synthetic outer source ACK loss')
    resolve=host.boundary.resolve_repository
    def uncertain_message(principal):
        repo=resolve(principal);connect=repo.connect
        repo.connect=lambda:LostOuter(connect())
        return repo
    host.boundary.resolve_repository=uncertain_message
    try:
        try:publish(data2,empty)
        except MessageCommitUnknown:pass
        else:raise AssertionError('outer MESSAGE ACK loss reported success')
    finally:host.boundary.resolve_repository=resolve
    assert json.loads(service.query_publication(token,*data2[:2]))['receipts']==[]
    print('PASS actual outer MESSAGE ACK loss after C publication: original empty/no-change result remains queryable, without treating completed as a new dispatch grant')

    data3=create('result-atomic','A companion visited a museum')
    first=json.loads(output(data3[4],'A companion visited a museum',slot='experience.visit',kind='experience'))['entries'][0]
    bad=json.dumps(dict(version='MEMORY-EXTRACT@1',entries=[first,dict(first,extent='current')])).encode()
    before=None
    with host.database.connect(scope) as conn:before=conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()[0]
    try:publish(data3,bad,caught=True)
    except Unavailable:pass
    else:raise AssertionError('caught publication error committed a partial result')
    with repository.transaction() as memory:
        tx=PublicationTransaction(memory);tx.require_live()
        row,stored=tx.output(*data3[:2])
        assert row[0].state=='inflight' and stored is None
    with host.database.connect(scope) as conn:assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()[0]==before
    print('PASS caught current-source failure poisons the C holder: checkpoint, first canonical entry and cursor all roll back; no inferred Travel or long-term fallback')

    data4=create('result-cancel','Cancel the original extraction')
    post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='result-cancel-disable',operation='disable',
        conversation_id='result-cancel',expected_generation=data4[5]['generation'],expected_epoch=0,expected_source_version=1))
    encoded=host.boundary.with_history_context(token,lambda context:service.transition_original_in_context(
        context,token,*data4[:2],'cancelled'))
    assert json.loads(encoded)['state']=='cancelled'
    assert json.loads(service.query_original(token,*data4[:2]))['state']=='cancelled'
    try:publish(data4,empty)
    except (Unavailable,MessageUnavailable,Conflict):pass
    else:raise AssertionError('cancelled/withdrawn source published a late result')
    print('PASS original nonproductive cancellation after source withdrawal; late publication denied and original status remains available')
