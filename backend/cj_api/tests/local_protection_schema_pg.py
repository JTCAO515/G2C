"""0016 schema/upgrade proof on fresh PG; not formal host activation evidence."""
import json
import psycopg
from cj_run.step_usage import ledger_scope_for
from cj_usage.core import Config, Ledger
from cj_usage.codec import encode, decode, CorruptLedger
import local_history_pg as harness


def seed(connection,scope,*,ledger=True):
    connection.execute('INSERT INTO cj_message_scope(scope) VALUES(%s)',(scope,))
    connection.execute("INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch,active) VALUES(%s,'chat','g',0,true)",(scope,))
    for index in (1,2):
        connection.execute('INSERT INTO cj_message_receipt VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                           (scope,f'm{index}','chat','g',index,f'r{index}','0'*64,b'original plain input'))
        connection.execute('INSERT INTO cj_message_delivery(scope,message_id,run_id) VALUES(%s,%s,%s)',(scope,f'm{index}',f'r{index}'))
    if ledger:
        cfg=Config('provider_call',2,100,1000,4,1,10000,600)
        connection.execute('INSERT INTO cj_usage_ledger_candidate VALUES(%s,0,1,%s::jsonb)',(ledger_scope_for(scope,cfg),encode(Ledger(cfg))))


def exercise(auth,conninfo):
    config=json.loads(conninfo.read_text());manifest=harness.migrate.load()
    def old_state(conn):
        return (conn.execute("SELECT tablename,policyname,roles,cmd,qual,with_check FROM pg_policies WHERE tablename NOT LIKE 'cj_local_run_%' ORDER BY tablename,policyname").fetchall(),
                conn.execute("SELECT relname,relacl,relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname LIKE 'cj_%' AND relname NOT LIKE 'cj_local_run_%' ORDER BY relname").fetchall(),
                conn.execute("SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname='cj_m1_runtime'").fetchone())
    with psycopg.connect(**config,autocommit=True) as admin:
        harness.migrate.down(admin,manifest,15)
        admin.execute('CREATE DATABASE protection_base TEMPLATE postgres')
        old=old_state(admin)
        scopes=['plain','quote"slash\\tab\tline\ncontrol\b\f\r','中文-é-😀-\u2028','foreign']
        for scope in scopes: seed(admin,scope)
        seed(admin,'legacy',ledger=False)
        for extra in ('selection-only','binding-only','step-only','corrupt-attempts'):
            seed(admin,extra,ledger=extra in ('step-only','corrupt-attempts'))
        for extra in ('selection-only','binding-only'):
            admin.execute('INSERT INTO cj_needs_scope VALUES(%s)',(extra,))
            admin.execute("INSERT INTO cj_needs_record VALUES(%s,'needs',1,%s)",(extra,b'{}'))
            admin.execute("INSERT INTO cj_needs_revision(scope,needs_id,version,action_id,operation,original_input,content,source_kind) VALUES(%s,'needs',1,'act','manual_patch',%s,%s,'user_provided')",(extra,b'{}',b'{}'))
        admin.execute("INSERT INTO cj_message_needs_selection VALUES('selection-only','chat','g','selection-only','needs')")
        admin.execute("INSERT INTO cj_message_needs_binding VALUES('binding-only','m1','r1','binding-only','needs',1,%s)",('0'*64,))
        admin.execute("INSERT INTO cj_run_scope VALUES('step-only','1',true)")
        admin.execute("INSERT INTO cj_run_record(scope,run_id,conversation_id,generation,message_id,message_sequence,status,event_sequence,expires_at) VALUES('step-only','r1','chat','g','m1',1,'queued',0,now()+interval '1 day')")
        account=ledger_scope_for('step-only',Config('provider_call',2,100,1000,4,1,10000,600))
        admin.execute("INSERT INTO cj_run_step_usage VALUES('step-only','r1','answer','attempt',%s,'provider_call',100,1000,%s,%s)",(account,b'{}',b'original'))
        broken=ledger_scope_for('corrupt-attempts',Config('provider_call',2,100,1000,4,1,10000,600))
        admin.execute("UPDATE cj_usage_ledger_candidate SET ledger=jsonb_set(ledger,'{attempts}','[]') WHERE scope_id=%s",(broken,))
        scopes+=['selection-only','binding-only','step-only','corrupt-attempts']
        before=admin.execute('SELECT scope_id,revision,ledger FROM cj_usage_ledger_candidate ORDER BY scope_id').fetchall()
        raw=admin.execute('SELECT scope,message_id,raw_input FROM cj_message_receipt ORDER BY scope,message_id').fetchall()
        harness.migrate.up(admin,manifest,16)
        assert old_state(admin)==old
        assert admin.execute('SELECT scope FROM cj_local_run_protection ORDER BY scope').fetchall()==sorted((s,) for s in scopes)
        assert admin.execute('SELECT count(*) FROM cj_local_run_requirement').fetchone()[0]==2*len(scopes)
        assert admin.execute('SELECT scope_id,revision,ledger FROM cj_usage_ledger_candidate ORDER BY scope_id').fetchall()==before
        assert admin.execute('SELECT scope,message_id,raw_input FROM cj_message_receipt ORDER BY scope,message_id').fetchall()==raw
        try: decode(admin.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(broken,)).fetchone()[0])
        except CorruptLedger: pass
        else: raise AssertionError('semantic corruption silently repaired')
        # Real runtime role: only MESSAGE scope is needed to observe the requirement.
        with psycopg.connect(**dict(config,user='cj_m1_runtime'),autocommit=True) as runtime:
            for table in ('cj_local_run_protection','cj_local_run_requirement'):
                assert runtime.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
            with runtime.transaction():
                runtime.execute("SELECT set_config('cj.message_scope','plain',true)")
                assert runtime.execute('SELECT scope FROM cj_local_run_protection').fetchall()==[('plain',)]
                assert runtime.execute('SELECT count(*) FROM cj_local_run_requirement').fetchone()[0]==2
                for sql in ("INSERT INTO cj_local_run_protection VALUES('plain','local-budget-needs.1')",
                            "UPDATE cj_local_run_protection SET version='local-budget-needs.1'",
                            'DELETE FROM cj_local_run_protection','TRUNCATE cj_local_run_protection',
                            "UPDATE cj_local_run_requirement SET version='local-budget-needs.1'",
                            'DELETE FROM cj_local_run_requirement','TRUNCATE cj_local_run_requirement',
                            "INSERT INTO cj_local_run_requirement VALUES('foreign','m1','r1','local-budget-needs.1')"):
                    try:
                        with runtime.transaction(): runtime.execute(sql)
                    except psycopg.errors.InsufficientPrivilege: pass
                    else: raise AssertionError('runtime privilege/foreign write allowed: '+sql)
            assert runtime.execute('SELECT count(*) FROM cj_local_run_protection').fetchone()[0]==0
        admin.execute("INSERT INTO cj_message_receipt VALUES('plain','m3','chat','g',3,'r3',%s,%s)",('0'*64,b'new input'))
        with psycopg.connect(**dict(config,user='cj_m1_runtime'),autocommit=True) as runtime:
            with runtime.transaction():
                runtime.execute("SELECT set_config('cj.message_scope','plain',true)")
                runtime.execute("INSERT INTO cj_local_run_requirement VALUES('plain','m3','r3','local-budget-needs.1')")
                try:
                    with runtime.transaction(): runtime.execute("INSERT INTO cj_local_run_requirement VALUES('plain','m3','r3','local-budget-needs.1')")
                except psycopg.errors.UniqueViolation: pass
                else: raise AssertionError('original requirement duplicated')
        try: harness.migrate.down(admin,manifest,15)
        except psycopg.errors.RaiseException: pass
        else: raise AssertionError('populated protection downgraded')
        assert 16 in harness.migrate.applied(admin)
        print('PASS canonical UTF8/escaping ledger-only pre-step upgrade, original bytes/ledger unchanged, grants/RLS unchanged, runtime negatives and populated down refusal')
        # Each malformed/unresolved mapping has its own database; failed up leaves
        # both schema and original records untouched, including migration ledger.
        for index,bad in enumerate(('unmatched','unit-missing','unit-empty','period-float','period-negative','period-reversed')):
            name='protection_bad_'+str(index)
            admin.execute('CREATE DATABASE '+name+' TEMPLATE protection_base')
            with psycopg.connect(**dict(config,dbname=name),autocommit=True) as conn:
                harness.migrate.up(conn,manifest,15)
                seed(conn,'owner')
                if bad=='unmatched': conn.execute("UPDATE cj_usage_ledger_candidate SET scope_id='unresolved'")
                elif bad=='unit-missing': conn.execute("UPDATE cj_usage_ledger_candidate SET ledger=ledger #- '{config,unit}'")
                elif bad=='unit-empty': conn.execute("UPDATE cj_usage_ledger_candidate SET ledger=jsonb_set(ledger,'{config,unit}','\"\"')")
                else:
                    value={'period-float':'100.5','period-negative':'-1','period-reversed':'2000'}[bad]
                    conn.execute("UPDATE cj_usage_ledger_candidate SET ledger=jsonb_set(ledger,'{config,period_start}',%s::jsonb)",(value,))
                original=conn.execute('SELECT * FROM cj_usage_ledger_candidate').fetchall()
                try: harness.migrate.up(conn,manifest,16)
                except psycopg.Error: pass
                else: raise AssertionError('ambiguous mapping accepted: '+bad)
                assert 16 not in harness.migrate.applied(conn)
                assert conn.execute("SELECT to_regclass('cj_local_run_protection')").fetchone()[0] is None
                assert conn.execute('SELECT * FROM cj_usage_ledger_candidate').fetchall()==original
        print('PASS malformed/unmatched original mapping aborts migration atomically; no fallback or ledger reset')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
