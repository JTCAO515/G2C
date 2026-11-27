"""`rich.trip_receipt` on the timeline row (#1984, T-1 #1994): the read-side check and the envelope hook."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from cj_api.lio_dialogue_routes import RICH_VERSION, _message
from cj_message import lio_rich_receipt as rr
from cj_message.lio_context import LioLayout

EXAMPLES = json.loads((Path(__file__).resolve().parents[3] / 'contracts/message/lio-answer-rich-examples.1.json').read_text(encoding='utf-8'))
RECEIPTS = [(e['name'], e['rich']['trip_receipt']) for e in EXAMPLES['valid'] if 'trip_receipt' in e['rich']]
BAD_RECEIPTS = [(e['name'], e['rich']['trip_receipt']) for e in EXAMPLES['invalid'] if 'trip_receipt' in e['rich']]
SAVED = dict(next(r for n, r in RECEIPTS if n == 'saved, undo available'))
FIRST = dict(next(r for n, r in RECEIPTS if n.startswith('first save of a new trip: undo removes it')))


class Wire(unittest.TestCase):
    def test_every_valid_contract_receipt_passes_unchanged(self):
        self.assertGreaterEqual(len(RECEIPTS), 10)
        for name, receipt in RECEIPTS:
            with self.subTest(name=name):
                self.assertEqual(rr.wire(receipt), receipt)

    def test_every_invalid_contract_receipt_is_left_out(self):
        self.assertGreaterEqual(len(BAD_RECEIPTS), 25)
        for name, receipt in BAD_RECEIPTS:
            with self.subTest(name=name):
                self.assertIsNone(rr.wire(receipt))

    def test_the_trip_side_object_and_its_first_flag(self):
        plain = dict(SAVED)
        plain.pop('first_autosave', None)
        out = rr.wire(SimpleNamespace(wire=plain, first=True))
        self.assertIs(out['first_autosave'], True)
        self.assertNotIn('first_autosave', rr.wire(SimpleNamespace(wire=plain, first=False)))
        self.assertEqual(rr.wire(SimpleNamespace(wire=dict(plain, first_autosave=True), first=False))['first_autosave'], True)
        self.assertIsNone(rr.wire(SimpleNamespace(wire=dict(plain, first_autosave=False), first=False)))

    def test_odd_input_never_raises(self):
        for value in (None, 5, 'x', [], {}, {'status': 'saved'}, SimpleNamespace(), SimpleNamespace(wire=None), {'status': 'saved', 'action_id': 'a', 'undo': 7}):
            self.assertIsNone(rr.wire(value))


def item():
    return SimpleNamespace(message_id='m1', text='帮我排行程', locale='zh')


def state(status, text, *effects):
    return SimpleNamespace(status=status, text=text, effects=tuple(effects), draft_outcome=None, budget_exhausted_stage='none')


SPLIT = LioLayout('split').effect()


class Row(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {'CJ_LIO_ANSWER_RICH': 'on'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def row(self, status, text, declared='rich', receipt=SAVED):
        return _message(item(), state(status, text, SPLIT), declared=declared, receipt=receipt)

    def test_a_completed_row_carries_the_receipt_even_without_entities_or_cards(self):
        rich = self.row('completed', '好的。\n\n已为你排好。')['rich']
        self.assertEqual(rich, dict(version=RICH_VERSION, trip_receipt=SAVED))

    def test_a_failed_row_keeps_the_receipt_so_the_save_can_be_undone(self):
        row = self.row('failed', '')
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['rich'], dict(version=RICH_VERSION, trip_receipt=SAVED))

    def test_a_first_save_receipt_rides_the_row(self):
        rich = self.row('completed', '好的', receipt=FIRST)['rich']
        self.assertEqual(rich['trip_receipt']['committed_version'], 1)
        self.assertEqual(rich['trip_receipt']['undo']['kind'], 'remove_created')
        self.assertIs(rich['trip_receipt']['first_autosave'], True)

    def test_no_receipt_for_a_poll_that_did_not_declare_rich_or_while_the_switch_is_off(self):
        for declared in (False, True):
            self.assertNotIn('rich', self.row('completed', '好的', declared=declared))
        with mock.patch.dict(os.environ, {'CJ_LIO_ANSWER_RICH': 'off'}):
            self.assertNotIn('rich', self.row('completed', '好的'))

    def test_a_bad_receipt_is_left_out_and_the_row_is_intact(self):
        plain = _message(item(), state('completed', '好的', SPLIT), declared=True)
        for name, bad in BAD_RECEIPTS[:5]:
            row = self.row('completed', '好的', receipt=bad)
            self.assertNotIn('rich', row, name)
            self.assertEqual({k: v for k, v in row.items()}, plain)

    def test_sending_and_answering_rows_never_carry_rich(self):
        self.assertNotIn('rich', _message(item(), state('running', '部分'), declared='rich', receipt=SAVED))
        self.assertNotIn('rich', _message(item(), None, declared='rich', receipt=SAVED))


class Reader(unittest.TestCase):
    def test_the_reader_is_asked_only_for_a_run_with_a_receipt_effect(self):
        from cj_api.lio_dialogue_routes import _receipt
        asked = []

        def reader(scope, run_id, effects):
            asked.append((scope, run_id))
            return SAVED
        context, binding = SimpleNamespace(scope='scope-a'), SimpleNamespace(run_id='run-1')
        self.assertIsNone(_receipt(reader, context, binding, state('completed', 'x', SPLIT)))
        self.assertEqual(asked, [])
        self.assertEqual(_receipt(reader, context, binding, state('completed', 'x', 'lio_trip_receipt:{"x":1}')), SAVED)
        self.assertEqual(asked, [('scope-a', 'run-1')])
        self.assertIsNone(_receipt(None, context, binding, state('completed', 'x', 'lio_trip_receipt:{}')))
        self.assertIsNone(_receipt(reader, context, binding, None))

    def test_a_failing_reader_never_fails_the_page(self):
        from cj_api.lio_dialogue_routes import _receipt

        def broken(*args):
            raise RuntimeError('database unavailable')
        self.assertIsNone(_receipt(broken, SimpleNamespace(scope='s'), SimpleNamespace(run_id='r'), state('completed', 'x', 'lio_trip_receipt:{}')))


if __name__ == '__main__':
    unittest.main()
