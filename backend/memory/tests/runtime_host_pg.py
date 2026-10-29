"""Actual signed API, runtime-role PG and formal run_once; FakeProvider only."""
import json
import sys
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'backend/agent/tests'), str(ROOT / 'scripts')]
from e2e_local import Harness
import memory_save_read_checks as helpers
from cj_agent.provider import FakeProvider
from cj_api.local_app import LocalDatabase, scope_for, ISSUER
from cj_memory.local_runtime import RuntimeConfiguration
from cj_memory.runtime import RuntimeDenied
from cj_run.core import Binding
import run_worker


class ObservedProvider(FakeProvider):
    def __init__(self, after_first=None):
        super().__init__()
        self.inputs = []
        self.after_first = after_first

    def stream(self, messages, system=None):
        self.inputs.append((messages, system))
        stored=json.loads(messages[0]['content'].split('\n',1)[1])
        for i, chunk in enumerate(super().stream(messages, system)):
            yield (('Memory: '+';'.join(item['text'] for item in stored['items'])+'\n')
                   if i==0 and system is None else '')+chunk
            if i == 0 and self.after_first is not None:
                self.after_first()


class MemoryRuntimeChecks(Harness):
    # Reuse #226's real signed-API helpers, without inheriting/re-running its ACs.
    setUp = helpers.MemorySaveReadChecks.setUp
    write_policy = helpers.MemorySaveReadChecks.write_policy
    app_from_policy = helpers.MemorySaveReadChecks.app_from_policy
    raw = helpers.MemorySaveReadChecks.raw
    save = helpers.MemorySaveReadChecks.save
    receipt = helpers.MemorySaveReadChecks.receipt
    service = helpers.MemorySaveReadChecks.service

    def configuration(self):
        return RuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.1',
            collection=self.policy, selections={identity: dict(subject='self',
                slots=[slot for slot,rule in self.policy['profiles'][identity]['slots'].items()
                       if rule['collection_allowed'] and rule['semantic_resolved']], max_bytes=32768)
                for identity in ('alice','bob')})).encode())

    def execute(self, model):
        # Reconstruct the actual factory each time; no synthetic Context enters RUN.
        return run_worker.run_once(LocalDatabase(run_worker_database_path()), model,
                                   self.auth, memory_configuration=self.configuration())

    def test_runtime_current_next_chat_restart_and_scope(self):
        with TestClient(self.memory_app) as client:
            long = self.raw(text='长期原文 / long-term original')
            self.assertEqual(self.save(client,long).status_code,200)
            temporary = self.raw(text='仅本次 / current only', extent='current', context_id=self.chat_a)
            self.assertEqual(client.put('/v1/conversations',params={'conversation_id':self.chat_a},
                                       headers=self.headers('alice')).status_code,200)
            self.assertEqual(self.save(client,temporary).status_code,200)
            for conversation, expected in ((self.chat_a,'仅本次 / current only'),
                                           (self.chat_b,'长期原文 / long-term original')):
                mid,response = self.send(client,'alice','Current explicit request',conversation=conversation)
                self.assertEqual(response.status_code,200,response.text)
                model = ObservedProvider()
                outcomes = self.execute(model)
                self.assertEqual([o.status for o in outcomes if o.message_id==mid],['completed'])
                data = json.loads(model.inputs[0][0][0]['content'].split('\n',1)[1])
                self.assertEqual([i['text'] for i in data['items'] if i['slot']==self.slots['preference']],[expected])
                self.assertEqual(model.inputs[0][0][-1]['content'],'Current explicit request')
                self.assertIn(expected,''.join(event[2]['text'] for event in self.events(
                    client,'alice',mid) if event[0]=='delta'))
            self.assertEqual(self.service().detail(json.loads(long)['item_id']).command.text,
                             '长期原文 / long-term original')
            mid,response = self.send(client,'bob','Other identity',conversation=self.chat_b)
            self.assertEqual(response.status_code,200,response.text)
            model = ObservedProvider(); self.execute(model)
            self.assertEqual(json.loads(model.inputs[0][0][0]['content'].split('\n',1)[1])['items'],[])

    def test_runtime_source_expiry_blocks_late_answer(self):
        # No privileged mutation simulates an editor. Real wall-clock expiry is
        # observed by the actual worker while its provider stream is in flight.
        from datetime import datetime,timedelta,timezone
        import time
        self.policy['expires_at']=(datetime.now(timezone.utc)+timedelta(seconds=4)).isoformat()
        self.write_policy(); self.memory_app=self.app_from_policy()
        with TestClient(self.memory_app) as client:
            self.assertEqual(self.save(client,self.raw()).status_code,200)
            mid,response=self.send(client,'alice','A short answer',conversation=self.chat_a)
            self.assertEqual(response.status_code,200,response.text)
            model=ObservedProvider(after_first=lambda:time.sleep(4.1))
            outcomes=self.execute(model)
            self.assertEqual([o.status for o in outcomes if o.message_id==mid],['context_invalid'])
            self.assertEqual(model.calls,1)
            scope=scope_for(ISSUER,'alice')
            with self.database.connect(scope) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],0)

    def test_runtime_committed_save_invalidates_inflight_capture(self):
        with TestClient(self.memory_app) as client:
            self.assertEqual(self.save(client,self.raw()).status_code,200)
            mid,response=self.send(client,'alice','An in-flight answer',conversation=self.chat_a)
            self.assertEqual(response.status_code,200,response.text)
            def save_new_epoch():
                self.assertEqual(self.save(client,self.raw('fact')).status_code,200)
            model=ObservedProvider(after_first=save_new_epoch)
            outcomes=self.execute(model)
            self.assertEqual([o.status for o in outcomes if o.message_id==mid],['context_invalid'])
            self.assertEqual(model.calls,1)

    def test_runtime_bounded_projection_fails_before_provider(self):
        with TestClient(self.memory_app) as client:
            self.assertEqual(self.save(client,self.raw()).status_code,200)
            mid,response=self.send(client,'alice','Bounded context',conversation=self.chat_a)
            self.assertEqual(response.status_code,200,response.text)
            configured=self.configuration()
            from cj_memory.runtime import Selection
            configured=RuntimeConfiguration(configured.collection,dict(configured.selections,
                alice=Selection('self',frozenset({self.slots['preference']}),1)))
            model=ObservedProvider()
            outcomes=run_worker.run_once(self.database,model,self.auth,memory_configuration=configured)
            self.assertEqual([o.status for o in outcomes if o.message_id==mid],['context_invalid'])
            self.assertEqual(model.calls,0)

    def test_runtime_z_metered_original_worker(self):
        import time
        from cj_api.local_app import create_local_app
        from cj_api.local_run_context import load_run_context
        from cj_memory.local import LocalMemoryConfiguration
        import local_run_context as operator
        now=int(time.time())
        path=self.auth/'runtime-meter.json'
        path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@1',current=dict(meter=dict(
            unit='provider_call',budget=20,period_start=now-60,period_end=now+3600,
            max_steps=4,max_tools=1,max_output=10000,max_seconds=600),
            output_limits=dict(answer=1000,draft=1000)),history=[])))
        context=load_run_context(path)
        for identity in ('alice','bob'):
            operator.provision_budget(run_worker_database_path(),context,identity)
        database=LocalDatabase(run_worker_database_path(),run_context=context)
        app=create_local_app(conninfo_path=run_worker_database_path(),auth_dir=self.auth,
            run_context=context,memory_configuration=LocalMemoryConfiguration.from_bytes(json.dumps(self.policy).encode()))
        with TestClient(app) as client:
            self.assertEqual(self.save(client,self.raw()).status_code,200)
            mid,response=self.send(client,'alice','Metered memory',conversation=self.chat_a)
            self.assertEqual(response.status_code,200,response.text)
            model=ObservedProvider()
            outcomes=run_worker.run_once(database,model,self.auth,memory_configuration=self.configuration())
            self.assertEqual([o.status for o in outcomes if o.message_id==mid],['completed'])
            self.assertEqual(model.calls,1)
            self.assertIn(self.slots['preference'],model.inputs[0][0][0]['content'])

    def test_runtime_missing_config_rejects_before_accept(self):
        with TestClient(self.memory_app) as client:
            self.assertEqual(self.save(client,self.raw()).status_code,200)
            mid,response=self.send(client,'alice','No silent recall downgrade',conversation=self.chat_a)
            self.assertEqual(response.status_code,200,response.text)
            model=ObservedProvider()
            with self.assertRaises(RuntimeDenied):
                run_worker.run_once(self.database,model,self.auth)
            self.assertEqual(model.calls,0)
            self.assertEqual([o.status for o in self.execute(model) if o.message_id==mid],['completed'])

    def test_runtime_process_rebuild_and_policy_boundary(self):
        from cj_memory.domain import InvalidInput
        configured=self.configuration()
        source=dict(version='local-memory-run.1',collection=self.policy,
            selections={identity:dict(subject=selection.subject,slots=sorted(selection.slots),
                                      max_bytes=selection.max_bytes)
                        for identity,selection in configured.selections.items()})
        for key,value in [('subject','other-person'),('slots',[]),('max_bytes',True),('max_bytes',32769)]:
            invalid=json.loads(json.dumps(source))
            invalid['selections']['alice'][key]=value
            with self.assertRaises(InvalidInput): RuntimeConfiguration.from_bytes(json.dumps(invalid).encode())
        with self.assertRaises(InvalidInput):
            RuntimeConfiguration.from_bytes(b'{"version":"a","version":"b"}')
        path=self.auth/('runtime-'+self.tag+'.json')
        path.write_text(json.dumps(source)); path.chmod(0o600)
        with TestClient(self.memory_app) as client:
            self.assertEqual(self.save(client,self.raw()).status_code,200)
            mid,response=self.send(client,'alice','New actual worker process',conversation=self.chat_a)
            self.assertEqual(response.status_code,200,response.text)
            result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/run_worker.py'),
                '--conninfo-json',run_worker_database_path(),'--auth-dir',str(self.auth),
                '--memory-run-policy',str(path),'--once'],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('completed',result.stdout)
            self.assertEqual(self.events(client,'alice',mid)[-1][2],{'status':'completed'})


def run_worker_database_path():
    from e2e_local import CONNINFO
    return CONNINFO


if __name__=='__main__':
    unittest.main(verbosity=2)
