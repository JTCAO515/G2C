"""Fresh private PG, actual signed MESSAGE/RUN/Meter; supplier adapters are fixtures."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict,replace
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import base64,json,os,sys,time,uuid
from unittest.mock import patch
import psycopg
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from cj_api.local_app import LocalDatabase,ISSUER,scope_for
from cj_api.local_run_context import load_run_context,LocalRunContext,RunProfile
from cj_api.local_worker_context import checker_for,LocalBudgetRouter
from cj_agent.provider import FakeProvider,ProviderUnknown
from cj_message.auth_boundary import Boundary
from cj_run.core import Binding
from cj_run.step_usage import ledger_scope_for
from cj_run.operation_usage import OperationStore
from cj_usage.codec import decode_v2
from deploy.hk import checkpoint,native4_usage
from cj_usage.core import LedgerV2,NATIVE4_PROFILE,Meter
from cj_usage.registered_exit import Native4RegisteredExit,Registration,InvocationInput
from cj_usage.metered_exit import BudgetExceeded,BudgetUnknown
import dev_auth,local_run_context,migrate,pg_suites,run_worker


def exercise(root,config):
    auth=root/'auth';dev_auth.init(auth,['native-a','native-b'])
    path=root/'conn.json';path.write_text(json.dumps(config));now=int(time.time())
    context_path=root/'context.json';context_path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(
        unit='provider_call',budget=800,period_start=now-60,period_end=now+3600,max_steps=24,max_tools=12,max_output=65536,max_seconds=600),
        output_limits=dict(model=12000,tool=48000,memory=1000)),history=[])))
    context=load_run_context(context_path);database=LocalDatabase(path,run_context=context,travel_context=True,needs_context=True)
    control=root/'control'
    @contextmanager
    def operator():
        with psycopg.connect(**config,autocommit=True)as db:yield db,config
    with patch.object(checkpoint,'operator',operator):checkpoint.bootstrap(control,lambda _:None)
    following=LocalRunContext(RunProfile(replace(context.current.meter,period_start=now+3600,period_end=now+7200),context.current.output_limits),(),context.version)
    for subject in('native-a','native-b'):
        with psycopg.connect(**config)as db:
            local_run_context.provision_budget_connection(db,context,subject)
            if subject=='native-a':local_run_context.provision_budget_connection(db,following,subject)
            db.execute("INSERT INTO cj_message_context_profile VALUES(%s,'message-travel.1')",(scope_for(ISSUER,subject),))
    scope=scope_for(ISSUER,'native-a');account=ledger_scope_for(scope,context.current.meter)
    boundary=Boundary(checker_for(auth),lambda principal:database.message_repository(scope_for(principal.issuer,principal.subject)),lambda:str(uuid.uuid4()))
    def send(mid,version,subject='native-a'):
        selected_scope=scope_for(ISSUER,subject)
        token=dev_auth.token(auth,subject,3600)
        value=dict(version=version,message_id=mid,text='Synthetic planning input',locale='en',new_conversation=True)
        receipt=boundary.receive_lio(token,json.dumps(value).encode(),prepare_scope=database._provision_scope,version=version)
        with database.message_repository(selected_scope).transaction()as tx:stored=tx.find(mid)
        r=stored.receipt
        return Binding(selected_scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
    runtime=SimpleNamespace(planning_subjects=frozenset(('native-a','native-b')),context=context,
        demo_subjects=frozenset(('native-a',)),demo_next_context=following)
    with checkpoint.lock(control),psycopg.connect(**config)as db:
        preview=native4_usage.qualify(db,runtime,'native-a',control)
        assert preview['status']=='NATIVE4_USAGE_PREFLIGHT_ONLY'
        assert db.execute('SELECT format_version FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()==(1,)
        assert db.execute('SELECT count(*) FROM cj_native4_usage_profile').fetchone()==(0,)
    with checkpoint.lock(control),psycopg.connect(**config)as db:
        prepared=native4_usage.qualify(db,runtime,'native-a',control,apply=True)
        assert prepared['status']=='NATIVE4_USAGE_QUALIFIED_TRANSACTION_PENDING'
        assert len(prepared['accounts'])==2 and all(item['new_budget_units']==0 for item in prepared['accounts'])
    with checkpoint.lock(control),psycopg.connect(**config)as db:
        unchanged=db.execute('SELECT revision,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()
        same=native4_usage.qualify(db,runtime,'native-a',control,apply=True)
        assert same['accounts'][0]['existing']is True
        assert unchanged==db.execute('SELECT revision,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()
    old=send('legacy-before','LIO-message.3');native=send('native-current','LIO-message.4')
    router=LocalBudgetRouter(database)
    with checkpoint.lock(control),psycopg.connect(**config)as db:
        try:native4_usage.qualify(db,runtime,'native-b',control,apply=True)
        except ValueError as error:assert str(error)=='original_delivery_or_run_in_flight'
        else:raise AssertionError('in-flight qualifier did not stop')
    database.require_budget_account(scope)
    assert router._native4_policy(old,context.current)is None
    assert router._native4_policy(native,context.current)==NATIVE4_PROFILE
    try:router._native4_policy(replace(native,message_sequence=native.message_sequence+1),context.current)
    except BudgetUnknown as error:assert str(error)=='original native4 MESSAGE unavailable'
    else:raise AssertionError('native4 policy accepted a different original MESSAGE sequence')
    other=scope_for(ISSUER,'native-b')
    unqualified_worker=run_worker._worker_for_scope(database,FakeProvider(),auth,other,checker_for(auth))
    unqualified=send('unqualified-four','LIO-message.4','native-b')
    unqualified_state=unqualified_worker.runs.accept(unqualified)
    def rejects_unqualified():
        try:LocalBudgetRouter(database).for_run(unqualified,unqualified_state)
        except BudgetUnknown as error:assert str(error)=='original native4 account qualification unavailable'
        else:raise AssertionError('genuine native4 selected legacy limits without original qualification')
        with database.connect(other)as db:
            assert db.execute('SELECT count(*) FROM cj_run_metered_operation WHERE scope=%s',(other,)).fetchone()==(0,)
    rejects_unqualified()  # An original v1 account cannot silently select old caps.
    with psycopg.connect(**config)as db:
        from cj_usage.codec import decode_stored,encode_v2
        other_account=ledger_scope_for(other,context.current.meter)
        version,raw=db.execute('SELECT format_version,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(other_account,)).fetchone()
        old_other=asdict(decode_stored(version,raw));assert old_other['attempts']=={}
        upgraded=decode_v2(dict(old_other,run_profiles={},attempt_providers={}))
        db.execute('UPDATE cj_usage_ledger_candidate SET format_version=2,ledger=%s::jsonb WHERE scope_id=%s',(encode_v2(upgraded),other_account))
    rejects_unqualified()  # Format2 alone is not an operator qualification.
    old_unqualified=send('unqualified-old-three','LIO-message.3','native-b')
    old_unqualified_state=unqualified_worker.runs.accept(old_unqualified)
    assert type(LocalBudgetRouter(database).for_run(old_unqualified,old_unqualified_state))is not Native4RegisteredExit
    with database.connect(other)as db:
        assert db.execute('SELECT * FROM cj_native4_usage_profile').fetchall()==[]
        for sql in('INSERT INTO cj_native4_usage_profile VALUES(%s,%s,%s)',):
            try:
                with db.transaction():db.execute(sql,(other,account,NATIVE4_PROFILE))
            except psycopg.errors.InsufficientPrivilege:pass
            else:raise AssertionError('runtime gained native4 qualification writer')
    calls=[];prepared_arguments=[]
    def prepare(argument):
        prepared_arguments.append(argument)
        raw=str(argument).encode()
        def materialize():
            def invoke():
                calls.append(argument)
                if argument=='native-unknown':raise ProviderUnknown('injected original fixture UNKNOWN')
                yield 'fixture'
            return invoke
        return InvocationInput(raw,materialize)
    registrations={key:Registration(kind,prepare)for key,kind in(
        ('model.lio_exploration.1','model'),('memory.lio_extract.1','memory'),
        ('tool.lio_city.1','tool'),('tool.lio_poi2.1','tool'),('tool.lio_route.1','tool'),('tool.visitor_fact','tool'),('tool.unknown','tool'))}
    worker=run_worker._worker_for_scope(database,FakeProvider(),auth,scope,checker_for(auth))
    state=worker.runs.accept(native)
    selected=LocalBudgetRouter(database,registrations=registrations).for_run(native,state)
    assert isinstance(selected,Native4RegisteredExit)
    assert selected.output_limits['tool']==8192
    worker.budget_exit=selected;worker._event(native,state,'started')
    for i in range(45):assert ''.join(worker._registered_stream(native,'amap-'+str(i),'tool.lio_poi2.1',i))=='fixture'
    for i in range(6):
        key='memory.lio_extract.1'if i==5 else'model.lio_exploration.1'
        assert ''.join(worker._registered_stream(native,'model-'+str(i),key,'model-'+str(i)))=='fixture'
    for key,registration in(('amap46','tool.lio_route.1'),('model7','model.lio_exploration.1')):
        try:''.join(worker._registered_stream(native,key,registration,key))
        except BudgetExceeded:pass
        else:raise AssertionError('native4 per-attempt cap exceeded')
    before_calls=list(calls)
    try:''.join(worker._registered_stream(native,'unknown','tool.unknown','unknown'))
    except BudgetUnknown:pass
    else:raise AssertionError('unclassified native4 paid tool accepted')
    assert calls==before_calls and len(calls)==51 and 'unknown'not in prepared_arguments
    def capacity_guard():
        if worker.runs.valid(native)is not True:raise BudgetUnknown('original signed RUN unavailable')
    cap=json.loads(selected.read_run_capacity(native,guard=capacity_guard))
    assert cap['remaining_calls']==749 and cap['remaining_models']==0 and cap['remaining_amap_attempts']==0
    assert cap['admission']=='NOT_GRANTED'
    old_state=worker.runs.accept(old)
    old_exit=LocalBudgetRouter(database,registrations=registrations).for_run(old,old_state)
    assert type(old_exit)is not Native4RegisteredExit and old_exit.output_limits['tool']==48000
    worker.budget_exit=old_exit;worker._event(old,old_state,'started')
    for i in range(12):assert ''.join(worker._registered_stream(old,'old-'+str(i),'tool.lio_poi2.1','old-'+str(i)))=='fixture'
    try:''.join(worker._registered_stream(old,'old13','tool.lio_poi2.1','old13'))
    except BudgetExceeded:pass
    else:raise AssertionError('old3 tool limit changed after account upgrade')
    worker.budget_exit=selected
    try:''.join(worker._registered_stream(native,'native-unknown','tool.visitor_fact','native-unknown'))
    except ProviderUnknown:pass
    else:raise AssertionError('fixture UNKNOWN was hidden')
    worker._event(native,worker.runs.snapshot(native),'unknown')
    original=OperationStore(worker.runs,context.current.meter).read_original(native,'native-unknown')
    rebuilt=LocalBudgetRouter(database,registrations=registrations).for_run(native,worker.runs.snapshot(native))
    rebuilt.stop(native)
    original_meter=rebuilt._original_meter(native,account)
    minimal=json.loads(original_meter.repo.read_status(original.command.attempt_id,guard=capacity_guard,
        max_response_bytes=4096,expected_period=(context.current.meter.period_start,context.current.meter.period_end)))
    assert minimal['status']=='unknown' and minimal['cancelled']is True
    assert calls.count('native-unknown')==1
    rolled_context=LocalRunContext(following.current,(context.current,),context.version)
    rolled_database=LocalDatabase(path,run_context=rolled_context,travel_context=True,needs_context=True)
    historical=LocalBudgetRouter(rolled_database,registrations=registrations).for_run(native,worker.runs.snapshot(native))
    retained=json.loads(historical._original_meter(native,account).repo.read_status(original.command.attempt_id,guard=capacity_guard,
        max_response_bytes=4096,expected_period=(context.current.meter.period_start,context.current.meter.period_end)))
    assert retained==minimal
    with database.connect(scope)as db:
        row=db.execute('SELECT format_version,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()
        ledger=decode_v2(row[1]);assert row[0]==2 and ledger.config==context.current.meter
        assert len(ledger.attempts)==64 and Meter.exposure(ledger)==64
        assert db.execute('SELECT count(*) FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s',(scope,native.run_id)).fetchone()==(54,)
    with psycopg.connect(**config,autocommit=True)as db:
        try:migrate.down(db,migrate.load(),54)
        except psycopg.errors.RaiseException:pass
        else:raise AssertionError('populated version2 downgrade was allowed')
    print('PASS signed genuine4 qualification; unqualified v1/v2 four refused before operation, legacy3 retained, forged original sequence denied; same800 account/51 native complete sends+1 original UNKNOWN/6model inclMemory/45amap/legacy12+13 refusal/unknown-tool before prepare and46+7 refusal/rebuild no replay; runtime cross-owner/qualification-write denial; populated55 down refused',flush=True)


def main():
    with TemporaryDirectory(prefix='b931-native4-')as temp,patch.dict(os.environ,pg_suites.clean_env(),clear=True):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption
        os.environ.update(CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_BETA_DB_TARGET='hk-local',CJ_TRIAL_VALID_UNTIL='2026-12-31T16:00:00+00:00')
        recovery=Ed25519PrivateKey.generate()
        os.environ['CJ_BETA_RECOVERY_PRIVATE_B64']=base64.b64encode(recovery.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode()
        os.environ['CJ_BETA_RECOVERY_PUBLIC_B64']=base64.b64encode(recovery.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
        root=Path(temp)
        with pg_suites.cluster('native4',port=55731,role='native4_initializer',root=root/'pg',socket=root/'s')as config:
            with psycopg.connect(**config,autocommit=True)as db:migrate.up(db,migrate.load(),55)
            exercise(root,config)


if __name__=='__main__':main()
