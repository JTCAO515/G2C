"""Host lifecycle/closure controls, not a live simulator qualification."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, RLock
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import sqlite3

from cj_api.runtime_simulator_host import NativeSimulatorHost, SimulatorEpisode
from cj_strict_json import compact
from eval.lio_simulated_user.runner import HostUnavailable
from runtime_adapter.contract import Unavailable, Invalid


class SimulatorHostTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.root.chmod(0o700)
        self.host = NativeSimulatorHost.__new__(NativeSimulatorHost)
        h = self.host
        h.directory = self.root
        info=self.root.stat();h.directory_identity=(info.st_dev,info.st_ino)
        h.path = self.root/'manifest.json'; h.raw = compact({'fixture': True})
        h.path.write_bytes(h.raw); h.path.chmod(0o600)
        self.now = datetime(2026, 11, 16, 11, tzinfo=timezone.utc)
        h.start = self.now-timedelta(seconds=1); h.end = self.now+timedelta(minutes=5)
        h.wall_clock = lambda: self.now
        h.stopped = False; h.lock = RLock(); h.execution_lock = RLock()
        h.worker_failed = Event()
        h.worker_ready = Event(); h.cohort_thread = None; h.cohort_failure = None
        h.active = None; h.episodes = {}; h.by_message = {}; h.next_slot = 0

    def test_stop_expiry_manifest_change_and_closed_episode_refuse_new_work(self):
        h = self.host; episode = SimpleNamespace(closed=False); spec = SimpleNamespace(raw=b'actual pins')
        self.assertEqual(h.current(spec, episode), b'actual pins')
        for fault in ('stop', 'expired', 'closed', 'manifest', 'marker'):
            with self.subTest(fault=fault):
                if fault == 'stop': h.stopped = True
                elif fault == 'expired': self.now = h.end
                elif fault == 'closed': episode.closed = True
                elif fault == 'manifest': h.path.write_bytes(b'changed')
                else: (self.root/'STOP_NEW.json').symlink_to(self.root/'missing')
                with self.assertRaises(Unavailable): h.current(spec, episode)
                h.stopped = False; self.now = h.start+timedelta(seconds=1); episode.closed = False
                h.path.write_bytes(h.raw)
                if fault == 'marker': (self.root/'STOP_NEW.json').unlink()

    def test_private_results_are_append_only_without_symlink_following(self):
        h = self.host
        h.save('result.json', {'status': 'UNKNOWN'})
        before = (self.root/'result.json').read_bytes()
        self.assertEqual((self.root/'result.json').stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError): h.save('result.json', {'status': 'PASS'})
        self.assertEqual((self.root/'result.json').read_bytes(), before)
        (self.root/'link.json').symlink_to(self.root/'result.json')
        with self.assertRaises(FileExistsError): h.save('link.json', {'status': 'PASS'})
        self.assertEqual((self.root/'result.json').read_bytes(), before)

    def test_explicit_start_only_once_and_operational_failure_is_query_only(self):
        h = self.host
        def failure(): raise Unavailable('FIXTURE_ORIGINAL_UNAVAILABLE')
        h.run_cohort = failure
        h.begin(); h.cohort_thread.join(2)
        self.assertFalse(h.cohort_thread.is_alive())
        self.assertTrue(h.stopped)
        self.assertEqual(h.cohort_failure, 'SIMULATOR_COHORT_STOPPED_QUERY_ONLY')
        with self.assertRaises(Invalid): h.begin()
        h.run_cohort = lambda: (_ for _ in ()).throw(TypeError('programming error'))
        with self.assertRaises(TypeError): h._cohort_entry()

    def test_replaced_results_directory_cannot_lose_durable_intent(self):
        h=self.host
        h.save('cohort.intent.json',{'original': True})
        original=h.directory
        replacement=self.root/'replacement';replacement.mkdir(mode=0o700)
        h.directory=replacement
        with self.assertRaises(Invalid):h.save('cohort.intent.json',{'replacement': True})
        self.assertFalse((replacement/'cohort.intent.json').exists())
        self.assertTrue((original/'cohort.intent.json').exists())

    def test_worker_failure_stops_new_work_and_wakes_original_wait(self):
        h=self.host;h.clock=lambda:0
        episode=SimpleNamespace(session={'scope':'original-scope'})
        h.active=episode;h.by_message={('original-scope','mid'):episode}
        h.worker_unavailable()
        self.assertTrue(h.stopped)
        with self.assertRaises(Unavailable):h.wait_original(SimpleNamespace(message_id='mid'),100)

    def test_restart_with_original_intent_is_query_only(self):
        h = self.host; h.worker_ready.set()
        h.data = dict(window_id='fixture',runtime_card={})
        h.cohort = dict(dataset_sha256='a'*64,slots=[])
        h.save('cohort.intent.json',{'original': True})
        before = (self.root/'cohort.intent.json').read_bytes()
        with self.assertRaises(Unavailable): h.run_cohort()
        self.assertTrue(h.stopped)
        self.assertEqual((self.root/'cohort.intent.json').read_bytes(), before)
        self.assertFalse((self.root/'cohort.result.json').exists())


class EpisodeCostClosureTest(TestCase):
    def make_episode(self):
        e = SimulatorEpisode.__new__(SimulatorEpisode)
        e.closed = False; e.actor_charge_proofs = {}; e.last_cost_report = None
        e.session = dict(token=lambda:'fixture-token')
        e.specification = SimpleNamespace(key='fixture-pins')
        e.dut = SimpleNamespace(stopped=False, originals=[dict(step_id='mid')],
                                owner='owner',authority=SimpleNamespace(require=lambda **kw:None))
        e.actor = SimpleNamespace(originals=[])
        e.host = SimpleNamespace(clock=lambda:100)
        e.originals = SimpleNamespace(cost_tail=lambda token,mid:compact(dict(
            delivery_acknowledged=True,associated_history_jobs=[])))
        e.before_background = []; e.background = lambda:[]
        e.before_journal = dict(rows=[],anchor=dict(count=0,sha256='before'))
        e.journal = lambda:dict(rows=[('fee','model','wire','RECEIVED','receipt')],
                               anchor=dict(count=1,sha256='after'))
        e.returns = {('mid','run'):dict(status='completed')}
        e.report = dict(message_id='mid',run_id='run',status='completed',inventory_sha256='a'*64,operations=[dict(attempt_id='fee',
            financial_attempt=True,conservative_units=1000000,estimated_units=None)])
        return e

    def test_complete_requires_original_return_memory_closure_and_exact_journal(self):
        e = self.make_episode()
        with patch('cj_api.runtime_simulator_host.original_charges',return_value=e.report):
            value = e.original_cost()
        self.assertTrue(e.closed and e.dut.stopped)
        self.assertEqual(e.last_cost_report['coverage'],'COMPLETE')
        self.assertEqual(len(e.last_cost_report['producer_returns']),1)
        self.assertEqual(len(e.last_cost_report['memory_tails']),1)
        self.assertEqual(e.last_cost_report['inventory_proofs'][0]['inventory_sha256'],'a'*64)
        self.assertIsNone(value['token_estimate_cny'])
        self.assertIsNone(value['actual_paid_cny'])

    def test_missing_return_pending_memory_foreign_fee_or_background_never_complete(self):
        for fault in ('return','memory','fee','old_fee_changed','background','operational'):
            e = self.make_episode()
            if fault == 'return': e.returns.clear()
            elif fault == 'memory': e.originals.cost_tail = lambda *a:compact(dict(
                delivery_acknowledged=True,associated_history_jobs=[dict(state='pending')]))
            elif fault == 'fee': e.journal=lambda:dict(rows=[('foreign','model','wire','RECEIVED','receipt')],anchor={})
            elif fault == 'old_fee_changed': e.before_journal['rows']=[('old','model','wire','UNKNOWN',None)]
            elif fault == 'background': e.background=lambda:[('new-job',)]
            else: e.background=lambda:(_ for _ in ()).throw(sqlite3.OperationalError('io'))
            with self.subTest(fault=fault), patch('cj_api.runtime_simulator_host.original_charges',return_value=e.report):
                with self.assertRaises(HostUnavailable): e.original_cost()
                self.assertEqual(e.last_cost_report['coverage'],'UNKNOWN')
                self.assertTrue(e.closed and e.dut.stopped)

    def test_programming_error_propagates_without_inventing_financial_verdict(self):
        e = self.make_episode()
        e.background = lambda:(_ for _ in ()).throw(sqlite3.ProgrammingError('programming'))
        with patch('cj_api.runtime_simulator_host.original_charges',return_value=e.report):
            with self.assertRaises(sqlite3.ProgrammingError): e.original_cost()
        self.assertIsNone(e.last_cost_report)
