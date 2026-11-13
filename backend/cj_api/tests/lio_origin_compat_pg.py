"""Signed private PG origin/legacy/rollback/cleanup guards, no provider calls.

The test's future-wire producer calls the real authenticated admission service;
production HTTP v3 stays absent. Full Part2-to-Part1 app evidence is separate.
"""
import json,time,tempfile
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import psycopg
from fastapi.testclient import TestClient
from fastapi import FastAPI
from cj_api.local_app import LocalDatabase,create_local_app,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_message.travel import ABI
import dev_auth,local_run_context,migrate,pg_suites


def exercise(work,config):
    evidence=work/'evidence';evidence.mkdir()
    auth=work/'auth';rp=work/'run.json'
    subjects=('compat-new-owner','compat-legacy-owner');owner=scope_for(ISSUER,subjects[0])
    context=load_run_context(rp);database=LocalDatabase(work/'connection.json',run_context=context,travel_context=True,needs_context=True)
    headers={s:{'Authorization':'Bearer '+dev_auth.token(auth,s,300),'Content-Type':'application/octet-stream'} for s in subjects}
    from cj_cleanup.core import encode,digest
    from cj_api.local_cleanup import Configuration
    registry=work/'cleanup-registry.json';registry.write_bytes(encode(dict(version='compat-message-run-component',stores=[dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),dict(id='business',objects=[dict(id='message',cleanup_protocol='CLEANUP@1.1')])])))
    options=Configuration({'local':b'synthetic-compat-cleanup-key-00000'},'local',3600,('checkpoints/run','business/message'),registry)
    from cj_api.lio_dialogue_routes import register_lio_dialogue_routes
    captured={}
    def capture_routes(*args,**kwargs):
        captured['boundary']=args[1];captured['prepare_scope']=kwargs['prepare_scope']
        captured['args']=args;captured['kwargs']=dict(kwargs)
        return register_lio_dialogue_routes(*args,**kwargs)
    with patch('cj_api.lio_dialogue_routes.register_lio_dialogue_routes',side_effect=capture_routes):
        app=create_local_app(conninfo_path=None,auth_dir=auth,database=database,run_context=context,account_admission=True,demo_dialogue_subjects=frozenset(subjects),lio_dialogue_subjects=frozenset(subjects),cleanup_configuration=options)
    # Keep the original legacy-consumer contract test even when the newer
    # application explicitly installs its separate calendar routes.
    legacy_app=FastAPI()
    legacy_options={key:value for key,value in captured['kwargs'].items() if key!='calendar_cards'}
    register_lio_dialogue_routes(legacy_app,*captured['args'][1:],**legacy_options)
    def dump():
        # Logical exact-byte dump of all protected business/ledger/deletion-fence rows.
        tables=('cj_message_receipt','cj_message_chat','cj_message_delivery','cj_message_needs_binding','cj_trip_record','cj_trip_proposal','cj_trip_receipt','cj_trip_needs_basis','cj_trip_needs_action','cj_usage_ledger_candidate','cj_run_record','cj_run_event','cj_run_step_usage','cj_run_metered_operation','cj_memory_scope','cj_memory_item','cj_account_fence','cj_cleanup_operation','cj_cleanup_request')
        with psycopg.connect(**config) as db:return {t:[r[0] for r in db.execute('SELECT row_to_json(t)::text FROM '+t+' t ORDER BY row_to_json(t)::text')] for t in tables}
    with TestClient(app) as api:
            older=encode(dict(version='LIO-message.2',message_id='compat-earlier-v2',text='EARLIER_V2',locale='en',new_conversation=True))
            earlier=api.post('/v2/lio/messages',headers=headers[subjects[0]],content=older)
            assert earlier.status_code==200,earlier.text
            mixed_cid=earlier.json()['conversation_id']
            assert api.get('/v2/lio/messages',headers=headers[subjects[0]],params=dict(message_id='compat-earlier-v2',input_sha256=sha256(older).hexdigest())).status_code==200
            raw=json.dumps(dict(version='LIO-message.3',message_id='compat-original-v3',text='SYNTHETIC_FUTURE_WIRE',locale='en',conversation_id=mixed_cid),indent=1).encode()
            captured['boundary'].receive_lio(dev_auth.token(auth,subjects[0],300),raw,prepare_scope=captured['prepare_scope'],version='LIO-message.3')
            with psycopg.connect(**config) as db:
                row=db.execute('SELECT conversation_id,generation,sequence,run_id,input_sha256,raw_input,demo_dialogue_protocol,lio_wire_protocol,lio_wire_input FROM cj_message_receipt WHERE scope=%s AND message_id=%s',(owner,'compat-original-v3')).fetchone()
                assert row[6:] == ('LIO-message.1','LIO-message.3',raw),row
                assert bytes(row[5])!=raw
                (evidence/'original.core.bin').write_bytes(bytes(row[5]));(evidence/'original.wire.bin').write_bytes(raw)
            result=dict(mid='compat-original-v3',cid=row[0],generation=row[1],sequence=row[2],run_id=row[3],core_sha256=row[4],outer_sha256=sha256(raw).hexdigest(),producer='authenticated internal future-wire admission, not an exposed HTTP route')
            (evidence/'seed.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
            before_down=dump()
            with psycopg.connect(**config,autocommit=True) as db:
                try:migrate.down(db,migrate.load(),52)
                except psycopg.errors.RaiseException as error:
                    assert error.sqlstate=='P0001' and 'Lio wire originals must be preserved' in str(error)
                else:raise AssertionError('rollback deleted a saved newer wire')
                assert migrate.applied(db)[-1]==53
            assert dump()==before_down
            seed=json.loads((evidence/'seed.json').read_text());before=dump();(evidence/'before-denials.json').write_text(json.dumps(before,indent=2))
            statuses={}
            for name,url,params in (('lookup','/v2/lio/messages',dict(message_id=seed['mid'],input_sha256=seed['outer_sha256'])),('timeline','/v2/lio/timeline',dict(conversation_id=seed['cid']))):
                r=api.get(url,headers=headers[subjects[0]],params=params);statuses[name]=r.status_code;assert r.status_code==400,r.text
            for name,url,params in (
                ('older_lookup','/v2/lio/messages',dict(message_id='compat-earlier-v2',input_sha256=sha256(older).hexdigest())),
                ('older_page','/v2/lio/timeline',dict(conversation_id=seed['cid'],before=seed['mid'])),
                ('empty_older_page','/v2/lio/timeline',dict(conversation_id=seed['cid'],before='compat-earlier-v2'))):
                r=api.get(url,headers=headers[subjects[0]],params=params);statuses[name]=r.status_code;assert r.status_code==400,r.text
            r=api.post('/v2/lio/messages',headers=headers[subjects[0]],content=encode(dict(version='LIO-message.2',message_id='compat-denied-v2',text='MUST_NOT_APPEND',locale='en',conversation_id=seed['cid'])));statuses['append']=r.status_code;assert r.status_code==400,r.text
            with TestClient(legacy_app) as legacy_api:
                r=legacy_api.post('/v3/lio/messages',headers=headers[subjects[0]],content=(evidence/'original.wire.bin').read_bytes())
                statuses['legacy_v3_route_absent']=r.status_code;assert r.status_code==404,r.text
            # Real production factory + real native receipt + actual _one/worker lease.
            from cj_api.local_account_admission_v2 import account_checker_for
            from cj_agent.provider import FakeProvider
            from cj_run.core import Service
            import run_worker
            calls=dict(run_accept=0,started=0,memory=0,model=0,meter=0,tools=0)
            class Model(FakeProvider):
                def stream(self,*a,**k):calls['model']+=1;raise AssertionError('model reached')
            class Memory:
                def capture(self,*a,**k):calls['memory']+=1;raise AssertionError('memory reached')
            class Tools:
                def answer(self,*a,**k):calls['tools']+=1;raise AssertionError('tools reached')
            worker=run_worker._worker_for_scope(database,Model(),auth,owner,account_checker_for(auth,database),demo_planning=True)
            assert worker.lio_original is not None
            worker.memory=Memory();worker.memory_history=True;worker.history_adapter=worker.memory;worker.tools=Tools()
            accept=Service.accept;event=type(worker)._event
            def denied_accept(*a,**k):calls['run_accept']+=1;return accept(*a,**k)
            def observed_event(self,binding,state,kind,*a,**k):
                if kind=='started':calls['started']+=1
                return event(self,binding,state,kind,*a,**k)
            def meter(*a,**k):calls['meter']+=1;raise AssertionError('meter reached')
            receipt=worker.messages.query(seed['mid']).receipt;error=None
            with patch.object(Service,'accept',denied_accept),patch.object(type(worker),'_event',observed_event),patch.object(type(worker.budget_exit),'for_run',meter):
                try:worker._one(receipt)
                except Exception as exc:error=dict(type=type(exc).__module__+'.'+type(exc).__name__,message=str(exc))
                else:raise AssertionError('new wire consumed by compat worker')
            assert error==dict(type='cj_message.domain.Unavailable',message='newer Lio original requires its selected calendar worker'),error
            assert all(v==0 for v in calls.values()),calls
            after=dump();assert after==before
            (evidence/'after-denials.json').write_text(json.dumps(after,indent=2))
            guard=dict(error=error,calls=calls,all_business_ledger_fence_rows_exactly_unchanged=True)
            # Native legacy v2 still accepts, looks up, lists, and appends on schema53.
            legacy=[];cid=None
            for mid,text in (('legacy-v2-first','LEGACY_V2_FIRST'),('legacy-v2-append','LEGACY_V2_APPEND')):
                raw=encode(dict(version='LIO-message.2',message_id=mid,text=text,locale='en',**({'new_conversation':True} if cid is None else {'conversation_id':cid})))
                r=api.post('/v2/lio/messages',headers=headers[subjects[1]],content=raw);assert r.status_code==200,r.text
                cid=r.json()['conversation_id'];legacy.append(dict(mid=mid,sha256=sha256(raw).hexdigest(),send_status=r.status_code))
                found=api.get('/v2/lio/messages',headers=headers[subjects[1]],params=dict(message_id=mid,input_sha256=sha256(raw).hexdigest()));assert found.status_code==200 and found.json()['receipt']['message_id']==mid,found.text
            timeline=api.get('/v2/lio/timeline',headers=headers[subjects[1]],params=dict(conversation_id=cid));assert timeline.status_code==200,timeline.text
            assert [x['message_id'] for x in timeline.json()['messages']]==[x['mid'] for x in legacy]
            with psycopg.connect(**config) as db:
                assert db.execute('SELECT demo_dialogue_protocol,lio_wire_protocol,lio_wire_input FROM cj_message_receipt WHERE scope=%s ORDER BY sequence',(scope_for(ISSUER,subjects[1]),)).fetchall()==[('LIO-message.1',None,None)]*2
            # Same fenced account component workflow as earlier review, dedicated role.
            stable=dump();# Compare the foreign owner's exact original rows after cleanup.
            def post(url,value,who,status=200):
                r=api.post(url,headers=headers[who],content=encode(value));assert r.status_code==status,r.text
                return r.json()
            device=post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='compat-device',device_id='compat-local-device',state_ref=digest(b'compat-local-state')),subjects[0])
            prepared=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='compat-cleanup',binding_id=device['binding_id']),subjects[0]);op=prepared['operation_id']
            confirmation=dict(version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT')
            before_foreign_confirm=dump();post('/v1/account-cleanup-operations/'+op+'/confirmation',confirmation,subjects[1],403);assert dump()==before_foreign_confirm
            from cj_cleanup.account_hooks import DomainHook
            hook_calls=[];execute=DomainHook.execute
            def observe(self,request):
                with self.store.transaction(request.operation_id,writing=False) as cur:
                    assert cur.execute('SELECT current_user').fetchone()==('cj_local_cleanup',)
                result=execute(self,request);hook_calls.append(dict(target=request.target,outcome=result.outcome,role='cj_local_cleanup'));return result
            with patch.object(DomainHook,'execute',observe):cleaned=post('/v1/account-cleanup-operations/'+op+'/confirmation',confirmation,subjects[0])
            assert cleaned['online_status']=='complete' and len(hook_calls)==2,cleaned
            final=dump();current_rows=[json.loads(s) for s in final['cj_message_receipt']];prior_rows=[json.loads(s) for s in stable['cj_message_receipt']]
            assert [r for r in current_rows if r['scope']==owner]==[]
            foreign=scope_for(ISSUER,subjects[1]);assert [r for r in current_rows if r['scope']==foreign]==[r for r in prior_rows if r['scope']==foreign]
            with psycopg.connect(**config) as db:
                assert db.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='cj_message_receipt'::regclass").fetchone()==(True,True)
                assert db.execute("SELECT has_table_privilege('cj_m1_runtime','cj_message_receipt','DELETE'),has_table_privilege('cj_m1_runtime','cj_message_receipt','TRUNCATE'),has_table_privilege('cj_local_cleanup','cj_message_receipt','UPDATE'),has_table_privilege('cj_local_cleanup','cj_message_receipt','TRUNCATE')").fetchone()==(False,False,False,False)
            result=dict(statuses=statuses,worker=guard,legacy=dict(send_lookup_timeline_append='PASS',messages=legacy),cleanup=dict(actual_http_component_workflow=True,privileged_delete_used=False,hook_calls=hook_calls,new_owner_core_wire_rows_removed=True,foreign_exact_bytes_preserved=True,foreign_confirmation_status=403,forced_rls_and_acl_unchanged=True,online_status=cleaned['online_status'],aggregate_status=cleaned['status']))
            (evidence/'compat-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='g2c-origin-compat-') as directory:
        work=Path(directory)
        with pg_suites.cluster('origin-compat',port=55827,role='cj_origin_compat_initializer',root=work/'pg',socket=work/'s') as config:
            with psycopg.connect(**config,autocommit=True) as db:
                migrations=migrate.load();migrate.up(db,migrations,53)
                migrate.down(db,migrations,52);migrate.up(db,migrations,53)
            (work/'connection.json').write_text(json.dumps(config))
            subjects=('compat-new-owner','compat-legacy-owner');dev_auth.init(work/'auth',list(subjects))
            now=int(time.time());run=dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=20,period_start=now-60,period_end=now+3600,max_steps=20,max_tools=10,max_output=10000,max_seconds=600),output_limits=dict(model=2000,tool=2000,memory=2000)),history=[])
            (work/'run.json').write_text(json.dumps(run));context=load_run_context(work/'run.json')
            for subject in subjects:
                local_run_context.provision_budget(work/'connection.json',context,subject)
                dev_auth.activate_travel(work/'connection.json',subject,context,ABI)
            exercise(work,config)
    print('PASS signed origin compatibility, old v2, rollback data preservation and fenced component cleanup; zero supplier calls',flush=True)


if __name__=='__main__':main()
