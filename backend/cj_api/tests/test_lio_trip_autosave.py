"""#1994 T-1 part 2: the CJ_LIO_TRIP_AUTOSAVE switch, the lio_trip_receipt: effect and its writer."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cj_agent.draft import DraftRejected
from cj_agent.trip_autosave import publish, reason
from cj_api.lio_trip_autosave import autosave_for, autosave_mode, autosave_subjects, undo_sources
from cj_api.lio_trip_receipt import read, undo_action_id
from cj_api.local_app import ISSUER, scope_for
from cj_message.lio_trip_receipt import EFFECT, MAX_EFFECT_BYTES, effect, last, parse
from cj_trip.autosave import AutosaveConflict
from cj_trip.domain import Conflict, Denied, Receipt
from cj_trip.structured import SourceRejected

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'contracts/message'))
import check_lio_answer_rich as rich_check  # noqa: E402

ON = 'm4-synthetic-demo-aaaaaaaaaaaa'
OTHER = 'm4-synthetic-demo-bbbbbbbbbbbb'
NAMES = ('CJ_LIO_TRIP_AUTOSAVE', 'CJ_LIO_TRIP_AUTOSAVE_SUBJECTS_JSON', 'CJ_LIO_ANSWER_LAYOUT', 'CJ_LIO_ANSWER_LAYOUT_SUBJECTS_JSON')
LISTED = dict(CJ_LIO_TRIP_AUTOSAVE_SUBJECTS_JSON=json.dumps([ON]))
LAYOUT_ONLY = dict(CJ_LIO_ANSWER_LAYOUT='one-screen', CJ_LIO_ANSWER_LAYOUT_SUBJECTS_JSON=json.dumps([ON]))


def environment(**values):
    base = {k: v for k, v in os.environ.items() if k not in NAMES}
    return patch.dict(os.environ, dict(base, **values), clear=True)


class Switch(unittest.TestCase):
    def test_defaults_off_and_names_only_listed_accounts(self):
        with environment():
            self.assertEqual((autosave_mode(), autosave_subjects()), ('off', frozenset()))
            self.assertIsNone(autosave_for(scope_for(ISSUER, ON)))
            self.assertIsNone(undo_sources(object(), None))   # off: the host registers no v4 undo route
        with environment(**LISTED):
            self.assertIsNone(autosave_for(scope_for(ISSUER, ON)))   # the list alone does nothing
        with environment(CJ_LIO_TRIP_AUTOSAVE='on', **LISTED):
            self.assertIs(autosave_for(scope_for(ISSUER, ON)), True)
            self.assertIsNone(autosave_for(scope_for(ISSUER, OTHER)))
        # #2127: the list is the autosave list alone; the layout switch and the layout list have nothing to do with it.
        with environment(CJ_LIO_TRIP_AUTOSAVE='on', CJ_LIO_ANSWER_LAYOUT='flat', **LISTED):
            self.assertIs(autosave_for(scope_for(ISSUER, ON)), True)

    def test_an_account_on_the_layout_list_only_gets_no_autosave(self):
        # The case of 58.1 batch 1: a real person goes on the one-screen layout list, autosave stays closed for them.
        with environment(CJ_LIO_TRIP_AUTOSAVE='on', **LAYOUT_ONLY):
            self.assertEqual(autosave_subjects(), frozenset())
            self.assertIsNone(autosave_for(scope_for(ISSUER, ON)))
        with environment(CJ_LIO_TRIP_AUTOSAVE='on', CJ_LIO_TRIP_AUTOSAVE_SUBJECTS_JSON=json.dumps([OTHER]), **LAYOUT_ONLY):
            self.assertIsNone(autosave_for(scope_for(ISSUER, ON)))           # on the layout list, not on the autosave list
            self.assertIs(autosave_for(scope_for(ISSUER, OTHER)), True)      # the other way round

    def test_not_set_or_empty_closes_autosave_for_everybody_without_noise(self):
        for raw in (None, '', '   ', '[]'):
            with self.subTest(raw=raw), environment(CJ_LIO_TRIP_AUTOSAVE='on', **({} if raw is None else dict(CJ_LIO_TRIP_AUTOSAVE_SUBJECTS_JSON=raw))):
                self.assertEqual(autosave_subjects(), frozenset())
                self.assertIsNone(autosave_for(scope_for(ISSUER, ON)))

    def test_the_undo_routes_answer_only_the_accounts_on_the_autosave_list(self):
        from cj_api.lio_rich_undo_routes import _admitted
        from cj_trip.domain import Denied

        def context(subject):
            return SimpleNamespace(metadata=SimpleNamespace(principal=SimpleNamespace(issuer=ISSUER, subject=subject)))
        with environment(CJ_LIO_TRIP_AUTOSAVE='on', CJ_LIO_TRIP_AUTOSAVE_SUBJECTS_JSON=json.dumps([ON]), **LAYOUT_ONLY):
            _admitted(context(ON))                                           # on the autosave list: admitted
            with self.assertRaises(Denied):
                _admitted(context(OTHER))
        with environment(CJ_LIO_TRIP_AUTOSAVE='on', **LAYOUT_ONLY):          # layout list only: no undo route for the scope
            with self.assertRaises(Denied):
                _admitted(context(ON))

    def test_any_other_switch_value_is_off_with_an_audit_line(self):
        for value in ('ON', '1', 'true', ' on', 'on ', ''):
            with self.subTest(value=value), environment(CJ_LIO_TRIP_AUTOSAVE=value, **LISTED), \
                    self.assertLogs('cj_usage.audit', 'WARNING') as logs:
                self.assertEqual(autosave_mode(), 'off')
                self.assertIsNone(autosave_for(scope_for(ISSUER, ON)))
                self.assertIn('LIO_TRIP_AUTOSAVE_INVALID', logs.output[0])

    def test_an_unusable_account_list_is_off_not_an_error(self):
        for subjects in ('not json', '{}', '"x"', '["x"]', '[1]', '[null]', json.dumps([ON, ON]), json.dumps([ON, 'x'])):
            with self.subTest(subjects=subjects), \
                    environment(CJ_LIO_TRIP_AUTOSAVE='on', CJ_LIO_TRIP_AUTOSAVE_SUBJECTS_JSON=subjects), \
                    self.assertLogs('cj_usage.audit', 'WARNING') as logs:
                self.assertIsNone(autosave_for(scope_for(ISSUER, ON)))
                self.assertEqual(autosave_subjects(), frozenset())
                self.assertIn('LIO_TRIP_AUTOSAVE_SUBJECTS_INVALID', logs.output[0])


class Effect(unittest.TestCase):
    def test_bytes_parse_and_last_valid_wins(self):
        intent, saved = effect('lio-plan-r1', 'unknown'), effect('lio-plan-r1', 'saved')
        self.assertEqual(intent, EFFECT + '{"action_id":"lio-plan-r1","status":"unknown"}')
        refused = effect('lio-edit-r1', 'not_saved', 'protected')
        self.assertEqual(refused, EFFECT + '{"action_id":"lio-edit-r1","reason":"protected","status":"not_saved"}')
        self.assertEqual(parse(refused), dict(action_id='lio-edit-r1', status='not_saved', reason='protected'))
        self.assertEqual(last(['lio_layout:split', intent, saved, 'lio_followups:{}']),
                         dict(action_id='lio-plan-r1', status='saved'))
        for bad in (EFFECT + '{"status":"saved","action_id":"lio-plan-r1"}',
                    EFFECT + '{"action_id":"lio-plan-r1","status":"done"}',
                    EFFECT + '{"action_id":"lio-plan-r1","reason":"protected","status":"saved"}', EFFECT + 'nope',
                    EFFECT + '{"action_id":"-x","status":"saved"}', EFFECT + '{"action_id":"a","extra":1,"status":"saved"}'):
            self.assertIsNone(parse(bad))
            self.assertEqual(last([intent, bad]), dict(action_id='lio-plan-r1', status='unknown'))
        for args in (('lio-plan-r1', 'saved', 'protected'), ('lio-plan-r1', 'not_saved', 'off'), ('x' * 129, 'saved'),
                     ('lio plan', 'saved'), ('lio-plan-r1', 'pending')):
            with self.assertRaises(ValueError):
                effect(*args)
        self.assertLess(len(effect('a' * 128, 'not_saved', 'too_large').encode()), MAX_EFFECT_BYTES)

    def test_refusal_reasons_follow_the_cause_chain(self):
        def wrapped(cause):
            try:
                try:
                    raise cause
                except Exception as error:
                    raise DraftRejected('Lio Trip publication refused') from error
            except DraftRejected as outer:
                return outer
        self.assertEqual(reason(wrapped(Conflict('trip version conflict'))), 'conflict')
        for code in ('user_item_changed', 'user_order_changed', 'tombstone_readded'):
            self.assertEqual(reason(wrapped(AutosaveConflict(code))), 'protected')
        self.assertEqual(reason(wrapped(AutosaveConflict('too_large'))), 'too_large')
        self.assertIsNone(reason(wrapped(Conflict('candidate not eligible'))))
        self.assertIsNone(reason(DraftRejected('explicit Trip time conflict')))

    def test_undo_action_id_matches_the_contract_checker_and_no_effect_reads_nothing(self):
        for action_id in ('lio-plan-r1', 'lio-edit-' + 'x' * 100):
            self.assertEqual(undo_action_id(action_id), rich_check.undo_action_id(action_id))

        class NoDatabase:
            def connect(self, scope):
                raise AssertionError('no receipt effect, no database read')
        self.assertIsNone(read(NoDatabase(), 'scope', 'r1', ['lio_layout:split', 'trip_proposal:p'], undo_route=True))


class Worker:
    def __init__(self, fail=False):
        self.events, self.fail = [], fail
        self.runs = SimpleNamespace(snapshot=lambda binding: SimpleNamespace(sequence=len(self.events)))

    def _event(self, binding, state, kind, value):
        if self.fail:
            raise Conflict('state changed')
        assert kind == 'effect_committed' and state.sequence == len(self.events)
        self.events.append(value)
        return SimpleNamespace(sequence=len(self.events))


BINDING = SimpleNamespace(run_id='r1')
RECEIPT = Receipt('lio-plan-r1', 'accept', 'p', 'h', 'trip-r1', 1)
ON_REPO, OFF_REPO = SimpleNamespace(autosave=True), SimpleNamespace(autosave=None)


def raising(error):
    def step():
        raise error
    return step


class Writer(unittest.TestCase):
    def test_switch_off_is_exactly_the_step(self):
        worker, sentinel = Worker(), object()
        self.assertEqual(publish(worker, BINDING, OFF_REPO, 'lio-plan-r1', lambda: ('state', sentinel)), ('state', sentinel))
        self.assertEqual(publish(worker, BINDING, None, 'lio-plan-r1', lambda: ('state', sentinel)), ('state', sentinel))
        self.assertEqual(worker.events, [])

    def test_switch_on_brackets_the_step_with_intent_and_result(self):
        worker = Worker()

        def step():
            self.assertEqual(worker.events, [effect('lio-plan-r1', 'unknown')])   # committed before the Trip write
            worker.events.append('trip_proposal:p')
            return SimpleNamespace(sequence=len(worker.events)), RECEIPT
        state, result = publish(worker, BINDING, ON_REPO, 'lio-plan-r1', step)
        self.assertEqual((result, state.sequence), (RECEIPT, 3))
        self.assertEqual(worker.events, [effect('lio-plan-r1', 'unknown'), 'trip_proposal:p', effect('lio-plan-r1', 'saved')])

    def test_a_step_that_wrote_no_trip_is_not_saved(self):
        # #2051 P2-3: `saved` needs this action's accepted receipt with a committed version.
        for result in ('receipt', None, Receipt('lio-plan-r1', 'reject', 'p', 'h', 't', None),
                       Receipt('lio-plan-r9', 'accept', 'p', 'h', 't', 2), SimpleNamespace(proposal_id='p')):
            with self.subTest(result=result):
                worker = Worker()
                with self.assertLogs('cj_usage.audit', 'INFO') as logs:
                    _, returned = publish(worker, BINDING, ON_REPO, 'lio-plan-r1', lambda: (SimpleNamespace(sequence=1), result))
                self.assertIs(returned, result)
                self.assertEqual(worker.events, [effect('lio-plan-r1', 'unknown'), effect('lio-plan-r1', 'not_saved')])
                self.assertIn('LIO_TRIP_RECEIPT_NOT_WRITTEN', logs.output[0])

    def test_a_refused_write_is_not_saved_and_still_raises(self):
        for error, expected in ((AutosaveConflict('user_item_changed'), effect('lio-edit-r1', 'not_saved', 'protected')),
                                (Conflict('trip version conflict'), effect('lio-edit-r1', 'not_saved', 'conflict')),
                                (AutosaveConflict('too_large'), effect('lio-edit-r1', 'not_saved', 'too_large')),
                                (Denied('trusted review and confirmation unavailable'), effect('lio-edit-r1', 'not_saved'))):
            with self.subTest(error=error):
                worker = Worker()
                rejected = DraftRejected('Lio Trip publication refused')
                rejected.__cause__ = error
                with self.assertRaises(DraftRejected):
                    publish(worker, BINDING, ON_REPO, 'lio-edit-r1', raising(rejected))
                self.assertEqual(worker.events, [effect('lio-edit-r1', 'unknown'), expected])
        worker = Worker()
        with self.assertRaises(SourceRejected):
            publish(worker, BINDING, ON_REPO, 'lio-plan-r1', raising(SourceRejected('items', 'x')))
        self.assertEqual(worker.events, [effect('lio-plan-r1', 'unknown'), effect('lio-plan-r1', 'not_saved')])

    def test_an_unknown_commit_keeps_the_intent_and_a_failed_receipt_write_never_fails_the_answer(self):
        class Unknown(Exception):
            pass
        worker = Worker()
        with self.assertRaises(Unknown):
            publish(worker, BINDING, ON_REPO, 'lio-plan-r1', raising(Unknown()))
        self.assertEqual(worker.events, [effect('lio-plan-r1', 'unknown')])
        worker = Worker(fail=True)
        with self.assertLogs('cj_usage.audit', 'INFO') as logs:
            state, result = publish(worker, BINDING, ON_REPO, 'lio-plan-r1', lambda: ('after', RECEIPT))
        self.assertEqual((result, state.sequence), (RECEIPT, 0))
        self.assertIn('LIO_TRIP_RECEIPT_UNAVAILABLE', logs.output[0])


class Withdrawal(unittest.TestCase):
    """#1994 part 3: LIO-trip-undo.5 beside LIO-trip-undo.4 on the same v4 routes (ADR-0012 revision 1)."""
    TARGET = dict(trip_id='trip-r1', expected_version=1, original_hash='a' * 64, content_version='structured.4')
    RESTORE = dict(TARGET, expected_version=2, restore_version=1, restore_hash='b' * 64, restore_content_version='structured.4')

    def body(self, version, target):
        return dict(version=version, action_id=undo_action_id('lio-plan-r1'), conversation_id='lio-dialogue-' + 'a' * 32,
                    target=target)

    def test_version_tells_the_two_requests_apart(self):
        from cj_api.lio_rich_undo_routes import _original
        from cj_trip.rich_undo import RichUndo
        from cj_trip.withdrawal import Withdraw
        withdraw, _, target = _original(self.body('LIO-trip-undo.5', self.TARGET))
        self.assertIsInstance(withdraw, Withdraw)
        self.assertEqual((withdraw.trip_id, withdraw.expected_version, withdraw.content_version, target),
                         ('trip-r1', 1, 'structured.4', self.TARGET))
        restore, _, _ = _original(self.body('LIO-trip-undo.4', self.RESTORE))
        self.assertIsInstance(restore, RichUndo)
        for version, target in (('LIO-trip-undo.5', self.RESTORE), ('LIO-trip-undo.5', dict(self.TARGET, expected_version=2)),
                                ('LIO-trip-undo.5', dict(self.TARGET, content_version='structured.9')),
                                ('LIO-trip-undo.5', {k: v for k, v in self.TARGET.items() if k != 'original_hash'}),
                                ('LIO-trip-undo.4', self.TARGET), ('LIO-trip-undo.6', self.TARGET)):
            with self.subTest(version=version, target=target), self.assertRaises(ValueError):
                _original(self.body(version, target))

    def test_private_input_is_canonical_and_only_version_one(self):
        from cj_trip.withdrawal import Withdraw
        built = Withdraw.build('undo-x', 'trip-r1', 1, 'a' * 64, 'structured.2')
        self.assertEqual(Withdraw.parse(built.raw), built)
        for raw in (built.raw.replace(b'"expected_version":1', b'"expected_version":2'), built.raw + b' ',
                    built.raw.replace(b'TRIP-lio-withdraw.1', b'TRIP-lio-undo.3')):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                Withdraw.parse(raw)

    def test_a_withdrawn_trip_reads_as_a_conflict(self):
        from cj_trip.autosave import UNDO_BASES, WITHDRAW_BASIS, WithdrawnConflict, writer
        self.assertEqual(reason(WithdrawnConflict()), 'conflict')
        self.assertIn(WITHDRAW_BASIS, UNDO_BASES)
        self.assertEqual(writer(WITHDRAW_BASIS), 'undo')


