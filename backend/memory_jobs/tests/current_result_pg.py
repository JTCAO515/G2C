"""Signed typed source -> C publication -> original normal run_once/Meter/Fake.

Extraction output is supplied. The normal answer worker is actual; this is not
the still-separate background extraction producer or real model quality.
"""
from datetime import datetime,timedelta,timezone
import hashlib,json,os,sys,tempfile,time,subprocess
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from cj_agent.provider import FakeProvider
from cj_api.local_app import scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_message.source import SourceQuery
from cj_message.travel import ABI,Selection
from cj_memory.domain import Unavailable as MemoryUnavailable
from cj_memory.manual import ManualPolicy
from cj_memory.typed_api import create_local_typed_app
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.codec import Unavailable

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,local_run_context as operator,migrate,pg_suites


class Observed(FakeProvider):
    def __init__(self,after_first=None):
        super().__init__();self.inputs=[];self.after_first=after_first
    def stream(self,messages,system=None):
        self.inputs.append((messages,system))
        data=json.loads(messages[0]['content'].split('\n',1)[1])
        prefix='Synthetic selected memory: '+json.dumps(data['items'],ensure_ascii=False)+'\n'
        for index,chunk in enumerate(super().stream(messages,system)):
            yield (prefix if index==0 else '')+chunk
            if index==0 and self.after_first is not None:self.after_first()


