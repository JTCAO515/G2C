"""Migration14 database permission/lock checks; schema fixtures, NOT host acceptance."""
import json
import psycopg
import local_history_pg as harness


def exercise(auth, conninfo):
    config=json.loads(conninfo.read_text())
    def connect(user=None): return psycopg.connect(**dict(config, **({'user':user} if user else {})),autocommit=True)
    def scope(connection, suffix):
        for name,value in [('message','m'+suffix),('trip','t'+suffix),('needs','n'+suffix),('usage','u'+suffix)]:
            connection.execute("SELECT set_config(%s,%s,true)",('cj.'+name+'_scope',value))
    def denied(connection, sql, parameters=()):
        try:
            with connection.transaction(): connection.execute(sql,parameters)
        except psycopg.errors.InsufficientPrivilege: return
        raise AssertionError('expected privilege/RLS refusal: '+sql)
    with connect() as admin:
        for suffix in ('a','b'):
            m,n,u='m'+suffix,'n'+suffix,'u'+suffix
            admin.execute('INSERT INTO cj_message_scope(scope) VALUES(%s)',(m,))
            admin.execute("INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch,active) VALUES(%s,'chat','g',0,true)",(m,))
            admin.execute("INSERT INTO cj_message_receipt VALUES(%s,'msg','chat','g',1,'run',%s,%s)",(m,'0'*64,b'{}'))
            admin.execute('INSERT INTO cj_needs_scope VALUES(%s)',(n,))
            admin.execute("INSERT INTO cj_needs_record VALUES(%s,'needs',1,%s)",(n,b'{}'))
            admin.execute("INSERT INTO cj_needs_revision(scope,needs_id,version,action_id,operation,original_input,content,source_kind) VALUES(%s,'needs',1,'act','manual_patch',%s,%s,'user_provided')",(n,b'{}',b'{}'))
            admin.execute("INSERT INTO cj_message_needs_selection VALUES(%s,'chat','g',%s,'needs')",(m,n))
            admin.execute("INSERT INTO cj_usage_ledger_candidate VALUES(%s,0,1,'{}')",(u,))
            admin.execute("INSERT INTO cj_run_scope VALUES(%s,'1',true)",(m,))
            admin.execute("INSERT INTO cj_run_record(scope,run_id,conversation_id,generation,message_id,message_sequence,status,event_sequence,expires_at) VALUES(%s,'run','chat','g','msg',1,'queued',0,now()+interval '1 day')",(m,))
        with connect('cj_m1_runtime') as runtime:
            with runtime.transaction():
                scope(runtime,'a')
                for table in ('cj_needs_scope','cj_needs_record','cj_needs_revision','cj_message_needs_selection','cj_usage_ledger_candidate'):
                    assert len(runtime.execute('SELECT * FROM '+table).fetchall())==1
                for table in ('cj_needs_scope','cj_needs_record','cj_needs_revision'):
                    denied(runtime,'DELETE FROM '+table)
                    denied(runtime,'TRUNCATE '+table)
                denied(runtime,"UPDATE cj_needs_record SET version=2")
                denied(runtime,"INSERT INTO cj_needs_scope VALUES('na')")
                runtime.execute("UPDATE cj_usage_ledger_candidate SET ledger='{}',revision=revision+1 WHERE scope_id='ua'")
                assert runtime.execute("UPDATE cj_usage_ledger_candidate SET revision=revision+1 WHERE scope_id='ub'").rowcount==0
                denied(runtime,"UPDATE cj_usage_ledger_candidate SET scope_id='ub'")
                denied(runtime,"UPDATE cj_usage_ledger_candidate SET format_version=1")
                denied(runtime,"INSERT INTO cj_usage_ledger_candidate VALUES('uc',0,1,'{}')")
                denied(runtime,'DELETE FROM cj_usage_ledger_candidate')
                runtime.execute("INSERT INTO cj_message_needs_binding VALUES('ma','msg','run','na','needs',1,%s)",('0'*64,))
                denied(runtime,"INSERT INTO cj_message_needs_binding VALUES('mb','msg','run','nb','needs',1,%s)",('0'*64,))
                runtime.execute("INSERT INTO cj_run_step_usage VALUES('ma','run','answer','attempt-a','ua','provider_call',0,100,%s,%s)",(b'{}',b'input'))
                denied(runtime,"INSERT INTO cj_run_step_usage VALUES('mb','run','answer','attempt-b','ub','provider_call',0,100,%s,%s)",(b'{}',b'input'))
                for table in ('cj_message_needs_binding','cj_run_step_usage'):
                    denied(runtime,'DELETE FROM '+table)
                denied(runtime,"UPDATE cj_run_step_usage SET attempt_id='replacement'")
            # Same physical connection has no surviving LOCAL authorization.
            for table in ('cj_needs_record','cj_message_needs_binding','cj_run_step_usage','cj_usage_ledger_candidate'):
                assert runtime.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
            with runtime.transaction():
                scope(runtime,'b')
                assert runtime.execute('SELECT scope FROM cj_needs_record').fetchone()[0]=='nb'
            try:
                with runtime.transaction():
                    scope(runtime,'a'); raise RuntimeError('rollback')
            except RuntimeError: pass
            assert runtime.execute('SELECT count(*) FROM cj_needs_record').fetchone()[0]==0
        # Reader's shared lease forces a writer to fail its bounded lock wait.
        with connect('cj_m1_runtime') as reader, connect() as writer:
            with reader.transaction():
                scope(reader,'a')
                reader.execute("SELECT pg_advisory_xact_lock_shared(cj_needs_fence_key('na'))")
                try:
                    with writer.transaction():
                        writer.execute("SET LOCAL lock_timeout='100ms'")
                        writer.execute("UPDATE cj_needs_record SET version=2 WHERE scope='na'")
                except psycopg.errors.LockNotAvailable: pass
                else: raise AssertionError('writer bypassed reader lease')
                assert reader.execute('SELECT version FROM cj_needs_record').fetchone()[0]==1
            with writer.transaction(): writer.execute("UPDATE cj_needs_record SET version=2 WHERE scope='na'")
            with reader.transaction():
                scope(reader,'a')
                reader.execute("SELECT pg_advisory_xact_lock_shared(cj_needs_fence_key('na'))")
                assert reader.execute('SELECT version FROM cj_needs_record').fetchone()[0]==2
        # Reverse ordering: committed writer wins; a reader cannot observe a stale
        # revision as protected while that writer owns the exclusive lease.
        with connect() as writer, connect('cj_m1_runtime') as reader:
            with writer.transaction():
                writer.execute("UPDATE cj_needs_record SET version=3 WHERE scope='na'")
                try:
                    with reader.transaction():
                        scope(reader,'a')
                        reader.execute("SET LOCAL lock_timeout='100ms'")
                        reader.execute("SELECT pg_advisory_xact_lock_shared(cj_needs_fence_key('na'))")
                except psycopg.errors.LockNotAvailable: pass
                else: raise AssertionError('reader bypassed writer lease')
            with reader.transaction():
                scope(reader,'a')
                reader.execute("SELECT pg_advisory_xact_lock_shared(cj_needs_fence_key('na'))")
                assert reader.execute('SELECT version FROM cj_needs_record').fetchone()[0]==3
            try:
                with writer.transaction():
                    writer.execute("UPDATE cj_needs_record SET version=4 WHERE scope='na'")
                    raise RuntimeError('abort writer')
            except RuntimeError: pass
            with reader.transaction():
                scope(reader,'a')
                reader.execute("SELECT pg_advisory_xact_lock_shared(cj_needs_fence_key('na'))")
                assert reader.execute('SELECT version FROM cj_needs_record').fetchone()[0]==3
        # A lost lease connection must release its transaction advisory lock.
        lost=connect('cj_m1_runtime')
        lost.execute('BEGIN')
        scope(lost,'a')
        lost.execute("SELECT pg_advisory_xact_lock_shared(cj_needs_fence_key('na'))")
        with connect() as writer:
            try:
                with writer.transaction():
                    writer.execute("SET LOCAL lock_timeout='100ms'")
                    writer.execute("UPDATE cj_needs_record SET version=4 WHERE scope='na'")
            except psycopg.errors.LockNotAvailable: pass
            else: raise AssertionError('lost connection test never acquired lease')
            lost.close()
            with writer.transaction():
                writer.execute("SET LOCAL lock_timeout='1s'")
                writer.execute("UPDATE cj_needs_record SET version=4 WHERE scope='na'")
        assert admin.execute("SELECT version FROM cj_needs_record WHERE scope='na'").fetchone()[0]==4
        try: admin.execute('TRUNCATE cj_needs_scope,cj_needs_record,cj_needs_revision,cj_message_needs_selection,cj_message_needs_binding')
        except psycopg.errors.RaiseException: pass
        else: raise AssertionError('TRUNCATE bypassed revision protocol')
        assert admin.execute('SELECT count(*) FROM cj_needs_record').fetchone()[0]==2
        with connect('cj_m1_runtime') as runtime:
            assert runtime.execute("SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=current_user").fetchone()==(False,False,False,False,False)
        try: harness.migrate.down(admin,harness.migrate.load(),13)
        except psycopg.errors.RaiseException: pass
        else: raise AssertionError('down deleted context/attempt data')
        assert 14 in harness.migrate.applied(admin)
        assert admin.execute('SELECT count(*) FROM cj_run_step_usage').fetchone()[0]==1
    print('PASS M14 permissions, cross-scope RLS, LOCAL expiry, reader/writer lock, down refusal; host UNRUN')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
