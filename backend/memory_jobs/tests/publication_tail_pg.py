"""Real C COMMIT tail: elapsed time during final render cannot publish."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from cj_memory.manual import ManualPolicy
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs import model_v2
from cj_message.source import SourceQuery
from cj_api.local_app import ISSUER,scope_for
from cj_usage.metered_exit import BudgetExceeded

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,migrate,pg_suites


def exercise(conninfo,auth):
    dev_auth.init(auth,['tail-ok','tail-expired'])
    extraction=CollectionPolicy(frozenset({'self'}),frozenset({'diet.spicy'}),5,4096,
        lambda entry:True,lambda entry,rows:all(entry.text==row.text for row in rows))
    memory=ManualPolicy(extraction.subjects,extraction.slots,frozenset({'long_term'}),frozenset(),
        datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:True,lambda command,raw:True)
    app=create_collection_app(conninfo_path=conninfo,auth_dir=auth,
        resolve_collection=lambda principal:(extraction,memory,lambda entry:(None,None)))
    host=app.state.memory_history;c=host.service
    for subject in ('tail-ok','tail-expired'):
        token=dev_auth.token(auth,subject,30);headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
        def expect(response):
            assert response.status_code==200,(response.status_code,response.text)
            return response.json()
        with TestClient(app) as client:
            head=expect(client.put('/v1/conversations',params={'conversation_id':'source'},headers=headers))
            def post(url,value):return expect(client.post(url,content=json.dumps(value).encode(),headers=headers))
            post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='source',message_id='origin',text='No spicy food',
                trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0))
            post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='source',
                expected_generation=head['generation'],expected_epoch=0,expected_source_version=0))
            source=dict(conversation_id='source',generation=head['generation'],epoch=0,after=0,through=1,
                source_version=1,withdrawal_epoch=1,mode='incremental')
            post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id='job',attempt_id='attempt',source=source))
        c.transition(token,'job','attempt','inflight')
        prepared=c.prepare_model_input_v2(token,'job','attempt',max_payload_bytes=262144)
        message=json.loads(json.loads(prepared)['messages'][0]['content'])['messages'][0]
        output=json.dumps(dict(version='MEMORY-EXTRACT@2',entries=[dict(subject='self',slot='diet.spicy',kind='preference',
            text=message['text'],extent='long_term',occurred_at='date unknown',evidence=[dict(ref=message['ref'],quote=message['text'])])])).encode()
        tick=[0];events=[];renders=[0];original=model_v2.prepared
        def render(*args,**kwargs):
            result=original(*args,**kwargs)
            renders[0]+=1;events.append('actual-render-'+str(renders[0]))
            if subject=='tail-expired' and renders[0]==2:tick[0]+=10
            return result
        def before_commit():
            events.append('final-budget-check')
            if tick[0]>=10:raise BudgetExceeded('original publication deadline exceeded')
        def publish(context):
            policy=c.publication_policy_v3(context,token,'job','attempt',prepared,sha256(prepared).hexdigest(),output,
                sha256(output).hexdigest(),max_payload_bytes=262144,before_commit=before_commit)
            return context.with_enabled_source(SourceQuery(**source),policy,lambda snapshot:policy.apply_original_result(snapshot))
        with patch.object(model_v2,'prepared',render):
            if subject=='tail-expired':
                try:host.boundary.with_history_context(token,publish)
                except BudgetExceeded:pass
                else:raise AssertionError('final actual source rendering exceeded deadline but published')
            else:
                raw=host.boundary.with_history_context(token,publish)
                assert json.loads(raw)['receipts'][0]['status']=='active'
        assert events==['actual-render-1','actual-render-2','final-budget-check'],events
        with host.database.connect(scope_for(ISSUER,subject)) as conn:
            count=0 if subject=='tail-expired' else 1
            for table in ('cj_memory_item','cj_memory_source','cj_memory_operation','cj_memory_history_origin','cj_memory_history_cursor'):
                assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()==(count,),(subject,table)
            row=conn.execute('SELECT state,result_bytes,candidate,processed FROM cj_memory_history_job').fetchone()
            if count==0:assert row==('inflight',None,None,0),row
            else:assert row[0]=='completed' and bytes(row[1])==output and row[2] is not None and row[3]==1,row
        if subject=='tail-expired':assert c.query_publication_v2(token,'job','attempt')==b'null'
        else:assert c.query_publication_v2(token,'job','attempt')==raw
    print('PASS actual filtered-source final render then final budget callback before C COMMIT: expired case rolls canonical/source/origin/checkpoint/candidate/cursor back, positive exact result persists; no model/Meter claimed by this C-only probe')


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='publication-tail-') as folder:
        with pg_suites.cluster('publication_tail',port=55517,role='cj_publication_tail',socket=f'/tmp/cj-pub-tail-{os.getpid()}') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
            root=Path(folder);path=root/'conninfo.json';path.write_text(json.dumps(config));path.chmod(0o600)
            exercise(path,root/'auth')
