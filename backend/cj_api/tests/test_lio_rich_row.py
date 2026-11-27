"""A timeline row for a poll that declared LIO-answer-rich.1 (#1984, #1989): accepts rules, rows that stay as they were,
and `rich.entities` once the switches are on."""
import json
import os
from types import SimpleNamespace
import unittest
from unittest import mock

from cj_api.lio_dialogue_routes import RICH_VERSION, _message
from cj_message import lio_cards, lio_entities as ent
from cj_message.lio_followups import Destination
from cj_message.lio_context import LioFollowups, LioLayout
from cj_message.lio_followups import VERSION as FOLLOWUPS_VERSION
from test_lio_entities import APPROVED, DOC

ANSWER = '上午去**故宫**，下午去景山公园看全景😀。\n\n晚上可以去王府井走走。'
SPLIT = LioLayout('split').effect()
CHIPS = LioFollowups(dict(actions=[dict(tool='payment-guide', parameters={}, label='打开支付开通指南')], chips=[], issued_at=1_800_000_000)).effect()


def item():
    return SimpleNamespace(message_id='m1', text='北京怎么玩', locale='zh')


def state(text, *effects, status='completed'):
    return SimpleNamespace(status=status, text=text, effects=tuple(effects), draft_outcome=None, budget_exhausted_stage='none')


def stored(answer=ANSWER):
    return ent.effect(answer, ent.link(ent.display_text(answer) if hasattr(ent, 'display_text') else answer, [DOC]))


def row(declared, *effects, text=ANSWER):
    return _message(item(), state(text, *effects), declared=declared)


TAXI_BUTTON = dict(tool='taxi', parameters={}, label='打车')
PAY_BUTTON = dict(tool='payment-guide', parameters={}, label='打开支付开通指南')
PALACE = Destination('故宫博物院', '116.397026,39.918058', '景山前街4号', 'The Palace Museum')


def buttons(*actions, chips=()):
    import time
    return LioFollowups(dict(actions=list(actions), chips=list(chips), issued_at=int(time.time()))).effect()


