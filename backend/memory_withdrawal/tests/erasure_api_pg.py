"""Candidate signed deletion API reports real UNKNOWN without fake B cleanup."""
import json,os,sys,tempfile
from hashlib import sha256
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_cleanup import Configuration
from cj_cleanup.store import receipt_for
from cj_memory_withdrawal.erasure_app import create_erasure_app,create_erasure_app_v2
from cj_memory_withdrawal.erasure_command import VERSION
from cj_memory_withdrawal.erasure_service import ORDER
from cj_cleanup.core import encode
from cj_cleanup.core import Denied
from cj_memory_withdrawal.erasure_evidence import compare_prepared
from source_graph_pg import exercise as seed

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import migrate,pg_suites


def exercise(root,path,*,composition=1):
    f=seed(root,path);registry=root/'registry.json'
    stores=[dict(id='memory-derived',cleanup_protocol='CLEANUP@1.1'),
        dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),
        dict(id='business',objects=[dict(id=t.split('/')[1],cleanup_protocol='CLEANUP@1.1') for t in ORDER if t.startswith('business/')])]
    registry.write_bytes(encode(dict(version='erasure-api-observation-component',stores=stores)))
    config=Configuration({'local':b'candidate-erasure-api-component-key'},'local',3600,ORDER,registry)
    observed=[]
    class Unknown:
        def __init__(self,reader):self.reader=reader
        def execute(self,request):
            proof=json.loads(self.reader.read_evidence(request));job=proof['jobs'][0]
            assert compare_prepared(job,f['prepared'])==sha256(f['prepared']).hexdigest()
            assert sha256(job['original_utf8'].encode()).hexdigest()==job['original_input_sha256']
            assert job['publication_utf8'] is None  # Explicit legacy Collection completion, not Pub2/3.
            assert job['model_output_sha256'] is not None
            envelope=json.loads(f['prepared']);data=json.loads(envelope['messages'][0]['content']);data['messages'][0]['text']='unrelated bytes'
            envelope['messages'][0]['content']=json.dumps(data)
            try:compare_prepared(job,encode(envelope))
            except Denied:pass
            else:raise AssertionError('frozen source proof accepted unrelated prepared text')
            observed.append(('execute',request.target));return receipt_for(request,'unknown')
        def reconcile(self,request):observed.append(('reconcile',request.target));return receipt_for(request,'unknown')
    state=dict(ready=False,preflight=0)
    def backend(store,scope,reader):
        state['reader']=reader
        return {target:Unknown(reader) for target in ('business/message','checkpoints/run','business/usage')}
    @contextmanager
    def hold_payloads(store,scope,association,prototype):
        assert json.loads(association)['operation_id']==prototype.operation_id
        assert store.query(prototype.operation_id)['status']=='in_progress'
        assert observed==[]
        try:state['reader'].read_original(prototype)
        except Denied:pass
        else:raise AssertionError('pending preflight granted a physical erasure intent')
        state['preflight']+=1
        yield state['ready']
    options=dict(conninfo_path=path,auth_dir=f['auth'],resolve_collection=lambda principal:None,
                 cleanup_configuration=config,resolve_backend_hooks=backend)
    app=create_erasure_app_v2(**options,hold_payloads=hold_payloads) if composition==2 else create_erasure_app(**options)
    raw=encode(dict(version=VERSION,action_id='delete-action',item_id=f['item_id'],expected_version=3,derived_range='owned_trip_derived_scope'))
    with TestClient(app) as client:
        if composition==2:
            busy=client.post('/v1/memory-erasures',content=raw,headers=f['headers']['graph-alice'])
            assert busy.status_code==200,busy.text
            pending=busy.json()['result'];assert pending['online_status']=='in_progress'
            assert observed==[] and all(s['state']=='pending' for s in pending['steps'])
            state['ready']=True
        response=client.post('/v1/memory-erasures',content=raw,headers=f['headers']['graph-alice'])
        assert response.status_code==200,response.text
        result=response.json()['result'];assert result['stop_use']=='stopped' and result['online_status']=='unknown'
        assert observed==[('execute','business/message')]
        response=client.get('/v1/memory-erasure-progress',params={'action_id':'delete-action'},headers=f['headers']['graph-alice'])
        assert response.status_code==200 and response.json()['result']['online_status']=='unknown',response.text
        response=client.post('/v1/memory-erasures',content=raw,headers=f['headers']['graph-alice'])
        assert response.status_code==200 and response.json()['result']['online_status']=='unknown',response.text
        assert observed.count(('execute','business/message'))==1
        assert ('reconcile','business/message') in observed
        if composition==2:assert state['preflight']==2
        response=client.post('/v1/memory-erasures',content=raw+b' ',headers=f['headers']['graph-alice'])
        assert response.status_code==409,response.text
        foreign=client.get('/v1/memory-erasure-progress',params={'action_id':'delete-action'},headers=f['headers']['graph-bob'])
        assert foreign.status_code!=200 and 'result' not in foreign.json(),foreign.text
        invited=f['auth']/'invited.json';before=invited.read_bytes();dumps=json.dumps;revoked=[]
        def encode_response(value,*args,**kwargs):
            if type(value) is dict and value.get('version')=='MEMORY-ERASURE-response@1' and not revoked:
                invited.write_text(dumps([name for name in json.loads(before) if name!='graph-alice']));revoked.append(True)
            return dumps(value,*args,**kwargs)
        try:
            with patch.object(json,'dumps',encode_response):
                denied=client.get('/v1/memory-erasure-progress',params={'action_id':'delete-action'},headers=f['headers']['graph-alice'])
            assert revoked==[True] and denied.status_code==403 and 'result' not in denied.json(),denied.text
        finally:invited.write_bytes(before)
    with psycopg.connect(**json.loads(path.read_text())) as conn:
        assert conn.execute('SELECT status FROM cj_memory_item WHERE scope=%s AND item_id=%s',(f['scope'],f['item_id'])).fetchone()==('withdrawn',)
        assert conn.execute('SELECT count(*) FROM cj_memory_erasure_manifest WHERE scope=%s',(f['scope'],)).fetchone()==(1,)
    print('PASS candidate signed API freezes exact selected item, stops use, reports genuine UNKNOWN with no fake B erasure; read/repeated POST reconcile original without redispatch, byte alias conflicts, other owner/final-encode withdrawal deny. Backend test hooks observation-only, complete deletion UNRUN')


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='c-erasure-api-') as folder:
        root=Path(folder)
        if os.environ.get('CJ_E2E_CONNINFO'):
            exercise(root,Path(os.environ['CJ_E2E_CONNINFO']))
            sys.exit(0)
        with pg_suites.cluster('item_api',port=55818,role='cj_c_item_api',root=root/'pg',socket=root/'s') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                migrate.up(conn,migrate.load(),44)
            path=root/'conninfo.json';path.write_text(json.dumps(config));path.chmod(0o600);exercise(root,path)
