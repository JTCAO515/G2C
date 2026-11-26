"""W2-4 (#1731): entry answers come from the App's arrival rules; nationality only from the traveler."""
from datetime import date
import logging
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cj_api.lio_entry_rules import entry_question, entry_reply, entry_rules_enabled, entry_turn, stated_nationality
from cj_fact.arrival import load_rules, review_due
from cj_fact.policy import FactFailure

RULES = load_rules()
TODAY = date.fromisoformat(RULES['checked_at'])


class Detection(unittest.TestCase):
    def test_entry_questions_and_plan_requests(self):
        for text, kind in (('我需要签证吗？', 'visa'), ('美国人入境中国要办签证吗', 'visa'), ('过境北京能免签吗', 'visa'),
                           ('Do I need a visa for China?', 'visa'), ('I have a layover in Shanghai', None), ('I have a layover in Shanghai, do I need a visa?', 'visa'),
                           ('入境卡怎么填？', 'card'), ('How do I fill in the arrival card?', 'card'),
                           ('去北京玩3天需要签证吗', None), ('Plan 3 days in Beijing, do I need a visa?', None),
                           ('故宫门票多少钱', None), ('Where can I buy a SIM card?', None),
                           # Review of #1856: card payments, public transport and post-arrival travel are not entry questions.
                           ('Can I pay with Visa?', None), ('Do you accept Visa or Mastercard?', None),
                           ('Public transit in Beijing?', None), ('After entering China how do I get to the city?', None),
                           ('北京地铁换乘', None), ('入境需要什么', 'visa'), ('转机需要签证吗', 'visa'),
                           ('I have a layover in Shanghai, can I leave the airport?', 'visa'),
                           ('Do I need a visa to enter China?', 'visa'), ('Can I get a visa on arrival?', 'visa')):
            with self.subTest(text=text):
                self.assertEqual(entry_question(text), kind)

    def test_nationality_only_from_an_explicit_statement(self):
        for text, expected in (('我是美国人', ('rules', 'US')), ('持英国护照', ('rules', 'GB')), ('我拿的是日本护照', ('rules', 'JP')),
                               ('我来自澳大利亚的悉尼', ('rules', 'AU')), ('我们是韩国人', ('rules', 'KR')),
                               ('I am American', ('rules', 'US')), ('I hold a U.S. passport', ('rules', 'US')),
                               ('We are Australians', ('rules', 'AU')), ('we are from New Zealand', ('rules', 'NZ')),
                               ('My passport is Japanese', ('rules', 'JP')), ('German citizen', ('rules', 'DE')),
                               ("I'm from Mexico", ('other', 'Mexico')), ('我是巴西人', ('other', '巴西')),
                               ('Japanese food is great', None), ('Do you have an English menu?', None), ('I am Tom', None),
                               ('I am from Pudong Airport', None), ('我是本地人', None), ('我不是美国人', None),
                               ("I'm not Canadian", None), ('我是美国人，朋友是英国人', ('rules', 'US')),
                               # Review of #1856: someone else's passport never stands in for the traveler's.
                               ('我是巴西人，我朋友持英国护照', ('other', '巴西')), ('my wife has a British passport', None),
                               ('He is British', None), ('I am German and my husband is French', ('rules', 'DE')),
                               ('I have a US passport, my wife is Canadian', ('rules', 'US')),
                               # Review of #1856: no fragment of an unrelated phrase becomes a country.
                               ('我持有效护照', None), ('我是美籍华人', ('rules', 'US'))):
            with self.subTest(text=text):
                self.assertEqual(stated_nationality([text], RULES), expected)

    def test_the_latest_statement_wins(self):
        self.assertEqual(stated_nationality(['我是美国人', '更正一下，我持加拿大护照'], RULES), ('rules', 'CA'))