class LegacyContentVersions(unittest.TestCase):
    """#2051 P2-2: which content versions the v4 undo serves; the rest read `unavailable`, never `available`."""

    def test_structured_1_is_refused_by_the_legacy_undo_and_reads_unavailable(self):
        from cj_api.lio_trip_receipt import _RESTORABLE
        from cj_trip.lio_history import _protect_fixed
        one = SimpleNamespace(content=json.dumps(dict(content_version='structured.1', items=[], sources=[])).encode())
        two = SimpleNamespace(content=json.dumps(dict(content_version='structured.2', items=[], sources=[])).encode())
        for current, previous in ((one, one), (two, one), (one, two)):
            with self.subTest(current=current, previous=previous), self.assertRaises(Denied):
                _protect_fixed(current, previous)
        _protect_fixed(two, two)
        for pair in (('structured.1', 'structured.1'), ('structured.2', 'structured.1'), ('structured.2', 'structured.3'),
                     ('structured.3', 'structured.2'), ('structured.4', 'structured.2')):
            self.assertNotIn(pair, _RESTORABLE)
        for pair in (('structured.2', 'structured.2'), ('structured.3', 'structured.3'), ('structured.4', 'structured.3'),
                     ('structured.3', 'structured.4'), ('structured.4', 'structured.4')):
            self.assertIn(pair, _RESTORABLE)


class Wiring(unittest.TestCase):
    """#1994 part 3: the timeline gets the receipt reader only while the switch is on (#2055 signature)."""

    def test_reader_only_with_the_switch_and_undo_route_per_account(self):
        from cj_api.local_app import _trip_receipt_reader
        with environment(**LISTED):
            self.assertIsNone(_trip_receipt_reader(object(), True))
        calls = []
        with environment(CJ_LIO_TRIP_AUTOSAVE='on', **LISTED), \
                patch('cj_api.lio_trip_receipt.read', side_effect=lambda *a, **k: calls.append((a[1:], k)) or 'r'):
            reader = _trip_receipt_reader('db', True)
            self.assertEqual(reader(scope_for(ISSUER, ON), 'run-1', ('e',)), 'r')
            reader(scope_for(ISSUER, OTHER), 'run-2', ())
            _trip_receipt_reader('db', False)(scope_for(ISSUER, ON), 'run-3', ())
        self.assertEqual([k['undo_route'] for _, k in calls], [True, False, False])
        self.assertEqual(calls[0][0], (scope_for(ISSUER, ON), 'run-1', ('e',)))


if __name__ == '__main__':
    unittest.main()
