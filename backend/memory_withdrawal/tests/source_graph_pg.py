"""C read-only graph preparation across real automatic/confirm/edit sources."""
from datetime import datetime,timedelta,timezone
import json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import ISSUER,scope_for
from cj_memory.domain import Unavailable
from cj_memory.manual import ManualPolicy
from cj_memory.typed_api import create_local_typed_app
from cj_memory.typed_local import TypedConfiguration
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_withdrawal.source_graph import capture

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,migrate,pg_suites


def exercise(root,path):
    auth=root/'auth';dev_auth.init(auth,['graph-alice','graph-bob'])
    tokens={who:dev_auth.token(auth,who,30) for who in ('graph-alice','graph-bob')}
    headers={who:{'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'} for who,token in tokens.items()}
    deadline=datetime.now(timezone.utc)+timedelta(hours=1)
    extraction=CollectionPolicy(frozenset({'self'}),frozenset({'pace'}),5,4096,lambda entry:True,lambda entry,rows:False)
    memory=ManualPolicy(extraction.subjects,extraction.slots,frozenset({'long_term'}),frozenset(),deadline,
        lambda command,raw:True,lambda command,raw:True)
    app=create_collection_app(conninfo_path=path,auth_dir=auth,
        resolve_collection=lambda principal:(extraction,memory,lambda entry:(None,None)))
    host=app.state.memory_history;c=host.service;token=tokens['graph-alice']
    def expect(response):
        assert response.status_code==200,(response.status_code,response.text)
        return response.json()
    with TestClient(app) as client:
        def post(url,value):return expect(client.post(url,content=json.dumps(value).encode(),headers=headers['graph-alice']))
        head=expect(client.put('/v1/conversations',params={'conversation_id':'source'},headers=headers['graph-alice']))
        text='Maybe I prefer a slow pace'
        post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='source',message_id='origin',text=text,trip_id=None,
            creation_intent='none',expected_generation=head['generation'],expected_sequence=0))
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='source',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=0))
        source=dict(conversation_id='source',generation=head['generation'],epoch=0,after=0,through=1,source_version=1,withdrawal_epoch=1,mode='incremental')
        post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id='job',attempt_id='attempt',source=source))
        c.transition(token,'job','attempt','inflight')
        output=json.dumps(dict(version='MEMORY-EXTRACT@1',entries=[dict(subject='self',slot='pace',kind='inference',text=text,
            extent='long_term',occurred_at='date unknown',evidence=[dict(message_id='origin',quote=text)])])).encode()
        c.record_output(token,'job','attempt',output);c.publish_output(token,'job','attempt')
        listed=expect(client.get('/v3/memory-candidates',params={'job_id':'job','attempt_id':'attempt'},headers=headers['graph-alice']))['result']
        candidate=listed['candidates'][0];iid=candidate['candidate_id']
        post('/v3/memory-candidate-actions',dict(version='MEMORY-CANDIDATE@1',action_id='confirm',job_id='job',attempt_id='attempt',
            candidate_id=iid,expected_candidate_version=1,expected_memory_epoch=listed['memory_epoch'],operation='confirm',
            kind='preference',text='I prefer a slow pace',extent='long_term',context=None,occurred_at='date unknown'))
    profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
        extents=['long_term'],context_ids=[])
    config=TypedConfiguration.from_bytes(json.dumps(dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at=deadline.isoformat(),profiles={who:profile for who in tokens}),travel_contexts={who:[] for who in tokens})).encode())
    with TestClient(create_local_typed_app(conninfo_path=path,auth_dir=auth,configuration=config)) as manager:
        expect(manager.post('/v2/memory-management-actions',content=json.dumps(dict(version='MEMORY-management.2',action_id='edit',
            operation='edit',item_id=iid,expected_version=2,expected_source_version=1,context=None,text='I prefer a very slow pace')).encode(),headers=headers['graph-alice']))
    def graph(who='graph-alice',maximum=1_000_000):
        def read(context):
            repository,_,guard=c._binding(context,tokens[who])
            with repository.transaction() as transaction:
                raw=capture(transaction,iid,max_sources=1000,max_bytes=maximum)
                guard('graph_projection')
                return raw
        return host.boundary.with_history_context(tokens[who],read)
    raw=graph();value=json.loads(raw)
    assert value['item_version']==3 and len(value['source_refs'])==3 and value['scope_epoch']==4
    assert value['origin_producers']==[dict(job_id='job',attempt_id='attempt')]
    assert len(value['message_refs'])==1 and value['message_refs'][0]['message_id']=='origin'
    assert 'I prefer' not in raw.decode() and text not in raw.decode()
    assert graph()==raw
    for who,maximum in (('graph-bob',1_000_000),('graph-alice',1)):
        try:graph(who,maximum)
        except Unavailable:pass
        else:raise AssertionError('foreign or oversized graph exposed')
    # Controlled private-DB corruption: an otherwise valid selected-item source
    # not connected to any original transition must not disappear from the graph.
    scope=scope_for(ISSUER,'graph-alice');admin=json.loads(path.read_text())
    with psycopg.connect(**admin) as conn:
        stored=conn.execute('SELECT approved_input FROM cj_memory_source WHERE scope=%s AND source_id=%s',
            (scope,value['current_source_id'])).fetchone()[0]
        orphan=json.loads(bytes(stored));orphan.update(source_id='orphan-source',operation_id='orphan-op')
        conn.execute('''INSERT INTO cj_memory_source(scope,source_id,version,approved_input,authorized,confirmed,semantic_resolved,active,expires_at)
            VALUES(%s,'orphan-source',1,%s,true,true,true,true,%s)''',(scope,json.dumps(orphan).encode(),deadline))
    try:
        try:graph()
        except Unavailable:pass
        else:raise AssertionError('unlinked source was ignored')
    finally:
        with psycopg.connect(**admin) as conn:conn.execute("DELETE FROM cj_memory_source WHERE scope=%s AND source_id='orphan-source'",(scope,))
    assert graph()==raw
    print('PASS actual signed history candidate→confirmation→typed edit graph includes all three canonical sources and original message/producer refs; no values leaked, foreign/bounds/unlinked source denied, read-only stable; immutable cleanup descriptor/physical erasure UNRUN')


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='source-graph-') as folder:
        with pg_suites.cluster('source_graph',port=55523,role='cj_c_source_graph',socket=f'/tmp/cj-source-graph-{os.getpid()}') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
            root=Path(folder);path=root/'conninfo.json';path.write_text(json.dumps(config));path.chmod(0o600)
            exercise(root,path)