class Cards(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {'CJ_LIO_ANSWER_RICH': 'on'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.metro = lio_cards.effect(lio_cards.build('北京地铁', 'zh', library_city='beijing'), 1)
        self.taxi = lio_cards.effect(lio_cards.build('打车去故宫', 'zh', destination=PALACE, taxi_topic=True), 1)

    def test_cards_ride_in_rich_for_a_declared_poll_only(self):
        rich = row('rich', SPLIT, self.metro, CHIPS)['rich']
        self.assertEqual([c['type'] for c in rich['cards']], ['metro'])
        self.assertNotIn('rich', row(True, SPLIT, self.metro, CHIPS))
        self.assertNotIn('rich', row(False, SPLIT, self.metro, CHIPS))
        self.assertEqual(row(True, SPLIT, self.metro, CHIPS), row(True, SPLIT, CHIPS))

    def test_a_taxi_card_replaces_the_taxi_button_and_nothing_else_changes(self):
        both = buttons(TAXI_BUTTON, PAY_BUTTON)
        rich_row = row('rich', SPLIT, self.taxi, both)
        self.assertEqual([c['type'] for c in rich_row['rich']['cards']], ['taxi'])
        self.assertEqual([a['tool'] for a in rich_row['followups']['actions']], ['payment-guide'])
        self.assertEqual([a['tool'] for a in row(True, SPLIT, both)['followups']['actions']], ['taxi', 'payment-guide'])   # followups.1 row
        only = row('rich', SPLIT, self.taxi, buttons(TAXI_BUTTON))
        self.assertNotIn('followups', only)                       # the taxi button was all there was
        with_chip = row('rich', SPLIT, self.taxi, buttons(TAXI_BUTTON, chips=[dict(label='打车怎么付款', ticket='a' * 43)]))
        self.assertEqual(with_chip['followups'], dict(version='LIO-answer-followups.1', chips=[dict(label='打车怎么付款', ticket='a' * 43)]))

    def test_a_row_with_a_trip_card_carries_no_tool_cards(self):
        planned = _message(item(), state(ANSWER, SPLIT, self.metro, CHIPS), trip={'trip_id': 'trip:a'}, declared='rich')
        self.assertNotIn('rich', planned)

    def test_entities_and_cards_together_and_bad_card_records(self):
        os.environ.update(CJ_LIO_ENTITIES='on')
        with mock.patch.object(ent, 'approved_ids', lambda: frozenset(APPROVED)):
            both = row('rich', SPLIT, ent.effect(ANSWER, ent.link(ANSWER, [DOC])), self.metro, CHIPS)['rich']
        self.assertEqual(sorted(k for k in both if k != 'version'), ['cards', 'entities'])
        for bad in ('lio_cards:oops', 'lio_cards:{}', 'lio_cards:null'):
            self.assertNotIn('rich', row('rich', SPLIT, bad, CHIPS))


class Rows(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ('CJ_LIO_ENTITIES', 'CJ_LIO_ANSWER_RICH'):
            os.environ.pop(name, None)
        library = mock.patch.object(ent, 'approved_ids', lambda: frozenset(APPROVED))
        library.start()
        self.addCleanup(library.stop)
        # the row's visible answer is display_answer(text): for this text it is the text itself
        self.effect = ent.effect(ANSWER, ent.link(ANSWER, [DOC]))

    def test_undeclared_and_followups_rows_are_byte_for_byte_the_old_ones(self):
        os.environ.update(CJ_LIO_ENTITIES='on', CJ_LIO_ANSWER_RICH='on')
        for declared in (False, True):
            self.assertNotIn('rich', row(declared, SPLIT, self.effect, CHIPS))
        self.assertEqual(row(False, SPLIT, self.effect, CHIPS), row(False, SPLIT, CHIPS))
        self.assertEqual(row(True, SPLIT, self.effect, CHIPS), row(True, SPLIT, CHIPS))

    def test_with_the_rich_switch_off_a_rich_declaration_reads_exactly_like_followups(self):
        os.environ['CJ_LIO_ENTITIES'] = 'on'
        self.assertEqual(row('rich', SPLIT, self.effect, CHIPS), row(True, SPLIT, self.effect, CHIPS))

    def test_with_both_switches_on_the_row_carries_the_entities(self):
        os.environ.update(CJ_LIO_ENTITIES='on', CJ_LIO_ANSWER_RICH='on')
        rich = row('rich', SPLIT, self.effect, CHIPS)['rich']
        self.assertEqual(rich['version'], RICH_VERSION)
        self.assertEqual([(ANSWER[e['start']:e['end']], e['place_id']) for e in rich['entities']],
                         [('故宫', 'pl_bj_gugong'), ('景山公园', 'pl_bj_jingshan'), ('王府井', 'pl_bj_wangfujing')])
        # the followups of a rich row are the followups.1 row's
        self.assertEqual(row('rich', SPLIT, self.effect, CHIPS)['followups'], row(True, SPLIT, CHIPS)['followups'])
        self.assertEqual(row('rich', SPLIT, self.effect, CHIPS)['layout'], 'split')

    def test_rich_only_on_a_completed_row_with_an_answer(self):
        os.environ.update(CJ_LIO_ENTITIES='on', CJ_LIO_ANSWER_RICH='on')
        self.assertNotIn('rich', _message(item(), state(ANSWER, SPLIT, self.effect, status='running'), declared='rich'))
        self.assertNotIn('rich', _message(item(), None, declared='rich'))
        self.assertNotIn('rich', _message(item(), state('', SPLIT, self.effect), declared='rich'))

    def test_a_changed_answer_a_withdrawn_place_or_a_bad_record_leaves_rich_out_and_the_row_intact(self):
        os.environ.update(CJ_LIO_ENTITIES='on', CJ_LIO_ANSWER_RICH='on')
        plain = row(True, SPLIT, CHIPS, text=ANSWER + '补充')
        changed = row('rich', SPLIT, self.effect, CHIPS, text=ANSWER + '补充')
        self.assertNotIn('rich', changed)
        self.assertEqual({k: v for k, v in changed.items()}, plain)
        for bad in ('lio_entities:oops', 'lio_entities:{}', 'lio_entities:null'):
            self.assertNotIn('rich', row('rich', SPLIT, bad, CHIPS))
        with mock.patch.object(ent, 'approved_ids', lambda: frozenset()):
            self.assertNotIn('rich', row('rich', SPLIT, self.effect, CHIPS))

    def test_a_broken_switch_value_or_library_read_never_fails_the_row(self):
        os.environ['CJ_LIO_ANSWER_RICH'] = 'maybe'
        self.assertNotIn('rich', row('rich', SPLIT, self.effect, CHIPS))
        os.environ['CJ_LIO_ANSWER_RICH'] = 'on'
        with mock.patch.object(ent, 'approved_ids', side_effect=RuntimeError('library unreadable')):
            self.assertNotIn('rich', row('rich', SPLIT, self.effect, CHIPS))

    def test_the_last_entities_effect_counts(self):
        os.environ.update(CJ_LIO_ENTITIES='on', CJ_LIO_ANSWER_RICH='on')
        empty = ent.effect(ANSWER, [])
        self.assertEqual(len(row('rich', SPLIT, empty, self.effect)['rich']['entities']), 3)
        self.assertNotIn('rich', row('rich', SPLIT, self.effect, empty))


def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from cj_api.lio_dialogue_routes import register_lio_dialogue_routes
    page = SimpleNamespace(messages=(), conversation_id='lio-c', next_before=None, requires_new_lio=False)
    context = SimpleNamespace(scope='scope', lio_timeline=lambda *args, **kwargs: page)
    boundary = SimpleNamespace(with_history_context=lambda token, project: project(context))
    app = FastAPI()
    register_lio_dialogue_routes(app, boundary, None, None, prepare_scope=None)
    return TestClient(app)


class Accepts(unittest.TestCase):
    def test_the_two_values_are_accepted_and_every_other_form_is_a_400(self):
        http, headers = client(), {'Authorization': 'Bearer t'}
        base = http.get('/v2/lio/timeline', headers=headers)
        for value in (FOLLOWUPS_VERSION, RICH_VERSION):
            ok = http.get('/v2/lio/timeline?accepts=' + value, headers=headers)
            self.assertEqual((ok.status_code, ok.json()), (200, base.json()))
        for query in ('accepts=', 'accepts=LIO-answer-rich.2', 'accepts=lio-answer-rich.1', 'accepts=LIO-answer-rich.1+',
                      'accepts=LIO-answer-rich.1%20', 'accepts=LIO-answer-rich', 'accepts=' + FOLLOWUPS_VERSION + ',' + RICH_VERSION,
                      'accepts=' + FOLLOWUPS_VERSION + '%2C' + RICH_VERSION, 'accepts=' + RICH_VERSION + '&accepts=' + RICH_VERSION,
                      'accepts=' + RICH_VERSION + '&accepts=' + FOLLOWUPS_VERSION, 'accept=' + RICH_VERSION):
            self.assertEqual(http.get('/v2/lio/timeline?' + query, headers=headers).status_code, 400, query)
        for path in ('/v1/lio/timeline', '/v3/lio/timeline'):
            self.assertEqual(http.get(path + '?accepts=' + RICH_VERSION, headers=headers).status_code in (400, 404), True, path)


if __name__ == '__main__':
    unittest.main()
