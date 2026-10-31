"""C344 actual producer/worker/typed-memory; no real services or fake Context."""
import sys,json,unittest,threading,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import psycopg
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/memory/tests'),str(ROOT/'backend/agent/tests'),str(ROOT/'scripts')]
from edit_support import Fixture,ProbePublisher,Model,Harness,CONNINFO
from cj_memory.postgres import Transaction
from cj_memory.runtime import RuntimeDenied,RuntimeUnknown
from cj_agent.draft import trip_scope_for


class EditMemoryChecks(unittest.TestCase):
    headers=Harness.headers
    setUpClass=classmethod(Harness.setUpClass.__func__)
    tearDownClass=classmethod(Harness.tearDownClass.__func__)

    def test_real_current_long_and_independent_temporary_scope_and_live_lease(self):
        f=Fixture(self,'eligible',ProbePublisher());binding=f.send('first')
        model=Model();host=f.host_worker(model);seen=[];capture=host.memory.capture
        def observe_capture(bound):
            value=capture(bound);seen.append(value);return value
        with patch.object(host.memory,'capture',observe_capture):result=host.process()[0]
        memory_run=seen[0]
        self.assertEqual(result.status,'completed');self.assertIsNotNone(result.proposal_id)
        self.assertEqual(memory_run.context.kind,'travel');self.assertEqual(memory_run.context.id,f.namespace['id'])
        self.assertNotEqual(f.namespace['id'],f.trip.trip_id)
        payload=json.loads(memory_run.payload)
        self.assertEqual({v['text'] for v in payload['items']},{'Vegetarian / 素食','Slow / 慢行'})
        self.assertTrue(all('Do not leak other trip' not in m['content'] for inputs in model.inputs for m in inputs))
        with self.assertRaises(RuntimeDenied):memory_run.check()
        # The actual publication must not open a second Trip SHARE while owning UPDATE.
        calls=[];original=host.message_context.hold_for_effect
        from contextlib import contextmanager
        @contextmanager
        def observe(bound,*,source_lock=True):
            calls.append(source_lock)
            with original(bound,source_lock=source_lock) as lease:yield lease
        with patch.object(host.message_context,'hold_for_effect',observe):
            with host.message_context.publication(binding,host.message_context.capture(binding),phase='accept',deadline=lambda:None) as pub:
                pub.enter_source(memory_run.hold(binding));pub.lock_trip();pub.before_write()
        self.assertEqual(calls,[False])

    def test_edit_pause_resume_stop_and_fresh_identity_never_publish_old_memory(self):
        from fastapi.testclient import TestClient
        from cj_trip.domain import packed
        for operation in ('edit','pause','resume','withdraw','revoke'):
            with self.subTest(operation=operation):
                f=Fixture(self,'fence-'+operation,ProbePublisher())
                if operation=='resume':f.manage('pause',1)
                binding=f.send('old-input');model=Model()
                invitations=(f.auth/'invited.json').read_bytes()
                def change():
                    if operation=='edit':f.manage('edit',1,text='New preference / 新偏好')
                    elif operation=='pause':f.manage('pause',1)
                    elif operation=='resume':f.manage('resume',2)
                    elif operation=='withdraw':
                        with TestClient(f.memory_app) as client:
                            item=client.get('/v2/memory-items',params={'item_id':'mem-long'},headers=f.headers).json()['item']
                            body=packed(dict(version='MEMORY-STOP-USE@2',action_id='stop-original',operation='withdraw',item_id='mem-long',
                                expected_version=1,source_id=item['command']['source_id'],expected_source_version=1))
                            response=client.post('/v2/memory-withdrawal-actions',content=body,headers={**f.headers,'Content-Type':'application/octet-stream'})
                            self.assertEqual(response.status_code,200,response.text)
                    else:(f.auth/'invited.json').write_text(json.dumps([]))
                model.hook=change
                try:
                    outcome=f.run(model)[0]
                    self.assertEqual(outcome.status,'context_invalid');self.assertIsNone(outcome.proposal_id)
                finally:(f.auth/'invited.json').write_bytes(invitations)
                state=f.database.run_repository(f.scope).recover(binding).state
                self.assertEqual(state.effects,());self.assertEqual(state.text,'')
                if operation!='revoke':
                    f.send('new-input');fresh=Model();self.assertEqual(f.run(fresh)[0].status,'completed')
                    data=''.join(message['content'] for inputs in fresh.inputs for message in inputs)
                    if operation=='edit':self.assertIn('New preference',data);self.assertNotIn('Vegetarian',data)
                    elif operation in ('pause','withdraw'):self.assertNotIn('Vegetarian',data)
                    else:self.assertIn('Vegetarian',data)
                    self.assertIn('Slow / 慢行',data);self.assertNotIn('Do not leak other trip',data)

    def test_unknown_or_missing_namespace_withholds_instead_of_empty_or_partial(self):
        from cj_message.edit_reference import EditAuthority
        from cj_message.domain import Unavailable
        f=Fixture(self,'withhold',ProbePublisher());binding=f.send('unknown')
        host=f.host_worker(Model())
        with patch.object(host.memory.service,'with_operation',side_effect=RuntimeUnknown('actual dependency unavailable')):
            with self.assertRaises(RuntimeUnknown):host.memory.capture(binding)
        wrong=f.host.headers['other-'+f.subject]['Authorization']
        from cj_auth.interfaces import AdmissionStatus
        from cj_api.local_worker_context import checker_for
        checker=checker_for(f.auth)
        other=lambda:checker.check(wrong[7:]).principal
        with self.assertRaises(RuntimeDenied):f.memory.bind(f.database,f.scope,'other-'+f.subject,other,message_context=host.message_context).capture(binding)
        with self.assertRaises(RuntimeDenied):f.memory.bind(f.database,f.scope,f.subject,host.memory.guard,message_context=None)
        from fastapi.testclient import TestClient
        with TestClient(f.app) as client:
            from cj_trip.domain import packed
            response=client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id='advance',operation='advance',
                travel_context=dict(id=f.namespace['id'],expected_version=1))),headers={**f.headers,'Content-Type':'application/octet-stream'})
            self.assertEqual(response.status_code,200,response.text)
        from cj_run.core import Denied
        with self.assertRaises((Denied,RuntimeDenied,Unavailable)):
            host.memory.capture(binding)

    def wait_memory(self):
        with psycopg.connect(**json.loads(Path(CONNINFO).read_text()),autocommit=True) as observer:
            end=time.monotonic()+4
            while time.monotonic()<end:
                if observer.execute("SELECT count(*) FROM pg_stat_activity WHERE usename='cj_m1_runtime' AND wait_event_type='Lock' AND query LIKE '%SELECT epoch FROM cj_memory_scope%'").fetchone()[0]:return
                time.sleep(.01)
        self.fail('actual Memory lock wait not observed')

    def test_publication_memory_first_does_not_deadlock_concurrent_capture_trip_read(self):
        f=Fixture(self,'publication-first',ProbePublisher());binding=f.send('locking')
        model=Model();host=f.host_worker(model)
        entered=threading.Event();release=threading.Event()
        def held():entered.set();self.assertTrue(release.wait(8))
        f.publisher.after_sources=held
        with ThreadPoolExecutor(max_workers=2) as pool:
            running=pool.submit(host.process);self.assertTrue(entered.wait(10))
            capture=pool.submit(host.memory.capture,binding)
            try:self.wait_memory();self.assertFalse(capture.done())
            finally:release.set()
            result=running.result(timeout=15)[0];captured=capture.result(timeout=15)
        self.assertEqual(result.status,'completed');self.assertIsNotNone(result.proposal_id)
        self.assertEqual(captured.context.id,f.namespace['id'])

    def test_capture_memory_first_releases_trip_before_publication(self):
        f=Fixture(self,'capture-first',ProbePublisher());binding=f.send('locking')
        model=Model();host=f.host_worker(model)
        model_entered=threading.Event();model_release=threading.Event();capture_entered=threading.Event();capture_release=threading.Event()
        def model_pause():model_entered.set();self.assertTrue(model_release.wait(10))
        model.hook=model_pause
        original=Transaction.lock_scope;capture_thread=[]
        def lock(tx):
            value=original(tx)
            if threading.get_ident() in capture_thread:
                capture_entered.set();self.assertTrue(capture_release.wait(10))
            return value
        def capture():capture_thread.append(threading.get_ident());return host.memory.capture(binding)
        with ThreadPoolExecutor(max_workers=2) as pool:
            running=pool.submit(host.process);self.assertTrue(model_entered.wait(10))
            with patch.object(Transaction,'lock_scope',lock):
                reading=pool.submit(capture);self.assertTrue(capture_entered.wait(10))
                # Capture holds Memory; an unrelated real Trip writer can still UPDATE.
                with psycopg.connect(**json.loads(Path(CONNINFO).read_text()),autocommit=True) as writer:
                    with writer.transaction():
                        writer.execute("SET LOCAL lock_timeout='1s'")
                        writer.execute('SELECT scope FROM cj_trip_scope WHERE scope=%s FOR UPDATE',(trip_scope_for(f.scope),))
                model_release.set()
                try:self.wait_memory();self.assertFalse(running.done())
                finally:capture_release.set()
                captured=reading.result(timeout=15);result=running.result(timeout=15)[0]
        self.assertEqual(result.status,'completed');self.assertIsNotNone(result.proposal_id)
        self.assertEqual(captured.context.id,f.namespace['id'])


if __name__=='__main__':unittest.main(verbosity=2)
