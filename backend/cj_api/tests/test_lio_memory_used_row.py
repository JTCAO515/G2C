"""`rich.memory.used` on the timeline row (#2001, M-3): ids at write, titles read now, nothing for what was taken back."""
import json
import os
from types import SimpleNamespace
import unittest
from unittest import mock

from cj_api.lio_dialogue_routes import RICH_VERSION, _message, _used_titles
from cj_api.lio_memory_routes import LioMemoryCards
from cj_message.lio_context import LioLayout

SPLIT = LioLayout('split').effect()


def effect(ids, total=None):
    return 'lio_memory_used:' + json.dumps(dict(item_ids=ids, total=len(ids) if total is None else total), separators=(',', ':'))


def item():
    return SimpleNamespace(message_id='m1', text='推荐几家酒店', locale='zh')


def state(*effects):
    return SimpleNamespace(status='completed', text='好的。\n\n推荐这几家。', effects=tuple(effects), draft_outcome=None, budget_exhausted_stage='none')


class Row(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {'CJ_LIO_ANSWER_RICH': 'on'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def row(self, titles, *effects, declared='rich'):
        calls = []

        def lookup(ids):
            calls.append(list(ids))
            return titles
        row = _message(item(), state(SPLIT, *effects), declared=declared, used_titles=lookup)
        row['_calls'] = calls
        return row

    def test_the_titles_come_from_the_lookup_in_the_stored_order(self):
        row = self.row({'a': '节奏慢', 'b': 'Quiet hotels'}, effect(['a', 'b']))
        self.assertEqual(row['rich'], dict(version=RICH_VERSION, memory=dict(used=[dict(item_id='a', title='节奏慢'), dict(item_id='b', title='Quiet hotels')], used_total=2)))
        self.assertEqual(row['_calls'], [['a', 'b']])

    def test_what_was_taken_back_is_not_shown_and_the_count_never_claims_more(self):
        row = self.row({'a': '节奏慢'}, effect(['a', 'b', 'c'], total=5))
        self.assertEqual(row['rich']['memory'], dict(used=[dict(item_id='a', title='节奏慢')], used_total=1))
        self.assertNotIn('rich', self.row({}, effect(['a', 'b'])))                  # all gone: no `used`
        full = self.row({'a': 'x1', 'b': 'x2', 'c': 'x3'}, effect(['a', 'b', 'c'], total=7))
        self.assertEqual(full['rich']['memory']['used_total'], 7)                    # the account really had seven in play

    def test_never_for_a_poll_that_did_not_declare_rich_and_the_lookup_is_not_asked(self):
        for declared in (False, True):
            row = self.row({'a': 'x1'}, effect(['a']), declared=declared)
            self.assertNotIn('rich', row)
            self.assertEqual(row['_calls'], [])
        with mock.patch.dict(os.environ, {'CJ_LIO_ANSWER_RICH': 'off'}):
            self.assertEqual(self.row({'a': 'x1'}, effect(['a']))['_calls'], [])

    def test_a_damaged_record_gives_no_used_and_no_lookup(self):
        for bad in ('lio_memory_used:', 'lio_memory_used:x', 'lio_memory_used:{}', effect(['a b']), effect([])):
            row = self.row({'a': 'x1'}, bad)
            self.assertNotIn('rich', row, bad)

    def test_a_failing_lookup_is_no_titles(self):
        def broken(*args):
            raise RuntimeError('memory unavailable')
        cards = SimpleNamespace(used_titles=broken, used_allowed=lambda scope: True)
        self.assertEqual(_used_titles(cards, SimpleNamespace(scope='s'))(['a']), {})
        self.assertEqual(_used_titles(SimpleNamespace(), SimpleNamespace(scope='s'))(['a']), {})

    def test_a_title_that_breaks_the_contract_never_reaches_the_row(self):
        # the lookup is the memory module's; the row still holds the line on shape and length
        row = self.row({'a': 'x' * 41}, effect(['a']))
        self.assertNotIn('rich', row)


class Consent(unittest.TestCase):
    def cards(self, granted, reader):
        class Store:
            def granted(self, scope):
                return granted
        return LioMemoryCards(SimpleNamespace(titles=reader), None, Store())

    def test_with_the_consent_switch_on_an_account_that_is_not_granted_gets_nothing(self):
        calls = []
        reader = lambda scope, ids: calls.append(ids) or {'a': 'x1'}
        with mock.patch.dict(os.environ, {'CJ_LIO_MEMORY_CONSENT_REQUIRED': '1'}):
            self.assertEqual(self.cards(False, reader).used_titles('s', ['a']), {})
            self.assertEqual(calls, [])
            self.assertEqual(self.cards(True, reader).used_titles('s', ['a']), {'a': 'x1'})
        with mock.patch.dict(os.environ, {'CJ_LIO_MEMORY_CONSENT_REQUIRED': '0'}):
            self.assertEqual(self.cards(False, reader).used_titles('s', ['a']), {'a': 'x1'})

    def test_the_consent_state_is_read_once_per_page(self):
        reads = []

        class Store:
            def granted(self, scope):
                reads.append(scope)
                return True
        cards = LioMemoryCards(SimpleNamespace(titles=lambda scope, ids: {i: 'x1' for i in ids}), None, Store())
        with mock.patch.dict(os.environ, {'CJ_LIO_MEMORY_CONSENT_REQUIRED': '1'}):
            lookup = _used_titles(cards, SimpleNamespace(scope='s'))
            self.assertEqual(lookup(['a']), {'a': 'x1'})
            self.assertEqual(lookup(['b']), {'b': 'x1'})
            self.assertEqual(lookup(['c']), {'c': 'x1'})
        self.assertEqual(reads, ['s'])

    def test_no_reader_mounted_is_no_titles(self):
        self.assertEqual(LioMemoryCards(SimpleNamespace(), None, None).used_titles('s', ['a']), {})


if __name__ == '__main__':
    unittest.main()