def exercise(conninfo,auth):
    import run_worker
    dev_auth.init(auth,['alice','bob'])
    now=int(time.time());path=auth/'run.json'
    path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(
        unit='provider_call',budget=100,period_start=now-60,period_end=now+3600,
        max_steps=20,max_tools=10,max_output=40000,max_seconds=600),
        output_limits=dict(model=4000,tool=8000,memory=4000)),history=[])))
    run=load_run_context(path)
    for who in ('alice','bob'):
        operator.provision_budget(conninfo,run,who)
        dev_auth.activate_travel(conninfo,who,run,ABI)
    tokens={who:dev_auth.token(auth,who,30) for who in ('alice','bob')}
    headers={who:{'Authorization':'Bearer '+value,'Content-Type':'application/octet-stream'} for who,value in tokens.items()}
    slot_kinds={'diet.spicy':'preference','pace':'preference','mobility.temporary':'fact',
                'interests.art':'preference','experience.visit':'experience'}
    common_slots=['diet.spicy','pace','mobility.temporary','interests.art']
    deadline=datetime.now(timezone.utc)+timedelta(hours=1)
    allowed={};travels=[]
    def content(entry):
        return all((entry.subject,entry.slot,entry.kind,entry.text,entry.extent)==allowed[e.message_id] for e in entry.evidence)
    extraction=CollectionPolicy(frozenset({'self','companion:one'}),frozenset(slot_kinds),10,4096,
        content,lambda entry,rows:entry.kind!='inference' and all(entry.text==row.text for row in rows))
    def resolve(principal):
        if principal.subject not in tokens:raise MemoryUnavailable('fixture identity unavailable')
        policy=ManualPolicy(extraction.subjects,extraction.slots,frozenset({'long_term','current'}),
            frozenset(t['id'] for t in travels) if principal.subject=='alice' else frozenset(),
            deadline,lambda command,raw:command.slot in slot_kinds,lambda command,raw:True)
        return extraction,policy,lambda entry:(None,None)
    app=create_collection_app(conninfo_path=conninfo,auth_dir=auth,resolve_collection=resolve,run_context=run)
    host=app.state.memory_history;service=host.service
    def expect(response,code=200):
        assert response.status_code==code,(response.status_code,response.text)
        return response.json()
    with TestClient(app) as client:
        def post(url,value,who='alice',code=200):
            return expect(client.post(url,content=json.dumps(value,ensure_ascii=False).encode(),headers=headers[who]),code)
        for label in ('A','B'):
            travels.append(post('/v1/travel-context-actions',dict(version='TRAVEL-context-action.1',action_id='travel-'+label,
                operation='create',travel_context=None))['receipt']['travel_context'])
        def send(chat,mid,text,selected,who='alice'):
            head=expect(client.put('/v1/conversations',params={'conversation_id':chat},headers=headers[who]))
            post('/v2/messages',dict(version='MESSAGE-send.2',conversation_id=chat,message_id=mid,text=text,trip_id=None,
                creation_intent='none',expected_generation=head['generation'],expected_sequence=head['last_sequence'],
                travel_context=None if selected is None else dict(id=selected['id'],expected_version=selected['version']),
                needs_reference=None),who)
            return head
        records=[('self','diet.spicy','preference','No spicy food / 不吃辣','long_term'),
                 ('self','pace','preference','Normally a slow pace / 通常慢节奏','long_term'),
                 ('self','pace','preference','Fast pace only for this trip / 本次快节奏','current'),
                 ('self','mobility.temporary','fact','My leg hurts for this trip / 本次腿伤','current'),
                 ('companion:one','diet.spicy','preference','My companion likes spicy food / 同伴爱辣','long_term'),
                 ('self','interests.art','inference','Maybe I like art / 也许喜欢艺术','long_term'),
                 ('self','experience.visit','experience','Visited a synthetic museum / 去过测试博物馆','long_term')]
        entries=[]
        for index,record in enumerate(records):
            subject,slot,kind,text,extent=record;mid=f'seed-{index}'
            head=send('source',mid,text,travels[0])
            allowed[mid]=record
            entries.append(dict(subject=subject,slot=slot,kind=kind,text=text,extent=extent,
                occurred_at='date unknown',evidence=[dict(message_id=mid,quote=text)]))
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',
            conversation_id='source',expected_generation=head['generation'],expected_epoch=0,expected_source_version=0))
        source=dict(conversation_id='source',generation=head['generation'],epoch=0,after=0,through=len(records),
                    source_version=1,withdrawal_epoch=1,mode='incremental')
        post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id='typed-job',attempt_id='typed-attempt',source=source))
        service.transition(tokens['alice'],'typed-job','typed-attempt','inflight')
        prepared=service.prepare_model_input(tokens['alice'],'typed-job','typed-attempt',max_payload_bytes=262144)
        output=json.dumps(dict(version='MEMORY-EXTRACT@1',entries=entries),ensure_ascii=False).encode()
        def publish(selected):
            def stage(context):
                policy=service.publication_policy(context,tokens['alice'],'typed-job','typed-attempt',prepared,
                    hashlib.sha256(prepared).hexdigest(),output,hashlib.sha256(output).hexdigest(),max_payload_bytes=262144)
                return context.with_enabled_source_and_travel(SourceQuery(**source),policy,Selection(selected['id'],selected['version']),
                    lambda snapshot,lease:policy.apply_original_result(snapshot,lease))
            return host.boundary.with_history_context(tokens['alice'],stage)
        try:publish(travels[1])
        except Unavailable:pass
        else:raise AssertionError('same-owner other Travel retargeted current source')
        scope=scope_for(ISSUER,'alice')
        with host.database.connect(scope) as conn:
            assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(0,)
            assert conn.execute('SELECT result_bytes FROM cj_memory_history_job').fetchone()==(None,)
        result=json.loads(publish(travels[0]))
        assert [r['status'] for r in result['receipts']]==['active']*5+['candidate','active']
        with host.database.connect(scope) as conn:
            assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(7,)
        print('PASS actual signed MESSAGE-send.2 source + genuine SOURCE@2 lease publishes current and long-term entries; wrong owned Travel rolls all entries/checkpoint back')
        profile=dict(subjects=['self','companion:one'],slots={slot:dict(kind=kind,collection_allowed=True,semantic_resolved=True)
            for slot,kind in slot_kinds.items()},extents=['long_term','current'],context_ids=[])
        document=dict(version='local-memory-run.2',collection=dict(version='local-memory-typed.1',
            collection=dict(version='local-memory-policy.1',expires_at=deadline.isoformat(),profiles={'alice':profile,'bob':profile}),
            travel_contexts={'alice':[t['id'] for t in travels],'bob':[]}),
            selections={who:dict(subject='self',slots=common_slots,max_bytes=32768) for who in tokens})
        configuration=TypedRuntimeConfiguration.from_bytes(json.dumps(document).encode())
        def answer(chat,mid,text,selected,who='alice',*,after_first=None):
            send(chat,mid,text,selected,who)
            model=Observed(after_first)
            outcomes=run_worker.run_once(host.database,model,auth,memory_configuration=configuration)
            outcome=next(o for o in outcomes if o.message_id==mid)
            display=expect(client.get('/v2/run-display',params={'message_id':mid},headers=headers[who]))['snapshot']
            data=json.loads(model.inputs[-1][0][0]['content'].split('\n',1)[1])
            return outcome,display,data,model
        wanted={'diet.spicy':records[0][3],'pace':records[2][3],'mobility.temporary':records[3][3]}
        for chat,mid,text,selected,who,values in (
                ('source','next-en','Can we plan food and walking?',travels[0],'alice',wanted),
                ('new-chat','next-cn','饮食与步行怎么安排？',travels[0],'alice',wanted),
                ('other-travel','next-other','Food and pace for another trip?',travels[1],'alice',
                 {'diet.spicy':records[0][3],'pace':records[1][3]}),
                ('no-travel','next-none','What general preferences are saved?',None,'alice',
                 {'diet.spicy':records[0][3],'pace':records[1][3]}),
                ('bob-chat','bob-question','What do you know about my preferences?',None,'bob',{})):
            outcome,display,data,model=answer(chat,mid,text,selected,who)
            assert outcome.status=='completed' and display['status']=='completed'
            assert {i['slot']:i['text'] for i in data['items']}==values
            assert all(value in display['text'] for value in values.values())
            assert records[4][3] not in display['text'] and records[5][3] not in display['text']
            assert records[6][3] not in display['text']  # Explicitly irrelevant canonical slot.
            assert all(i['subject']=='self' for i in data['items'])
        print('PASS actual original run_once + registered Meter + FakeProvider and signed RUN-display: same chat, Chinese/new chat, other Travel, no Travel and other account use canonical scoped source; companion/inference excluded')
        relevant=json.loads(json.dumps(document))
        for selected in relevant['selections'].values():selected['slots']=['experience.visit']
        configuration=TypedRuntimeConfiguration.from_bytes(json.dumps(relevant).encode())
        outcome,display,data,_=answer('experience-chat','experience-question','Which museum did I visit?',None)
        assert {i['slot']:i['text'] for i in data['items']}=={'experience.visit':records[6][3]}
        assert records[6][3] in display['text'] and records[0][3] not in display['text']
        configuration=TypedRuntimeConfiguration.from_bytes(json.dumps(document).encode())
        print('PASS actual experience entry and bounded canonical slot selection: irrelevant saved history is omitted; the relevant source is selected for a different question')
        runtime_path=auth/'memory-runtime.json';runtime_path.write_text(json.dumps(document));runtime_path.chmod(0o600)
        send('process-restart','process-question','Food and walking from a fresh process?',travels[0])
        process=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--resume',str(conninfo),str(auth),
            str(path),str(runtime_path)],capture_output=True,text=True,timeout=60,env=pg_suites.clean_env())
        assert process.returncode==0,process.stderr
        fresh=json.loads(process.stdout)
        assert [o['status'] for o in fresh['outcomes'] if o['message_id']=='process-question']==['completed']
        fresh_data=json.loads(fresh['inputs'][0][0][0]['content'].split('\n',1)[1])
        assert {i['slot']:i['text'] for i in fresh_data['items']}==wanted
        cli_mid='cli-question';send('cli-restart',cli_mid,'Original CLI with retained memory?',travels[0])
        cli=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/run_worker.py'),'--conninfo-json',str(conninfo),
            '--auth-dir',str(auth),'--run-context',str(path),'--travel-context','message-travel.1',
            '--memory-run-policy',str(runtime_path),'--once'],capture_output=True,text=True,timeout=60,env=pg_suites.clean_env())
        assert cli.returncode==0,cli.stderr
        assert expect(client.get('/v3/run-draft-status',params={'message_id':cli_mid},headers=headers['alice']))['run_status']=='completed'
        print('PASS actual fresh Python worker observes the same canonical context; unchanged original run_worker CLI accepts the typed runtime and completes its original message')
        # Reconstruct the worker database and configuration before another answer.
        from cj_api.local_app import LocalDatabase
        host=type(host)(LocalDatabase(conninfo,run_context=run,travel_context=True),host.boundary,host.service)
        configuration=TypedRuntimeConfiguration.from_bytes(json.dumps(document).encode())
        outcome,display,data,_=answer('restart','restart-question','Plan food and walking after restart?',travels[0])
        assert {i['slot']:i['text'] for i in data['items']}==wanted
        typed=create_local_typed_app(conninfo_path=conninfo,auth_dir=auth,configuration=configuration.collection)
        with TestClient(typed) as manager:
            mobility=result['receipts'][3]
            def pause():
                expect(manager.post('/v2/memory-management-actions',content=json.dumps(dict(version='MEMORY-management.2',
                    action_id='pause-mobility',operation='pause',item_id=mobility['item_id'],expected_version=1,
                    expected_source_version=1)).encode(),headers=headers['alice']))
            outcome,display,_,model=answer('restart','inflight-pause','Walking while state changes?',travels[0],after_first=pause)
            assert outcome.status=='context_invalid' and display['status']!='completed' and display['text_state']!='complete'
            assert model.calls==1
            outcome,display,data,_=answer('restart','after-pause','What remains for this trip?',travels[0])
            assert {i['slot'] for i in data['items']}=={'diet.spicy','pace'}
            pace=result['receipts'][2]
            item=expect(manager.get('/v2/memory-items',params={'item_id':pace['item_id']},headers=headers['alice']))['item']['command']
            expect(manager.post('/v2/memory-withdrawal-actions',content=json.dumps(dict(version='MEMORY-STOP-USE@2',
                action_id='withdraw-current-pace',operation='withdraw',item_id=pace['item_id'],expected_version=1,
                source_id=item['source_id'],expected_source_version=1)).encode(),headers=headers['alice']))
        outcome,display,data,_=answer('restart','after-withdraw','Which general pace remains?',travels[0])
        assert {i['slot']:i['text'] for i in data['items']}=={'diet.spicy':records[0][3],'pace':records[1][3]}
        diet_source=next(i['source_id'] for i in data['items'] if i['slot']=='diet.spicy')
        with psycopg.connect(**json.loads(conninfo.read_bytes())) as conn:
            conn.execute("UPDATE cj_memory_source SET expires_at=clock_timestamp()-interval '1 second' WHERE scope=%s AND source_id=%s",
                         (scope,diet_source))
        outcome,display,data,_=answer('restart','after-expiry','Only current usable data?',travels[0])
        assert {i['slot']:i['text'] for i in data['items']}=={'pace':records[1][3]}
        with host.database.connect(scope) as conn:assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(7,)
        print('PASS reconstructed actual worker; item pause invalidates inflight completion, withdrawal removes current override, expiry filters next actual request while all seven records remain retained')


def main():
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='g2c-current-result-') as temp:
        with pg_suites.cluster('current_result',port=55512,role='cj_current_result',socket=f'/tmp/cj-current-result-{os.getpid()}') as config:
            with psycopg.connect(**config,autocommit=True) as conn:migrate.up(conn,migrate.load(),migrate.load()[-1]['version'])
            root=Path(temp);conninfo=root/'conninfo.json';conninfo.write_text(json.dumps(config))
            exercise(conninfo,root/'auth')


def resume(args):
    from dataclasses import asdict
    from cj_api.local_app import LocalDatabase
    from cj_memory.typed_runtime import load_typed_runtime_configuration
    with patch.dict(os.environ,{'CJ_ENV':'local'}):
        import run_worker
        conninfo,auth,run_path,runtime_path=map(Path,args)
        model=Observed()
        results=run_worker.run_once(LocalDatabase(conninfo,run_context=load_run_context(run_path),travel_context=True),
            model,auth,memory_configuration=load_typed_runtime_configuration(runtime_path))
        print(json.dumps(dict(outcomes=[asdict(o) for o in results],inputs=model.inputs),ensure_ascii=False))


if __name__=='__main__':
    if sys.argv[1:2]==['--resume']:resume(sys.argv[2:])
    else:main()
