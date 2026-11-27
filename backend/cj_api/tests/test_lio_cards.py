"""Tool cards in answers (#1990, D-2; LIO-answer-rich.1): the table, the stored effect, the read, the switch."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

from cj_message import lio_cards as cards
from cj_message.lio_followups import Destination

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'contracts/message'))
import check_lio_answer_rich as contract  # noqa: E402

PALACE = Destination('故宫博物院', '116.397026,39.918058', '景山前街4号', 'The Palace Museum')


def kinds(rows):
    return [row['type'] for row in rows]


class Build(unittest.TestCase):
    def test_a_taxi_card_needs_a_taxi_question_and_a_destination_from_the_map_result(self):
        card, = cards.build('怎么打车去故宫', 'zh', destination=PALACE, taxi_topic=True)
        self.assertEqual(card, dict(type='taxi', label='打车去这里', open=dict(tool='taxi', parameters=dict(
            destination='故宫博物院', lat='39.918058', lng='116.397026', address='景山前街4号', destinationEN='The Palace Museum'))))
        self.assertEqual(cards.build('怎么打车去故宫', 'en', destination=PALACE, taxi_topic=True)[0]['label'], 'Taxi there')
        self.assertEqual(cards.build('怎么打车去故宫', 'zh', destination=None, taxi_topic=True), [])          # no destination, no card
        self.assertEqual(cards.build('故宫开门吗', 'zh', destination=PALACE, taxi_topic=False), [])           # not a taxi question
        for bad in (Destination('故宫', '0,0', None, None), Destination('故宫', '116.1,39.9999999', None, None), Destination(' ', '116.4,39.9', None, None),
                    Destination('故宫', '2.35,48.85', None, None)):
            self.assertEqual(cards.build('打车去故宫', 'zh', destination=bad, taxi_topic=True), [], bad)

    def test_a_metro_card_needs_a_metro_question_and_a_confirmed_city_with_a_bundled_map(self):
        card, = cards.build('北京地铁怎么坐', 'zh', library_city='beijing')
        self.assertEqual(card['data'], dict(city=dict(id='beijing', zh='北京', en='Beijing')))
        self.assertEqual(card['open'], dict(tool='metro-guide', parameters={}))
        self.assertEqual(cards.build('地铁怎么坐', 'zh', library_city=None), [])
        self.assertEqual(cards.build('地铁怎么坐', 'zh', library_city='hangzhou'), [])
        self.assertEqual(cards.build('今天天气怎么样', 'zh', library_city='beijing'), [])
        self.assertNotIn('route', card['data'])             # station data is not sent in this version

    def test_a_transport_card_needs_two_different_cities(self):
        card, = cards.build('北京到上海的高铁多久', 'zh')
        self.assertEqual(card['open']['parameters'], {'from': 'beijing', 'to': 'shanghai'})
        self.assertEqual(card['data']['to'], dict(id='shanghai', zh='上海', en='Shanghai'))
        card, = cards.build('flights from Shanghai to Beijing', 'en')
        self.assertEqual(card['open']['parameters'], {'from': 'shanghai', 'to': 'beijing'})
        self.assertEqual(card['label'], 'Trains & flights')
        one, = cards.build('高铁去上海要多久', 'zh', library_city='beijing')
        self.assertEqual(one['open']['parameters'], {'from': 'beijing', 'to': 'shanghai'})
        self.assertEqual(cards.build('高铁去北京要多久', 'zh', library_city='beijing'), [])      # the same city twice
        self.assertEqual(cards.build('高铁怎么买票', 'zh'), [])
        self.assertEqual(cards.build('北京的高铁', 'zh'), [])                                   # one city, no confirmed other

    def test_a_currency_card_carries_a_quote_only_when_exactly_one_is_named(self):
        self.assertEqual(cards.build('美元汇率多少', 'zh')[0]['data'], dict(quote='USD'))
        self.assertEqual(cards.build('how do I convert yen?', 'en')[0]['data'], dict(quote='JPY'))
        self.assertEqual(cards.build('Where can I exchange yen?', 'en')[0]['data'], dict(quote='JPY'))   # found by the Q-1 evaluation
        self.assertNotIn('data', cards.build('在哪里换钱', 'zh')[0])
        self.assertNotIn('data', cards.build('美元和欧元的汇率', 'zh')[0])               # two quotes: none
        self.assertNotIn('data', cards.build('exchange rate for a dollarstore', 'en')[0])  # not a word
        self.assertNotIn('cny_per_unit', json.dumps(cards.build('美元汇率', 'zh')))      # no rate on the answer path yet

    def test_order_and_the_limit_of_three(self):
        found = cards.build('北京地铁和北京到上海的高铁，还有美元汇率，打车去故宫', 'zh', destination=PALACE, library_city='beijing', taxi_topic=True)
        self.assertEqual(kinds(found), ['taxi', 'metro', 'transport'])
        self.assertEqual(kinds(cards.build('北京地铁和北京到上海的高铁，还有美元汇率', 'zh', library_city='beijing')), ['metro', 'transport', 'currency'])

    def test_every_built_card_passes_the_contract_checker(self):
        samples = [cards.build('怎么打车去故宫', 'zh', destination=PALACE, taxi_topic=True), cards.build('北京地铁', 'en', library_city='beijing'),
                   cards.build('北京到上海高铁', 'zh'), cards.build('美元汇率', 'zh'), cards.build('换钱', 'en')]
        for rows in samples:
            self.assertTrue(rows)
            contract.check(dict(version='LIO-answer-rich.1', cards=rows))

    def test_the_tables_agree_with_the_app_and_the_contract(self):
        metro = ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/Resources/Metro'
        for city in cards.METRO_CITIES:
            self.assertTrue((metro / f'LioMetroMap.{city}.v1.json').exists(), city)
        self.assertEqual(cards.TOOLS, contract.CARD_TOOLS)
        self.assertEqual(set(cards.QUOTES), {'USD', 'EUR', 'GBP', 'JPY', 'KRW', 'HKD', 'AUD', 'CAD', 'SGD', 'THB'})
        registry = (ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/LioToolRegistry.swift').read_text(encoding='utf-8')
        for tool in cards.TOOLS.values():
            self.assertIn(f'LioTool("{tool}")', registry)


class Stored(unittest.TestCase):
    def test_wire_returns_the_cards_in_table_order_one_per_type(self):
        built = cards.build('北京地铁，北京到上海高铁，美元汇率', 'zh', library_city='beijing')
        stored = cards.effect(list(reversed(built)) + [built[0]], 1_800_000_000)
        self.assertEqual(kinds(cards.wire(stored)), ['metro', 'transport', 'currency'])

    def test_a_card_that_fails_the_tables_is_dropped_alone(self):
        built = cards.build('北京地铁，北京到上海高铁', 'zh', library_city='beijing')
        bad_tool = json.loads(json.dumps(built[0])); bad_tool['open']['tool'] = 'shell'
        bad_label = json.loads(json.dumps(built[1])); bad_label['label'] = '免费'
        bad_city = json.loads(json.dumps(built[1])); bad_city['data']['to']['zh'] = '别处'
        same = json.loads(json.dumps(built[1])); same['open']['parameters']['to'] = 'beijing'; same['data']['to'] = same['data']['from']
        extra = json.loads(json.dumps(built[1])); extra['open']['parameters']['phone'] = '1'
        for broken in (bad_tool, bad_label, bad_city, same, extra):
            self.assertIsNone(cards.wire(cards.effect([broken], 1)), broken)
            self.assertEqual(kinds(cards.wire(cards.effect([broken, built[0]], 1))), ['metro'])

    def test_a_taxi_card_is_checked_again_with_the_shared_parameter_rules(self):
        card, = cards.build('打车去故宫', 'zh', destination=PALACE, taxi_topic=True)
        for field, value in (('lat', '39.9999999'), ('lng', '2.35'), ('destination', '故宫​'), ('address', 'x' * 201)):
            broken = json.loads(json.dumps(card)); broken['open']['parameters'][field] = value
            self.assertIsNone(cards.wire(cards.effect([broken], 1)), field)
        half = json.loads(json.dumps(card)); del half['open']['parameters']['lng']
        self.assertIsNone(cards.wire(cards.effect([half], 1)))
        for field in ('destination', 'lat', 'lng'):            # stored values were stripped when built: a padded one is damaged
            padded = json.loads(json.dumps(card)); padded['open']['parameters'][field] = ' ' + padded['open']['parameters'][field] + ' '
            self.assertIsNone(cards.wire(cards.effect([padded], 1)), field)
        self.assertEqual(cards.wire(cards.effect([card], 1)), [card])

    def test_a_damaged_record_reads_as_nothing_and_never_raises(self):
        for value in ('lio_cards:', 'lio_cards:oops', 'lio_cards:[]', 'lio_cards:{}', 'lio_cards:{"cards":1,"issued_at":1}',
                      'lio_cards:{"cards":[null,5,"x",[]],"issued_at":1}', 'lio_cards:{"cards":[],"issued_at":1,"extra":1}', None, 5, b'x'):
            self.assertIsNone(cards.wire(value), value)


class Switch(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop('CJ_LIO_CARDS', None)

    def test_off_by_default_strict_and_the_effect_needs_a_card(self):
        self.assertFalse(cards.cards_enabled())
        self.assertIsNone(cards.card_effect('北京地铁', 'zh', destination=None, adcode='110000', taxi_topic=False, now=1))
        os.environ['CJ_LIO_CARDS'] = 'on'
        self.assertTrue(cards.card_effect('北京地铁', 'zh', destination=None, adcode='110000', taxi_topic=False, now=1).startswith('lio_cards:'))
        self.assertIsNone(cards.card_effect('今天天气', 'zh', destination=None, adcode='110000', taxi_topic=False, now=1))
        for bad in ('', '1', 'ON'):
            os.environ['CJ_LIO_CARDS'] = bad
            with self.assertRaises(ValueError):
                cards.cards_enabled()


if __name__ == '__main__':
    unittest.main()
