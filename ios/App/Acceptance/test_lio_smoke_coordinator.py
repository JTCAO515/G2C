from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from check_lio_read_window import main as check_read_window
from lio_basic_ui_driver import compact
from lio_basic_ui_projection import EvidenceUnknown
from watch_lio_basic_smoke import AdmittedNativeUI, Coordinator, current_window, read_full_reply


def save(path, value):
    path.write_bytes(compact(value, sort_keys=True)); path.chmod(0o600)


class CoordinatorFences(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = dict(protocol='LIO-message.2', surface='LOCAL_CONTROL_NOT_ACTUAL_APP')
        self.steps = [dict(gate_id='SEED1', locale='zh', text='Synthetic only',
                           nonce='synthetic-nonce-one', new_conversation=True),
                      dict(gate_id='SEED2', locale='zh', text='Synthetic continuation',
                           nonce='synthetic-nonce-two', new_conversation=False)]
        self.plan = dict(version='LIO-basic-chain-plan.2', app=self.app, first_setup=True,
                         run_id='synthetic-control-only', steps=self.steps)
        plan_path = self.root / 'plan.json'; save(plan_path, self.plan)
        self.config = dict(app=self.app, plan=dict(path=str(plan_path),
                           sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest()))

    def instruction(self, stem, step):
        path = self.root / (stem + '-prepare.json')
        save(path, dict(version='LIO-basic-ui-instruction.2', run_id=self.plan['run_id'],
                        app=self.app, step=step, expected_draft=None, accepted_conversations={}))
        return path

    def test_changed_approved_plan_stops_before_any_native_client(self):
        self.config['plan']['sha256'] = '0' * 64
        with self.assertRaises(EvidenceUnknown): Coordinator(self.config, self.root, self.root / 'out')

    def test_changed_text_and_out_of_order_instruction_never_reach_ui(self):
        for name, stem, step in [('text', '00', dict(self.steps[0], text='Unapproved text')),
                                 ('order', '01', self.steps[1])]:
            with self.subTest(name=name):
                runner = Coordinator(self.config, self.root, self.root / name)
                with patch.object(runner, 'client', side_effect=AssertionError('No UI allowed')):
                    with self.assertRaises(EvidenceUnknown): runner.phase(self.instruction(stem, step))
                self.assertEqual(runner.next_index, 0)
                self.assertFalse((self.root / (stem + '-A-prepared.json')).exists())

    def test_original_phase_record_prevents_restarting_the_same_attempt(self):
        runner = Coordinator(self.config, self.root, self.root / 'out')
        path = self.instruction('00', self.steps[0])
        save(self.root / '00-A-prepared.json', dict(scope='LOCAL_CONTROL_ONLY'))
        with patch.object(runner, 'client', side_effect=AssertionError('No UI allowed')):
            with self.assertRaises(EvidenceUnknown): runner.phase(path)
        self.assertFalse((self.root / '00-A-completed.json').exists())

    def test_issued_interval_can_cross_beijing_midnight_and_still_expires(self):
        config = dict(starts_at='2026-11-16T15:58:00Z', ends_at='2026-11-16T16:03:00Z')
        start, end = (datetime.fromisoformat(config[key]) for key in ('starts_at', 'ends_at'))
        for now in (start, datetime(2026, 11, 16, 16, tzinfo=timezone.utc)):
            with self.subTest(now=now), patch('watch_lio_basic_smoke.datetime', wraps=datetime) as clock:
                clock.now.return_value = now
                current_window(config)
        with patch('watch_lio_basic_smoke.datetime', wraps=datetime) as clock:
            clock.now.return_value = end
            with self.assertRaisesRegex(EvidenceUnknown, 'Outside the issued purpose interval'):
                current_window(config)

    def test_account_free_native_read_control_can_prepare_at_night(self):
        output = self.root / 'native-read-control'
        build = self.root / 'build'
        argv = ['check', '--simulator', 'owned-control', '--output', str(output),
                '--build-dir', str(build), '--case', 'snapshot']
        with patch('sys.argv', argv), patch('check_lio_read_window.datetime', wraps=datetime) as clock, \
                patch('check_lio_read_window.subprocess.run', return_value=SimpleNamespace(returncode=1)), \
                patch('check_lio_read_window.exercise') as exercise:
            clock.now.return_value = datetime(2026, 11, 16, 16, tzinfo=timezone.utc)
            check_read_window()
        exercise.assert_called_once_with(output.resolve() / 'snapshot', build.resolve(),
                                         'owned-control', 'snapshot_in_window')

    def test_each_mutation_rechecks_authority_and_passes_the_original_interval(self):
        native = object.__new__(AdmittedNativeUI)
        interval = dict(startsAt='2026-11-16T12:00:00Z', endsAt='2026-11-16T12:05:00Z')
        checks = []
        native.guard = lambda: checks.append(True) or interval
        with patch('watch_lio_basic_smoke.NativeUI.command', return_value={}) as command:
            native.command('tap', identifier='lio.send')
            command.assert_called_once_with('tap', identifier='lio.send', **interval)
        self.assertEqual(checks, [True])
        native.guard = lambda: (_ for _ in ()).throw(EvidenceUnknown('Expired'))
        with patch('watch_lio_basic_smoke.NativeUI.command') as command:
            with self.assertRaises(EvidenceUnknown): native.command('type', identifier='lio.composer', text='Synthetic')
            command.assert_not_called()

    def test_complete_reply_geometry_uses_body_label_not_status_value(self):
        nodes = [dict(identifier='lio.answer', label='Day 1\nDay 2\nDay 3', value='Reply complete', depth=1, frame=[20, 150, 300, 120]),
                 dict(identifier='lio.composer', label='', value='', depth=1, frame=[20, 700, 300, 40]),
                 dict(identifier='lio.name', label='Lio', value='', depth=1, frame=[180, 110, 30, 20])]
        capture = SimpleNamespace(raw=lambda: dict(nodes=nodes),
                                  action=lambda *args, **kwargs: self.fail('Whole visible reply needs no scrolling'))
        read_full_reply(capture, 'Day 1\nDay 2\nDay 3')

    def test_cold_failure_is_recorded_before_any_history_navigation(self):
        app = self.app
        step = dict(gate_id='SM01', locale='zh', text=None, nonce='synthetic-cold', new_conversation=False)
        plan = dict(self.plan, steps=[step])
        plan_path = self.root / 'cold-plan.json'; save(plan_path, plan)
        config = dict(self.config, plan=dict(path=str(plan_path), sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest()),
                      qualification_sha256='synthetic-q', admission_wait_seconds=1)
        runner = Coordinator(config, self.root, self.root / 'cold-out')
        runner.targets = {'zh': {'old': [dict(question='Q', answer='A', visible_failure=False)]}}
        instruction = self.root / '00-prepare.json'
        save(instruction, dict(version='LIO-basic-ui-instruction.2', app=app, run_id=plan['run_id'], step=step,
                               expected_draft='keep draft', accepted_conversations={'old': {}}))
        save(self.root / '00-admission.json', dict(version='LIO-basic-ui-admission.2', run_id=plan['run_id'],
             nonce=step['nonce'], qualification_sha256='synthetic-q', checkpoint_ref='synthetic-checkpoint'))
        before = dict(errors=[], body_complete=True, transcript=runner.targets['zh']['old'], draft='keep draft', greeting_count=0)
        after = dict(before, errors=['Actual read failure'], body_complete=False, transcript=[])
        immediate_calls = []
        fake = SimpleNamespace(native=SimpleNamespace(simulator='synthetic'), originals=[],
            select_transcript=lambda *args: None, draft=lambda *args: ({}, dict(before)),
            ready=lambda **kwargs: ({}, dict(before)), action=lambda *args, **kwargs: None,
            immediate=lambda **kwargs: immediate_calls.append(True) or ({}, dict(before if len(immediate_calls) == 1 else after)),
            history=lambda *args: self.fail('Do not repair an immediate cold failure through history navigation'))
        with patch.object(runner, 'guard', return_value={}), patch.object(runner, 'client', return_value=fake), \
                patch('watch_lio_basic_smoke.verify_installation'):
            runner.phase(instruction)
        from lio_basic_ui_driver import decode
        witness = decode((self.root / '00-A-completed.json').read_bytes())
        self.assertEqual(immediate_calls, [True, True])
        self.assertFalse(witness['lifecycle'][0]['body_complete'])
        self.assertEqual(witness['lifecycle'][0]['errors'], ['Actual read failure'])

    def test_history_does_not_count_the_default_again_after_c_accepted_it(self):
        step = dict(gate_id='SM03', locale='zh', text=None, nonce='synthetic-history', new_conversation=False)
        plan = dict(self.plan, steps=[step])
        path = self.root / 'history-plan.json'; save(path, plan)
        config = dict(self.config, plan=dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
                      qualification_sha256='q', admission_wait_seconds=1)
        runner = Coordinator(config, self.root, self.root / 'history-out')
        instruction = self.root / '00-prepare.json'
        save(instruction, dict(version='LIO-basic-ui-instruction.2', app=self.app, run_id=plan['run_id'], step=step,
                               expected_draft=None, accepted_conversations={'cid-a': {}, 'cid-b': {}, 'cid-c': {}}))
        save(self.root / '00-admission.json', dict(version='LIO-basic-ui-admission.2', run_id=plan['run_id'],
             nonce=step['nonce'], qualification_sha256='q', checkpoint_ref='synthetic-checkpoint'))
        before = dict(errors=[], body_complete=True, transcript=[], draft='', greeting_count=0)
        counts = []
        def history(count):
            counts.append(count)
            self.assertEqual(count, 3)
            return dict(rows=[], opened=[])
        fake = SimpleNamespace(native=SimpleNamespace(simulator='synthetic'), originals=[],
                               ready=lambda **kwargs: ({}, dict(before)), immediate=lambda **kwargs: ({}, dict(before)), history=history)
        with patch.object(runner, 'guard', return_value={}), patch.object(runner, 'client', return_value=fake), \
                patch('watch_lio_basic_smoke.verify_installation'):
            runner.phase(instruction)
        self.assertEqual(counts, [3])

    def test_lifecycle_record_cannot_be_rewritten_by_later_navigation(self):
        from watch_lio_basic_smoke import lifecycle_snapshot
        view = dict(transcript=[dict(question='Q', answer='A', visible_failure=False)],
                    draft='keep', errors=[], body_complete=True)
        sealed = lifecycle_snapshot('cold_launch', view)
        view['errors'].append('Later navigation failure')
        view['transcript'][0]['answer'] = 'Later answer'
        view['body_complete'] = False
        self.assertEqual(sealed['errors'], [])
        self.assertEqual(sealed['transcript'][0]['answer'], 'A')
        self.assertTrue(sealed['body_complete'])

    def test_checkpoint_reobserves_fresh_ui_before_dispatch_instead_of_borrowing_preparation(self):
        step = dict(gate_id='SM03', locale='zh', text=None, nonce='synthetic-fresh', new_conversation=False)
        plan = dict(self.plan, steps=[step]); path = self.root / 'fresh-plan.json'; save(path, plan)
        config = dict(self.config, plan=dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
                      qualification_sha256='q', admission_wait_seconds=1)
        runner = Coordinator(config, self.root, self.root / 'fresh-out')
        instruction = self.root / '00-prepare.json'
        save(instruction, dict(version='LIO-basic-ui-instruction.2', app=self.app, run_id=plan['run_id'], step=step,
                               expected_draft=None, accepted_conversations={'cid-a': {}}))
        save(self.root / '00-admission.json', dict(version='LIO-basic-ui-admission.2', run_id=plan['run_id'],
             nonce=step['nonce'], qualification_sha256='q', checkpoint_ref='synthetic-checkpoint'))
        before = dict(errors=[], body_complete=True, transcript=[dict(question='Q', answer='A', visible_failure=False)],
                      draft='', greeting_count=0)
        fake = SimpleNamespace(native=SimpleNamespace(simulator='synthetic'), originals=[],
            ready=lambda **kwargs: ({}, dict(before)),
            immediate=lambda **kwargs: ({}, dict(before, body_complete=False, transcript=[])),
            history=lambda *args: self.fail('Current UI was not independently reobserved after checkpoint'))
        with patch.object(runner, 'guard', return_value={}), patch.object(runner, 'client', return_value=fake), \
                patch('watch_lio_basic_smoke.verify_installation'):
            with self.assertRaises(EvidenceUnknown): runner.phase(instruction)


if __name__ == '__main__': unittest.main()
