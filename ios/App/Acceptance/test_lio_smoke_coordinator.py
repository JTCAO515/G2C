from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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


if __name__ == '__main__': unittest.main()
