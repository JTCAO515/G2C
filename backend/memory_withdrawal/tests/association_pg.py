"""Actual source graph plus overlapping pending/UNKNOWN C job inventory."""
import json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from cj_memory.domain import Conflict,Unavailable
from cj_memory_withdrawal.association import prepare
from cj_memory_jobs.collection_app import create_collection_app
from source_graph_pg import exercise as seed

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import migrate,pg_suites


def exercise(root,path):
    fixture=seed(root,path);alice=fixture['tokens']['graph-alice'];headers=fixture['headers']['graph-alice']
    app=create_collection_app(conninfo_path=path,auth_dir=fixture['auth'],resolve_collection=lambda principal:None)
    host=app.state.memory_history
    service=host.service
    def ok(response):
        assert response.status_code==200,(response.status_code,response.text)
        return response.json()
    with TestClient(app) as client:
        head=ok(client.get('/v3/memory-history-settings',params={'conversation_id':'source'},headers=headers))['result']
        end=dict(version='MESSAGE-SOURCE@1',conversation_id='source',generation=head['generation'],epoch=0,through=1,conversation_type='travel')
        ok(client.post('/internal/v1/conversation-end',content=json.dumps(end).encode(),headers=headers))
        source=dict(conversation_id='source',generation=head['generation'],epoch=0,after=0,through=1,source_version=1,withdrawal_epoch=1,mode='conversation_end')
        service.enqueue(alice,json.dumps(dict(version='MEMORY-JOBS@1',job_id='end-unknown',attempt_id='end-attempt',source=source)).encode())
        service.transition(alice,'end-unknown','end-attempt','inflight');service.transition(alice,'end-unknown','end-attempt','unknown')
        for aid,op,version in (('off','disable',1),('on','enable',2)):
            ok(client.post('/v3/memory-history-actions',content=json.dumps(dict(version='MEMORY-HISTORY@1',action_id=aid,operation=op,
                conversation_id='source',expected_generation=head['generation'],expected_epoch=0,expected_source_version=version)).encode(),headers=headers))
        source.update(source_version=3,mode='incremental')
        service.enqueue(alice,json.dumps(dict(version='MEMORY-JOBS@1',job_id='new-pending',attempt_id='new-attempt',source=source)).encode())
        for aid,op,version in (('off-again','disable',3),('on-again','enable',4)):
            ok(client.post('/v3/memory-history-actions',content=json.dumps(dict(version='MEMORY-HISTORY@1',action_id=aid,operation=op,
                conversation_id='source',expected_generation=head['generation'],expected_epoch=0,expected_source_version=version)).encode(),headers=headers))
        source.update(source_version=5)
        service.enqueue(alice,json.dumps(dict(version='MEMORY-JOBS@1',job_id='latest-inflight',attempt_id='latest-attempt',source=source)).encode())
        service.transition(alice,'latest-inflight','latest-attempt','inflight')
    def read(who='graph-alice',max_jobs=1000,epoch=4):
        token=fixture['tokens'][who]
        def project(context):
            repository,_,guard=service._binding(context,token)
            with repository.transaction() as memory:
                raw=prepare(memory,fixture['item_id'],expected_version=3,expected_scope_epoch=epoch,
                    max_sources=1000,max_jobs=max_jobs,max_bytes=1_000_000)
                guard('erasure_association_comparison');return raw
        return host.boundary.with_history_context(token,project)
    raw=read();value=json.loads(raw)
    assert {ref['job_id']:ref['state'] for ref in value['job_refs']}==dict(job='completed',**{
        'end-unknown':'unknown','new-pending':'pending','latest-inflight':'inflight'})
    assert len(value['source_refs'])==len(value['operation_refs'])==3
    assert len(value['message_refs'])==1 and 'I prefer' not in raw.decode()
    assert read()==raw
    for who,bound,epoch in (('graph-bob',1000,4),('graph-alice',1,4),('graph-alice',1000,5)):
        try:read(who,bound,epoch)
        except (Conflict,Unavailable):pass
        else:raise AssertionError('foreign, incomplete or stale association accepted')
    assert json.loads(service.query_original(alice,'end-unknown','end-attempt'))['state']=='unknown'
    print('PASS actual bounded read-only erasure association covers three canonical source command identities plus save-ledger originals and ALL completed/UNKNOWN/pending/inflight overlapping jobs across consent versions; exact refs/no text, stable bytes, foreign/stale/bound failures; no intent/store/erasure authority')


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='c-erasure-association-') as folder:
        root=Path(folder)
        with pg_suites.cluster('c_erasure_association',port=55797,role='cj_c_association',root=root/'pg',socket=root/'s') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
            path=root/'conninfo.json';path.write_text(json.dumps(config));path.chmod(0o600)
            exercise(root,path)
