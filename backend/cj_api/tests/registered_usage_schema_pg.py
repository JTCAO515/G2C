"""0017 schema/RLS/compatibility fixtures on private PG; no business executor."""
import hashlib
import json
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor
import time
from cj_message.local_protection import require_original as m1_require_original
from cj_message.domain import Unavailable
import psycopg
from cj_run.step_usage import ledger_scope_for
from cj_usage.core import Config, Ledger, Command
from cj_usage.codec import encode
import local_history_pg as harness

NEW_TABLES=('cj_local_metered_profile','cj_message_metered_requirement',
            'cj_run_metered_binding','cj_run_metered_operation')


def exercise(auth,conninfo):
    config=json.loads(conninfo.read_text());manifest=harness.migrate.load()
    def connect(runtime=False):
        return psycopg.connect(**dict(config,**({'user':'cj_m1_runtime'} if runtime else {})),autocommit=True)
    def authority(c,scope,account=None):
        c.execute("SELECT set_config('cj.message_scope',%s,true)",(scope,))
        if account is not None: c.execute("SELECT set_config('cj.usage_scope',%s,true)",(account,))
    def failure(c,error,invoke):
        try:
            with c.transaction(): invoke()
        except error: return
        raise AssertionError('expected '+error.__name__)
    def receipt(c,scope,mid,rid,marker):
        sequence=c.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM cj_message_receipt WHERE scope=%s',(scope,)).fetchone()[0]
        c.execute('INSERT INTO cj_message_receipt VALUES(%s,%s,\'chat\',\'g\',%s,%s,%s,%s)',
                  (scope,mid,sequence,rid,'0'*64,b'schema original'))
        if marker:
            table='cj_message_metered_requirement' if marker=='new' else 'cj_local_run_requirement'
            version='registered-exit.1' if marker=='new' else 'local-budget-needs.1'
            c.execute('INSERT INTO '+table+' VALUES(%s,%s,%s,%s)',(scope,mid,rid,version))
        c.execute('INSERT INTO cj_message_delivery(scope,message_id,run_id) VALUES(%s,%s,%s)',(scope,mid,rid))
    def run(c,scope,mid,rid):
        sequence=c.execute('SELECT sequence FROM cj_message_receipt WHERE scope=%s AND message_id=%s',(scope,mid)).fetchone()[0]
        c.execute("INSERT INTO cj_run_record(scope,run_id,conversation_id,generation,message_id,message_sequence,status,event_sequence,expires_at) VALUES(%s,%s,'chat','g',%s,%s,'queued',0,now()+interval '1 day')",(scope,rid,mid,sequence))
    def bind(c,scope,rid,account,start=100,end=1000):
        c.execute("INSERT INTO cj_run_metered_binding VALUES(%s,%s,%s,'provider_call',%s,%s,'RUN-USAGE-OPERATIONS@1')",(scope,rid,account,start,end))
    def operation(c,scope,rid,account,key,kind,attempt=None):
        raw=('private fixture '+kind).encode()
        command=Command(attempt or 'attempt-'+key,'operation-'+key,rid,kind,hashlib.sha256(raw).hexdigest(),1,100)
        command_bytes=json.dumps(asdict(command),sort_keys=True,separators=(',',':')).encode()
        c.execute('INSERT INTO cj_run_metered_operation VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                  (scope,rid,key,account,'schema.'+kind,kind,command.attempt_id,command.operation_id,command_bytes,raw))
        return command_bytes,raw
    def old_snapshot(c,names):
        return (c.execute('SELECT relname,relacl,relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname=ANY(%s) ORDER BY relname',(names,)).fetchall(),
                c.execute('SELECT tablename,policyname,roles,cmd,qual,with_check FROM pg_policies WHERE tablename=ANY(%s) ORDER BY tablename,policyname',(names,)).fetchall(),
                c.execute("SELECT c.relname,a.attname,a.attacl FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid WHERE c.relname=ANY(%s) AND a.attnum>0 ORDER BY c.relname,a.attname",(names,)).fetchall(),
                c.execute("SELECT c.relname,k.conname,pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid WHERE c.relname=ANY(%s) AND k.contype<>'t' ORDER BY c.relname,k.conname",(names,)).fetchall(),
                c.execute("SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname='cj_m1_runtime'").fetchone())
    with connect() as admin:
        harness.migrate.down(admin,manifest,16)
        names=[r[0] for r in admin.execute("SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r'").fetchall()]
        before=old_snapshot(admin,names)
        harness.migrate.up(admin,manifest,17)
        assert old_snapshot(admin,names)==before
        accounts={}
        for scope in ('a','b','pending','active-run','legacy','send-first','activation-first'):
            admin.execute('INSERT INTO cj_message_scope(scope) VALUES(%s)',(scope,))
            admin.execute("INSERT INTO cj_local_run_protection VALUES(%s,'local-budget-needs.1')",(scope,))
            admin.execute("INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch) VALUES(%s,'chat','g',0)",(scope,))
            admin.execute("INSERT INTO cj_run_scope VALUES(%s,'1',true)",(scope,))
            cfg=Config('provider_call',6,100,1000,6,3,10000,600)
            accounts[scope]=ledger_scope_for(scope,cfg)
            admin.execute('INSERT INTO cj_usage_ledger_candidate VALUES(%s,0,1,%s::jsonb)',(accounts[scope],encode(Ledger(cfg))))
        with admin.transaction(): receipt(admin,'pending','old','old','old')
        failure(admin,psycopg.errors.CheckViolation,lambda:admin.execute("INSERT INTO cj_local_metered_profile VALUES('pending','registered-exit.1')"))
        with admin.transaction():
            receipt(admin,'active-run','old','old','old')
            admin.execute("UPDATE cj_message_delivery SET acknowledged=true WHERE scope='active-run'")
            run(admin,'active-run','old','old')
        failure(admin,psycopg.errors.CheckViolation,lambda:admin.execute("INSERT INTO cj_local_metered_profile VALUES('active-run','registered-exit.1')"))
        with admin.transaction():
            receipt(admin,'legacy','history','history','old')
            admin.execute("UPDATE cj_message_delivery SET acknowledged=true WHERE scope='legacy'")
        admin.execute("INSERT INTO cj_local_metered_profile VALUES('legacy','registered-exit.1')")
        with connect(True) as old_reader:
            with old_reader.transaction():
                authority(old_reader,'legacy',accounts['legacy'])
                with old_reader.cursor() as cursor: m1_require_original(cursor,'legacy',True,'history','history')
                assert old_reader.execute("SELECT raw_input FROM cj_message_receipt WHERE message_id='history'").fetchone()[0]==b'schema original'
        for scope in ('a','b'): admin.execute("INSERT INTO cj_local_metered_profile VALUES(%s,'registered-exit.1')",(scope,))
        with connect(True) as runtime:
            for table in NEW_TABLES: assert runtime.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
            failure(runtime,psycopg.errors.InsufficientPrivilege,lambda:receipt(runtime,'a','no-scope','no-scope','new'))
            with runtime.transaction():
                authority(runtime,'a',accounts['a'])
                receipt(runtime,'a','m','r','new');run(runtime,'a','m','r');bind(runtime,'a','r',accounts['a'])
                expected={kind:operation(runtime,'a','r',accounts['a'],kind,kind) for kind in ('model','tool','memory')}
                # FK/RLS and capability negatives retain the outer real transaction.
                failure(runtime,psycopg.errors.InsufficientPrivilege,lambda:receipt(runtime,'b','foreign','foreign','new'))
                for table in NEW_TABLES:
                    for verb in ('DELETE FROM ','TRUNCATE '):
                        failure(runtime,psycopg.errors.InsufficientPrivilege,lambda table=table,verb=verb:runtime.execute(verb+table))
                failure(runtime,psycopg.errors.InsufficientPrivilege,lambda:runtime.execute("INSERT INTO cj_local_metered_profile VALUES('legacy','registered-exit.1')"))
                failure(runtime,psycopg.errors.InsufficientPrivilege,lambda:runtime.execute("UPDATE cj_run_metered_operation SET kind='memory'"))
                failure(runtime,psycopg.errors.InsufficientPrivilege,lambda:runtime.execute("UPDATE cj_run_metered_binding SET period_end=2000"))
                failure(runtime,psycopg.errors.InsufficientPrivilege,lambda:runtime.execute("DELETE FROM cj_run_record WHERE scope='b'"))
                failure(runtime,psycopg.errors.UniqueViolation,lambda:operation(runtime,'a','r',accounts['a'],'model','model'))
                failure(runtime,psycopg.errors.UniqueViolation,lambda:operation(runtime,'a','r',accounts['a'],'replacement','model','attempt-model'))
            for table in NEW_TABLES: assert runtime.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
            for marker,mid in ((None,'missing'),('old','old-writer')):
                def old_write(marker=marker,mid=mid):
                    authority(runtime,'a',accounts['a']);receipt(runtime,'a',mid,mid,marker)
                failure(runtime,psycopg.errors.CheckViolation,old_write)
                assert admin.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=\'a\' AND message_id=%s',(mid,)).fetchone()[0]==0
            with runtime.transaction():
                authority(runtime,'a',accounts['a'])
                # The previous M1 guard's original lookup has no execution marker.
                assert runtime.execute("SELECT run_id,version FROM cj_local_run_requirement WHERE scope='a' AND message_id='m'").fetchone() is None
                try:
                    with runtime.cursor() as cursor: m1_require_original(cursor,'a',True,'m','r')
                except Unavailable: pass
                else: raise AssertionError('M1 guard accepted registered requirement')
                rows=runtime.execute('SELECT kind,command_bytes,input_bytes FROM cj_run_metered_operation ORDER BY kind').fetchall()
                assert {kind:(bytes(command),bytes(raw)) for kind,command,raw in rows}==expected
            with runtime.transaction():
                authority(runtime,'a',accounts['b'])
                assert runtime.execute('SELECT count(*) FROM cj_run_metered_operation').fetchone()[0]==0
                # Even deliberately mixed authority cannot bind another account.
                receipt(runtime,'a','mixed','mixed','new');run(runtime,'a','mixed','mixed')
                failure(runtime,psycopg.errors.CheckViolation,lambda:bind(runtime,'a','mixed',accounts['b']))
            with runtime.transaction():
                authority(runtime,'a')
                assert runtime.execute('SELECT count(*) FROM cj_run_metered_binding').fetchone()[0]==0
                failure(runtime,psycopg.errors.InsufficientPrivilege,lambda:operation(runtime,'a','r',accounts['a'],'no-usage','model'))
        # New period may hide originals, never replace a RUN's fixed partition.
        cfg2=Config('provider_call',6,1000,2000,6,3,10000,600);account2=ledger_scope_for('a',cfg2)
        admin.execute('INSERT INTO cj_usage_ledger_candidate VALUES(%s,0,1,%s::jsonb)',(account2,encode(Ledger(cfg2))))
        with connect(True) as runtime:
            def replace_period():
                authority(runtime,'a',account2);bind(runtime,'a','r',account2,1000,2000)
            failure(runtime,psycopg.errors.UniqueViolation,replace_period)
            def wrong_operation():
                authority(runtime,'a',account2);operation(runtime,'a','r',account2,'new-period','model')
            failure(runtime,psycopg.errors.ForeignKeyViolation,wrong_operation)
        # Both real lock orders. No sleeps stand in for evidence of contention.
        def wait_blocked(pid):
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                if admin.execute("SELECT 1 FROM pg_stat_activity WHERE pid=%s AND wait_event_type='Lock'",(pid,)).fetchone(): return
                time.sleep(.01)
            raise AssertionError('expected actual PostgreSQL lock wait')
        with connect(True) as writer,connect() as initializer,ThreadPoolExecutor(max_workers=1) as pool:
            with writer.transaction():
                authority(writer,'send-first',accounts['send-first'])
                writer.execute("SELECT scope FROM cj_message_scope WHERE scope='send-first' FOR UPDATE")
                receipt(writer,'send-first','first','first','old')
                attempt=pool.submit(initializer.execute,"INSERT INTO cj_local_metered_profile VALUES('send-first','registered-exit.1')")
                wait_blocked(initializer.info.backend_pid)
            try: attempt.result()
            except psycopg.errors.CheckViolation: pass
            else: raise AssertionError('activation ignored committed pending send')
        with connect(True) as writer,connect() as initializer,ThreadPoolExecutor(max_workers=1) as pool:
            def old_send():
                with writer.transaction():
                    authority(writer,'activation-first',accounts['activation-first'])
                    writer.execute("SELECT scope FROM cj_message_scope WHERE scope='activation-first' FOR UPDATE")
                    receipt(writer,'activation-first','late','late','old')
            with initializer.transaction():
                initializer.execute("INSERT INTO cj_local_metered_profile VALUES('activation-first','registered-exit.1')")
                attempt=pool.submit(old_send)
                wait_blocked(writer.info.backend_pid)
            try: attempt.result()
            except psycopg.errors.CheckViolation: pass
            else: raise AssertionError('old send bypassed committed activation')
        assert admin.execute("SELECT count(*) FROM cj_message_receipt WHERE scope='activation-first'").fetchone()[0]==0
        print('PASS both activation/send lock orders and actual M1 original guard refusal')
        # Idempotent profile insert is safe with new-mode pending work, not an upgrade.
        admin.execute("INSERT INTO cj_local_metered_profile VALUES('a','registered-exit.1') ON CONFLICT DO NOTHING")
        failure(admin,psycopg.errors.ForeignKeyViolation,lambda:admin.execute("DELETE FROM cj_local_metered_profile WHERE scope='a'"))
        failure(admin,psycopg.errors.ForeignKeyViolation,lambda:admin.execute("DELETE FROM cj_local_run_protection WHERE scope='a'"))
        failure(admin,psycopg.errors.RaiseException,lambda:harness.migrate.down(admin,manifest,16))
        assert 17 in harness.migrate.applied(admin)
        # Owned physical parent deletion clears its new private bytes, not another scope.
        with admin.transaction():
            receipt(admin,'b','m','r','new');run(admin,'b','m','r');bind(admin,'b','r',accounts['b']);operation(admin,'b','r',accounts['b'],'model','model')
        admin.execute("DELETE FROM cj_run_record WHERE scope='a'")
        assert admin.execute("SELECT count(*) FROM cj_run_metered_operation WHERE scope='a'").fetchone()[0]==0
        assert admin.execute("SELECT count(*) FROM cj_run_metered_operation WHERE scope='b'").fetchone()[0]==1
        assert admin.execute("SELECT count(*) FROM cj_local_metered_profile WHERE scope='a'").fetchone()[0]==1
        assert old_snapshot(admin,names)==before
    print('PASS schema: three kinds, original bytes/uniqueness, dual scopes/fixed period, deferred old-writer refusal, pending activation, cleanup restrictions and populated down refusal')
    print('UNRUN: generic execution core, business tool/background producers and consumer activation')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
