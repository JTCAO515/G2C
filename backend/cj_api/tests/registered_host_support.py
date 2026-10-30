"""Real signed local API/runtime-role worker fixtures; no business producer mock."""
from contextlib import contextmanager
import json
import os
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
import psycopg

from cj_api.local_app import app_from_environment, LocalDatabase, ISSUER, scope_for
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_run.step_usage import ledger_scope_for
from cj_usage.codec import decode
import local_history_pg as harness


class RegisteredHost:
    def __init__(self, auth, conninfo, limits):
        import local_run_context as operator
        self.auth,self.conninfo,self.subjects=auth,conninfo,list(limits)
        harness.dev_auth.init(auth,self.subjects)
        now=int(time.time())
        self.profiles={}
        for subject,(steps,tools,output) in limits.items():
            value=dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=16,
                period_start=now-60,period_end=now+3600,max_steps=steps,max_tools=tools,
                max_output=60000,max_seconds=600),output_limits=dict(model=4000,tool=output,memory=1000)),history=[])
            path=auth.parent/(subject+'.json')
            path.write_text(json.dumps(value))
            context=load_run_context(path)
            self.profiles[subject]=(path,context)
            operator.provision_budget(conninfo,context,subject)
        self.headers={s:{'Authorization':'Bearer '+harness.dev_auth.token(auth,s,30)} for s in limits}

    @contextmanager
    def api(self,subject):
        with patch.dict(os.environ,dict(CJ_LOCAL_AUTH_DIR=str(self.auth),CJ_LOCAL_CONNINFO=str(self.conninfo),
            CJ_LOCAL_RUN_CONTEXT=str(self.profiles[subject][0]))):
            with TestClient(app_from_environment()) as client: yield client

    def send(self,client,subject,message_id,text):
        chat=harness.expect(client.put('/v1/conversations',params={'conversation_id':message_id},headers=self.headers[subject]))
        raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id=message_id,message_id=message_id,text=text,
            trip_id=None,creation_intent='none',expected_generation=chat['generation'],expected_sequence=0)).encode()
        return harness.expect(client.post('/v1/messages',content=raw,
            headers={**self.headers[subject],'Content-Type':'application/octet-stream'}))['receipt']

    def worker(self,subject,model,tools):
        import run_worker
        database=LocalDatabase(self.conninfo,run_context=self.profiles[subject][1])
        return run_worker._worker_for_scope(database,model,self.auth,scope_for(ISSUER,subject),
            checker_for(self.auth),tools_configuration=tools)

    def display(self,client,subject,message_id):
        return harness.expect(client.get('/v1/run-display',params={'message_id':message_id},headers=self.headers[subject]))['snapshot']

    def status(self,client,subject,message_id):
        return harness.expect(client.get('/v2/run-draft-status',params={'message_id':message_id},headers=self.headers[subject]))

    def ledger(self,subject):
        scope=scope_for(ISSUER,subject)
        account=ledger_scope_for(scope,self.profiles[subject][1].current.meter)
        with psycopg.connect(**json.loads(self.conninfo.read_text())) as observer:
            return decode(observer.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0])