class Answers(unittest.TestCase):
    def test_every_listed_country_quotes_its_active_policies_and_sources(self):
        # Acceptance: entry answers agree with the rules file word for word.
        policies = {row['id']: row for row in RULES['policies']}
        for country in RULES['countries']:
            for locale in ('zh', 'en'):
                with self.subTest(country=country['code'], locale=locale):
                    statement = '我是' + country['name']['zh'] + '人' if locale == 'zh' else 'I have a ' + country['name']['en'] + ' passport'
                    reply = entry_reply('我需要签证吗？' if locale == 'zh' else 'Do I need a visa?', [statement], locale, TODAY, RULES)
                    urls = {url for _, _, url in reply.citations}
                    for key in country['policies']:
                        policy = policies[key]
                        self.assertIn(policy['summary'][locale], reply.text)
                        self.assertIn(policy['not_covered'][locale], reply.text)
                        self.assertTrue({row['url'] for row in policy['sources']} <= urls)
                    self.assertIn(country['checked_at'], reply.text)
                    if country['otherwise'] == 'check_official':
                        self.assertTrue({row['url'] for row in RULES['official_fallback']} <= urls)

    def test_without_a_stated_nationality_lio_asks_once(self):
        for locale, phrase in (('zh', '你持哪国护照？'), ('en', 'Which country issued your passport?')):
            reply = entry_reply('我需要签证吗？' if locale == 'zh' else 'Do I need a visa?', ['我想去成都'], locale, TODAY, RULES)
            self.assertTrue(reply.text.endswith(phrase))
            self.assertEqual(reply.citations, ())

    def test_transit_questions_put_the_transit_policy_first(self):
        reply = entry_reply('过境上海可以免签吗？', ['我是德国人'], 'zh', TODAY, RULES)
        transit = next(row for row in RULES['policies'] if row['kind'] == 'transit')
        visa_free = next(row for row in RULES['policies'] if row['id'] == 'unilateral-visa-free-2026')
        self.assertLess(reply.text.index(transit['summary']['zh']), reply.text.index(visa_free['summary']['zh']))

    def test_expired_policies_are_left_out(self):
        expired = dict(RULES, checked_at='2027-01-02',
                       countries=[dict(row, checked_at='2027-01-02') for row in RULES['countries']])
        reply = entry_reply('Do I need a visa?', ['I am German'], 'en', date(2027, 1, 3), expired)
        self.assertNotIn(next(row for row in RULES['policies'] if row['id'] == 'unilateral-visa-free-2026')['summary']['en'],
                         reply.text)
        self.assertIn(next(row for row in RULES['policies'] if row['kind'] == 'transit')['summary']['en'], reply.text)

    def test_after_the_review_date_lio_draws_no_conclusion(self):
        due = review_due(RULES)
        for kind_question in ('我需要签证吗？', '入境卡怎么填？'):
            reply = entry_reply(kind_question, ['我是美国人'], 'zh', due, RULES)
            self.assertIn('先不下结论', reply.text)
            for policy in RULES['policies']:
                self.assertNotIn(policy['summary']['zh'], reply.text)
            self.assertEqual({url for _, _, url in reply.citations}, {row['url'] for row in RULES['official_fallback']})

    def test_unlisted_nationality_points_to_official_sources(self):
        reply = entry_reply('Do I need a visa?', ["I'm from Mexico"], 'en', TODAY, RULES)
        self.assertIn('Mexico', reply.text)
        self.assertEqual({url for _, _, url in reply.citations}, {row['url'] for row in RULES['official_fallback']})

    def test_arrival_card_needs_no_nationality(self):
        reply = entry_reply('入境卡怎么填？', [], 'zh', TODAY, RULES)
        self.assertTrue(reply.text.startswith(RULES['arrival_card']['summary']['zh']))
        self.assertEqual({url for _, _, url in reply.citations}, {row['url'] for row in RULES['arrival_card']['sources']})

    def test_switch_is_off_by_default_and_accepts_only_zero_or_one(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CJ_LIO_ENTRY_RULES', None)
            self.assertFalse(entry_rules_enabled())
        with patch.dict(os.environ, {'CJ_LIO_ENTRY_RULES': '1'}):
            self.assertTrue(entry_rules_enabled())
        with patch.dict(os.environ, {'CJ_LIO_ENTRY_RULES': 'yes'}), self.assertRaises(ValueError):
            entry_rules_enabled()


class FollowUp(unittest.TestCase):
    def test_a_reply_that_only_gives_a_nationality_answers_the_previous_visa_question(self):
        # Review of #1856: after Lio asks for the passport, "美国" or "American" alone gets the rules answer.
        for reply, locale in (('美国', 'zh'), ('我持美国护照', 'zh'), ('美国人', 'zh'), ('American', 'en'),
                              ('an American', 'en'), ('US passport', 'en')):
            with self.subTest(reply=reply):
                question = '我需要签证吗？' if locale == 'zh' else 'Do I need a visa?'
                answer = entry_turn(reply, [question], locale, TODAY, RULES)
                self.assertIn('美国' if locale == 'zh' else 'United States', answer.text)

    def test_other_short_replies_are_not_entry_turns(self):
        for reply, prior in (('好的', ['我需要签证吗？']), ('美国', ['成都有什么好吃的']), ('美国', [])):
            with self.subTest(reply=reply, prior=prior):
                self.assertIsNone(entry_turn(reply, prior, 'zh', TODAY, RULES))


class Dispatch(unittest.TestCase):
    def run_dispatch(self, text, *, switch, prior=(), failure=False, unavailable=False):
        from cj_api.local_lio_exploration import ExplorationDispatch
        events, delegated = [], []

        class Legacy:
            def context(self, binding, current, answer_only=False):
                assert answer_only
                if unavailable:
                    from cj_message.domain import Unavailable
                    raise Unavailable('original nationwide context was erased')
                return (*prior, current.text), (), None
            def _reply(self, worker, binding, state, reply):
                events.append(('text_delta', reply))
                return 'done'
            def execute(self, *args):
                delegated.append(args)
                return 'delegated'
        worker = SimpleNamespace(_event=lambda binding, state, kind, value: events.append((kind, value)) or state)
        original = SimpleNamespace(protocol='LIO-message.2', locale='zh', question_day=TODAY)
        dispatch = ExplorationDispatch(Legacy(), SimpleNamespace(enabled=False))
        with patch.dict(os.environ, {'CJ_LIO_ENTRY_RULES': switch}):
            if failure:
                with patch('cj_api.lio_entry_rules.load_rules', side_effect=FactFailure('arrival_rules_unavailable')), \
                        self.assertLogs('cj_usage.audit', logging.INFO) as logs:
                    result = dispatch.execute(worker, SimpleNamespace(run_id='r1'), 's', text, original)
                self.assertEqual(logs.output, ['INFO:cj_usage.audit:LIO_ENTRY_RULES_UNAVAILABLE run_id=r1 '
                                               'code=arrival_rules_unavailable'])
            elif unavailable:
                with self.assertLogs('cj_usage.audit', logging.INFO) as logs:
                    result = dispatch.execute(worker, SimpleNamespace(run_id='r1'), 's', text, original)
                self.assertEqual(logs.output, ['INFO:cj_usage.audit:LIO_ENTRY_RULES_UNAVAILABLE run_id=r1 code=Unavailable'])
            else:
                result = dispatch.execute(worker, SimpleNamespace(run_id='r1'), 's', text, original)
        return result, events, delegated

    def test_switch_off_or_other_questions_keep_the_old_path(self):
        for text, switch in (('我需要签证吗？', '0'), ('成都有什么好吃的', '1')):
            with self.subTest(text=text, switch=switch):
                result, events, delegated = self.run_dispatch(text, switch=switch, prior=('我是美国人',))
                self.assertEqual((result, events, len(delegated)), ('delegated', [], 1))

    def test_entry_question_is_answered_from_rules_with_sources_first(self):
        result, events, delegated = self.run_dispatch('我需要签证吗？', switch='1', prior=('我是美国人',))
        self.assertEqual((result, delegated), ('done', []))
        kinds = [kind for kind, _ in events]
        self.assertEqual(kinds[-1], 'text_delta')
        self.assertTrue(kinds[:-1] and set(kinds[:-1]) == {'effect_committed'})
        self.assertIn('持美国普通护照', events[-1][1])

    def test_unreadable_context_falls_back_to_the_old_path(self):
        result, events, delegated = self.run_dispatch('我需要签证吗？', switch='1', unavailable=True)
        self.assertEqual((result, events, len(delegated)), ('delegated', [], 1))

    def test_nationality_reply_after_a_visa_question_is_answered_from_rules(self):
        result, events, delegated = self.run_dispatch('美国', switch='1', prior=('我需要签证吗？',))
        self.assertEqual((result, delegated), ('done', []))
        self.assertIn('持美国普通护照', events[-1][1])

    def test_unreadable_rules_fall_back_to_the_old_path(self):
        result, events, delegated = self.run_dispatch('我需要签证吗？', switch='1', failure=True)
        self.assertEqual((result, events, len(delegated)), ('delegated', [], 1))


if __name__ == '__main__':
    unittest.main()
