"""Current same-owner metadata checkpoints under native history AUTH.

Only hashes/IDs/state leave this reader. Candidate Memory jobs are reported
separately from saved items; an extraction is not a saved-preference mutation.
"""
from hashlib import sha256

from cj_agent.draft import trip_scope_for
from cj_usage.authorization_budget import canonical
from runtime_adapter.contract import Unavailable


class SmokeState:
    def __init__(self,controls,boundary,database):
        self.controls,self.boundary,self.database=controls,boundary,database

    def read(self,token):
        self.controls.guard()
        def project(context):
            scope=context.scope
            if scope not in self.controls.scopes:raise Unavailable('APP_SMOKE_STATE_OWNER_CHANGED')
            with self.database.connect(scope)as db:
                db.execute('SET TRANSACTION READ ONLY')
                role=db.execute('SELECT current_user,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,'
                    'EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid),'
                    'EXISTS(SELECT 1 FROM pg_class WHERE relowner=r.oid) FROM pg_roles r WHERE rolname=current_user').fetchone()
                if role!=('cj_m1_runtime',False,False,False,False,False,False,False):
                    raise Unavailable('APP_SMOKE_STATE_RUNTIME_ROLE_CHANGED')
                messages=db.execute('SELECT message_id,run_id,conversation_id,generation,sequence,input_sha256 '
                    'FROM cj_message_receipt WHERE scope=%s ORDER BY message_id',(scope,)).fetchall()
                trips=db.execute("SELECT trip_id,version,encode(sha256(content),'hex') FROM cj_trip_record "
                    'WHERE scope=%s ORDER BY trip_id',(trip_scope_for(scope),)).fetchall()
                memory=db.execute("SELECT item_id,version,status,source_id,source_version,encode(sha256(original_input),'hex') "
                    "FROM cj_memory_item WHERE scope=%s AND status<>'candidate' ORDER BY item_id",(scope,)).fetchall()
                background=db.execute('SELECT job_id,attempt_id,run_id,state,output_sha256,receipt_sha256 '
                    'FROM cj_run_background_job WHERE scope=%s ORDER BY job_id,attempt_id',(scope,)).fetchall()
                history=db.execute('SELECT job_id,attempt_id,state,processed FROM cj_memory_history_job '
                    'WHERE scope=%s ORDER BY job_id,attempt_id',(scope,)).fetchall()
                pending=db.execute('SELECT count(*) FROM cj_message_delivery WHERE scope=%s AND NOT acknowledged',(scope,)).fetchone()[0]
                active=db.execute("SELECT count(*) FROM cj_run_record WHERE scope=%s AND status IN('queued','running')",(scope,)).fetchone()[0]
            self.controls.guard()
            return dict(version='G2C-App-smoke-state.1',scope_sha256=sha256(scope.encode()).hexdigest(),
                runtime_role=role[0],role_flags=list(role[1:]),
                message_ids=[x[0]for x in messages],messages_sha256=sha256(canonical(messages)).hexdigest(),
                native_messages=[dict(message_id=m,run_id=r,conversation_id=c,generation=g,sequence=n,canonical_sha256=h)
                    for m,r,c,g,n,h in messages],
                trip_sha256=sha256(canonical(trips)).hexdigest(),memory_sha256=sha256(canonical(memory)).hexdigest(),
                saved_memory_definition='all non-candidate current items; no extraction-job inference',
                background_rows=[list(row)for row in background],memory_history_rows=[list(row)for row in history],
                pending=pending,active=active)
        return self.boundary.with_history_context(token,project)
