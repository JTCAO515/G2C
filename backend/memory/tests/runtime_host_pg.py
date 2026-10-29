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
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import time
        from cj_api.local_run_context import load_run_context
        import local_run_context as operator
        now=int(time.time())
        cls.run_path=cls.auth/'memory-meter.json'
        cls.run_path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@1',current=dict(meter=dict(
            unit='provider_call',budget=100,period_start=now-60,period_end=now+3600,
            max_steps=4,max_tools=1,max_output=10000,max_seconds=600),
            output_limits=dict(answer=1000,draft=1000)),history=[])))
        cls.run_context=load_run_context(cls.run_path)
        for identity in ('alice','bob'):
            operator.provision_budget(run_worker_database_path(),cls.run_context,identity)
        cls.database=LocalDatabase(run_worker_database_path(),run_context=cls.run_context)

    def setUp(self):
        helpers.MemorySaveReadChecks.setUp(self)
        self.runtime_expiry=self.policy['expires_at']

    write_policy = helpers.MemorySaveReadChecks.write_policy
    def app_from_policy(self, *, enabled=True):
        import os
        with patch.dict(os.environ,{'CJ_LOCAL_RUN_CONTEXT':str(self.run_path)}):
            return helpers.MemorySaveReadChecks.app_from_policy(self,enabled=enabled)
    raw = helpers.MemorySaveReadChecks.raw
    save = helpers.MemorySaveReadChecks.save
    receipt = helpers.MemorySaveReadChecks.receipt
    service = helpers.MemorySaveReadChecks.service

    def configuration(self):
        return RuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.1',
            collection=dict(self.policy,expires_at=self.runtime_expiry), selections={identity: dict(subject='self',
                slots=[slot for slot,rule in self.policy['profiles'][identity]['slots'].items()
                       if rule['collection_allowed'] and rule['semantic_resolved']], max_bytes=32768)
                for identity in ('alice','bob')})).encode())

    def execute(self, model):
        # Reconstruct the actual factory each time; no synthetic Context enters RUN.
        return run_worker.run_once(LocalDatabase(run_worker_database_path(),run_context=self.run_context), model,
                                   self.auth, memory_configuration=self.configuration())

    def test_runtime_original_receipt_and_rollback_before_consume(self):
        from contextlib import contextmanager
        from cj_memory.postgres import Repository
        from cj_memory.domain import CommitUnknown, Unavailable
        transaction=Repository.transaction
        with TestClient(self.memory_app) as client:
            raw=self.raw('fact',text='Committed original / 已提交原文')
            @contextmanager
            def lost_ack(repository):
                with transaction(repository) as tx: yield tx
                raise CommitUnknown('fixture ACK lost after real commit')
            with patch.object(Repository,'transaction',lost_ack):
                unknown=self.save(client,raw)
            self.assertEqual(unknown.status_code,503)
            self.assertNotIn('receipt',unknown.json())
            self.assertEqual(unknown.json()['error']['recovery'],'reconcile_original')
            original=self.receipt(client,raw)
            self.assertEqual(original.status_code,200)
            self.assertEqual(original.json()['receipt']['item_id'],json.loads(raw)['item_id'])
            self.assertEqual(self.save(client,raw).json()['receipt'],original.json()['receipt'])
            failed=self.raw('experience',text='Rolled back / 已回滚')
            @contextmanager
            def rollback(repository):
                with transaction(repository) as tx:
                    yield tx
                    raise Unavailable('fixture failure before real commit')
            with patch.object(Repository,'transaction',rollback):
                self.assertNotEqual(self.save(client,failed).status_code,200)
            self.assertIsNone(self.receipt(client,failed).json()['receipt'])
            mid,response=self.send(client,'alice','Use confirmed original only',conversation=self.chat_a)
            self.assertEqual(response.status_code,200,response.text)
            model=ObservedProvider();outcomes=self.execute(model)
            self.assertEqual([o.status for o in outcomes if o.message_id==mid],['completed'])
            data=json.loads(model.inputs[0][0][0]['content'].split('\n',1)[1])
            self.assertEqual([i['text'] for i in data['items']],['Committed original / 已提交原文'])

    def test_runtime_ineligible_rows_are_not_provider_context(self):
        # Pre-existing invalid/inactive fixtures use the actual restricted role.
        # This is filtering evidence, not a user pause/withdrawal acceptance claim.
        from datetime import datetime,timedelta,timezone
        scope=scope_for(ISSUER,'alice')
        cases=[('candidate',dict(status='candidate',kind='inference')),
               ('unconfirmed',dict(confirmed=False)),('unauthorized',dict(authorized=False)),
               ('unresolved',dict(semantic_resolved=False)),('disabled',dict(status='disabled')),
               ('withdrawn',dict(status='withdrawn')),('inactive-source',dict(active=False)),
               ('expired',dict(expired=True))]
        with self.database.connect(scope) as conn:
            conn.execute('INSERT INTO cj_memory_scope(scope) VALUES (%s) ON CONFLICT DO NOTHING',(scope,))
            for name,changes in cases:
                slot=name+'-'+self.tag
                for profile in self.policy['profiles'].values():
                    profile['slots'][slot]=dict(kind='fact',collection_allowed=True,semantic_resolved=True)
                item='fixture-'+slot;source='source-'+slot
                raw=json.dumps(dict(operation_id='op-'+item,item_id=item,subject='self',slot=slot,
                    kind=changes.get('kind','fact'),text='Excluded '+name,extent='long_term',context_id=None,
                    source_id=source,source_version=1,occurred_at='fixture; date unknown')).encode()
                expires=datetime.now(timezone.utc)+timedelta(seconds=-1 if changes.get('expired') else 3600)
                conn.execute('INSERT INTO cj_memory_source VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s)',
                    (scope,source,raw,changes.get('authorized',True),changes.get('confirmed',True),
                     changes.get('semantic_resolved',True),changes.get('active',True),expires))
                conn.execute('INSERT INTO cj_memory_item(scope,item_id,version,status,subject,slot,extent,context_id,source_id,source_version,original_input) '
                    "VALUES (%s,%s,1,%s,'self',%s,'long_term','',%s,1,%s)",
                    (scope,item,changes.get('status','active'),slot,source,raw))
        self.write_policy();self.memory_app=self.app_from_policy()
        with TestClient(self.memory_app) as client:
            self.assertEqual(self.save(client,self.raw(text='合法原文 / valid original')).status_code,200)
            self.assertEqual(self.save(client,self.raw(text='English synonym for same canonical slot')).status_code,409)
            mid,response=self.send(client,'alice','Read current eligible data',conversation=self.chat_a)
            self.assertEqual(response.status_code,200,response.text)
            model=ObservedProvider();outcomes=self.execute(model)
            self.assertEqual([o.status for o in outcomes if o.message_id==mid],['completed'])
            data=json.loads(model.inputs[0][0][0]['content'].split('\n',1)[1])
            self.assertEqual([i['text'] for i in data['items']],['合法原文 / valid original'])
            self.assertEqual(data['items'][0]['source_version'],1)
            self.assertEqual(data['items'][0]['subject'],'self')

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
        deadline=datetime.now(timezone.utc)+timedelta(seconds=10)
        self.policy['expires_at']=deadline.isoformat()
        self.write_policy(); self.memory_app=self.app_from_policy()
        with TestClient(self.memory_app) as client:
            self.assertEqual(self.save(client,self.raw()).status_code,200)
            mid,response=self.send(client,'alice','A short answer',conversation=self.chat_a)
            self.assertEqual(response.status_code,200,response.text)
            model=ObservedProvider(after_first=lambda:time.sleep(max(0,deadline.timestamp()-time.time())+.05))
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
        path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(
            unit='provider_call',budget=100,period_start=now-60,period_end=now+3600,
            max_steps=4,max_tools=1,max_output=10000,max_seconds=600),
            output_limits=dict(model=1000,tool=1000,memory=1000)),history=[])))
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
                '--run-context',str(self.run_path),'--memory-run-policy',str(path),'--once'],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('completed',result.stdout)
            self.assertEqual(self.events(client,'alice',mid)[-1][2],{'status':'completed'})


def run_worker_database_path():
    from e2e_local import CONNINFO
    return CONNINFO


if __name__=='__main__':
    unittest.main(verbosity=2)
