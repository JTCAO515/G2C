"""Actual long ended conversation segments; no model, queue storage or Meter claim."""
import base64,hashlib,json,os,sys,tempfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from cj_message.source import SourceQuery,EndQuery
from cj_memory_jobs.codec import decode_v2,Unavailable
from cj_memory_jobs.ending_source import EndingSegment,read_ending_segment
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory.manual import ManualPolicy
from cj_memory_jobs.ending import EndingCollectionAdapter

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,migrate,pg_suites


def exercise(conninfo,auth):
    dev_auth.init(auth,['alice','bob'])
    tokens={who:dev_auth.token(auth,who,30) for who in ('alice','bob')}
    headers={who:{'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'} for who,token in tokens.items()}
    extraction=CollectionPolicy(frozenset({'self'}),frozenset({'diet.spicy','pace'}),5,4096,
        lambda entry:True,lambda entry,rows:entry.kind!='inference' and all(entry.text==row.text for row in rows))
    memory=ManualPolicy(extraction.subjects,extraction.slots,frozenset({'long_term'}),frozenset(),
        datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:True,lambda command,raw:True)
    app=create_collection_app(conninfo_path=conninfo,auth_dir=auth,resolve_collection=lambda principal:(extraction,memory,lambda entry:(None,None)))
    host=app.state.memory_history;service=host.service
    def expected(response,code=200):
        assert response.status_code==code,(response.status_code,response.text)
        return response.json()
    with TestClient(app) as client:
        head=expected(client.put('/v1/conversations',params={'conversation_id':'long'},headers=headers['alice']))
        def post(path,value):return expected(client.post(path,content=json.dumps(value).encode(),headers=headers['alice']))
        for index in range(101):
            text='No spicy food' if index==0 else 'Maybe I prefer a slow pace' if index==100 else f'Committed message {index}'
            post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='long',message_id=f'm{index}',text=text,
                trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=index))
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='long',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=0))
        end=EndQuery('long',head['generation'],0,101)
        query=SourceQuery('long',head['generation'],0,0,100,1,1,'conversation_end')
        first=EndingSegment(query,end)
        def read(segment,who='alice'):
            token=tokens[who]
            return read_ending_segment(host.boundary,token,segment,lambda context:host.service.source_policy(context,token))
        from cj_message.domain import Unavailable as MessageUnavailable
        try:read(first)
        except (Unavailable,MessageUnavailable):pass
        else:raise AssertionError('unended conversation produced an ending segment')
        ended=post('/internal/v1/conversation-end',dict(version='MESSAGE-SOURCE@1',conversation_id='long',generation=head['generation'],
            epoch=0,through=101,conversation_type='travel'))['end']
        raw=read(first);value=json.loads(raw)
        source,rows,mode=decode_v2(base64.b64decode(value['batch_utf8_base64']))
        assert (source.cursor.after,source.cursor.through,mode,len(rows))==(0,100,'conversation_end',100)
        assert value['end']==ended and read(first)==raw
        tail=EndingSegment(SourceQuery('long',head['generation'],0,100,101,1,1,'conversation_end'),end)
        last=json.loads(read(tail));_,tail_rows,_=decode_v2(base64.b64decode(last['batch_utf8_base64']))
        assert [row.receipt.message_id for row in rows+tail_rows]==[f'm{i}' for i in range(101)]
        assert last['end']==ended
        # Original V1 cannot silently turn a prefix into the actual end.
        expected(client.post('/internal/v1/memory-history/jobs',content=json.dumps(dict(version='MEMORY-JOBS@1',
            job_id='legacy-prefix',attempt_id='legacy-attempt',source=query.__dict__)).encode(),headers=headers['alice']),503)
        adapter=EndingCollectionAdapter(service)
        def enqueue(segment,jid):
            value=dict(version='MEMORY-END-JOBS@1',job_id=jid,attempt_id=jid+'-attempt',
                source=segment.source.__dict__,end=segment.end.__dict__)
            raw=json.dumps(value).encode()
            receipt=expected(client.post('/internal/v1/memory-ending/jobs',content=raw,headers=headers['alice']))['result']
            assert expected(client.post('/internal/v1/memory-ending/jobs',content=raw,headers=headers['alice']))['result']==receipt
            service.transition(tokens['alice'],jid,jid+'-attempt','inflight')
            prepared=service.prepare_model_input_v2(tokens['alice'],jid,jid+'-attempt',max_payload_bytes=262144)
            data=json.loads(json.loads(prepared)['messages'][0]['content'])
            assert data['purpose']=='conversation_end' and data['end_ref']==ended['end_id']
            assert len(data['messages'])==segment.source.through-segment.source.after
            return raw,prepared,data
        def phase(segment,jid,prepared,output=None,query_override=None):
            def enter(context):
                args=(context,tokens['alice'],jid,jid+'-attempt',prepared,hashlib.sha256(prepared).hexdigest())
                policy=(adapter.processing_policy(*args,max_payload_bytes=262144) if output is None else
                    adapter.publication_policy(*args,output,hashlib.sha256(output).hexdigest(),max_payload_bytes=262144))
                actual=SourceQuery(**dict(segment.source.__dict__,mode='incremental')) if query_override is None else query_override
                return context.with_enabled_source(actual,policy,
                    lambda snapshot:policy.with_input(snapshot,lambda raw:b'bounded-local-phase') if output is None else
                        policy.apply_original_result(snapshot))
            return host.boundary.with_history_context(tokens['alice'],enter)
        first_raw,prepared,data=enqueue(first,'ending-first')
        assert phase(first,'ending-first',prepared)==b'bounded-local-phase'
        from cj_memory_jobs.codec import Conflict
        try:phase(first,'ending-first',prepared,query_override=query)
        except (Conflict,Unavailable,MessageUnavailable):pass
        else:raise AssertionError('ending adapter accepted another source reader/purpose')
        def output(data,index,slot,kind):
            message=data['messages'][index]
            return json.dumps(dict(version='MEMORY-EXTRACT@2',entries=[dict(subject='self',slot=slot,kind=kind,
                text=message['text'],extent='long_term',occurred_at='date unknown',
                evidence=[dict(ref=message['ref'],quote=message['text'])])])).encode()
        first_output=output(data,0,'diet.spicy','preference')
        first_receipt=json.loads(phase(first,'ending-first',prepared,first_output))
        assert first_receipt['receipts'][0]['status']=='active'
        # A reconstructed service reads the original status and exact result;
        # there is no second begin/provider and no cursor rewind.
        fresh=create_collection_app(conninfo_path=conninfo,auth_dir=auth,
            resolve_collection=lambda principal:(extraction,memory,lambda entry:(None,None))).state.memory_history.service
        assert json.loads(fresh.query_original(tokens['alice'],'ending-first','ending-first-attempt'))['processed_through']==100
        assert json.loads(fresh.query_publication_v2(tokens['alice'],'ending-first','ending-first-attempt'))==first_receipt
        _,tail_prepared,tail_data=enqueue(tail,'ending-tail')
        tail_receipt=json.loads(phase(tail,'ending-tail',tail_prepared,output(tail_data,0,'pace','inference')))
        assert tail_receipt['receipts'][0]['status']=='candidate'
        def discover(actor='alice',after=''):
            return client.get('/v5/memory-candidate-jobs',params=dict(conversation_id='long',after_job_id=after),headers=headers[actor])
        discovered=expected(discover())['result']
        assert discovered==dict(conversation_id='long',jobs=[dict(job_id='ending-tail',attempt_id='ending-tail-attempt')],next_after_job_id=None)
        actual_candidates=expected(client.get('/v3/memory-candidates',params=discovered['jobs'][0],headers=headers['alice']))['result']
        assert [item['candidate_id'] for item in actual_candidates['candidates']]==[tail_receipt['receipts'][0]['item_id']]
        assert expected(discover(after='ending-tail'))['result']['jobs']==[]
        expected(discover('bob'),503)
        from cj_api.local_app import ISSUER,scope_for
        scope=scope_for(ISSUER,'alice')
        with host.database.connect(scope) as connection:
            assert connection.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(2,)
            assert connection.execute('SELECT processed FROM cj_memory_history_cursor').fetchall()==[(101,)]
            assert connection.execute('SELECT count(*) FROM cj_memory_history_origin').fetchone()==(2,)
        # Separate incremental cursor, same canonical source ID: no duplicate item.
        incremental=SourceQuery(**dict(query.__dict__,mode='incremental'))
        expected(client.post('/internal/v1/memory-history/jobs',content=json.dumps(dict(version='MEMORY-JOBS@1',
            job_id='incremental',attempt_id='incremental-attempt',source=incremental.__dict__)).encode(),headers=headers['alice']))
        service.transition(tokens['alice'],'incremental','incremental-attempt','inflight')
        inc_prepared=service.prepare_model_input_v2(tokens['alice'],'incremental','incremental-attempt',max_payload_bytes=262144)
        def publish_incremental(context):
            policy=service.publication_policy_v2(context,tokens['alice'],'incremental','incremental-attempt',inc_prepared,
                hashlib.sha256(inc_prepared).hexdigest(),first_output,hashlib.sha256(first_output).hexdigest(),max_payload_bytes=262144)
            return context.with_enabled_source(incremental,policy,lambda snapshot:policy.apply_original_result(snapshot))
        reused=json.loads(host.boundary.with_history_context(tokens['alice'],publish_incremental))
        assert reused['receipts']==first_receipt['receipts']
        with host.database.connect(scope) as connection:
            assert connection.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(2,)
        print('PASS actual signed ending jobs persist 100+1 segments, independent ending/incremental cursors, Data2 real end, exact processing/publication2 and original result after host reconstruction; same source reuses canonical item; inference remains candidate')
        print('PASS signed chat candidate discovery returns actual original producer IDs; pagination and other-account denial, no fixture IDs or source renewal')
        try:read(first,'bob')
        except (Unavailable,MessageUnavailable):pass
        else:raise AssertionError('other account read a private ending segment')
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='disable',operation='disable',conversation_id='long',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=1))
        try:read(first)
        except (Unavailable,MessageUnavailable):pass
        else:raise AssertionError('withdrawn ending source was readable')
        assert json.loads(service.query_publication_v2(tokens['alice'],'ending-first','ending-first-attempt'))==first_receipt
        print('PASS actual 101 committed messages: real immutable end required, exact 100+1 segments/replay share its end ID, no truncation/Trip, other account and withdrawn source denied')


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='ending-source-') as tmp:
        with pg_suites.cluster('ending_source',port=55516,role='cj_ending_source',socket=f'/tmp/cj-ending-source-{os.getpid()}') as config:
            with psycopg.connect(**config,autocommit=True) as conn:migrate.up(conn,migrate.load(),migrate.load()[-1]['version'])
            root=Path(tmp);path=root/'conninfo.json';path.write_text(json.dumps(config))
            exercise(path,root/'auth')
