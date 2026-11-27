"""Entity links in answers (#1989, D-1; LIO-answer-rich.1): the linker, the stored effect, the read, the switches.

The library documents are synthetic. The production library holds only human-approved places and none yet
(`knowledge/places/candidates/` is not the library), so everything here supplies its own.
"""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

from cj_message import lio_entities as ent

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'contracts/message'))
import check_lio_answer_rich as contract  # noqa: E402


def place(pid, zh, en, aliases_zh=(), aliases_en=(), status='approved'):
    return dict(id=pid, city='beijing', category='attraction', name_zh=zh, name_en=en, aliases_zh=list(aliases_zh),
                aliases_en=list(aliases_en), review=dict(status=status, reviewer='t', reviewed_on='2026-11-27', note=None))


DOC = dict(version='g2c-places.1', city='beijing', places=[
    place('pl_bj_gugong', '故宫博物院', 'The Palace Museum', ['故宫', '紫禁城'], ['Forbidden City', 'Palace Museum']),
    place('pl_bj_jingshan', '景山公园', 'Jingshan Park'),
    place('pl_bj_wangfujing', '王府井', 'Wangfujing', ['王府井大街']),
    place('pl_bj_tiantan', '天坛公园', 'Temple of Heaven', ['天坛']),
    place('pl_bj_old', '老地方', 'Old Place', status='retired'),
    place('pl_bj_short', '井', 'Jin'),                 # too short to match by name
    place('pl_bj_md', '星*号', 'Star*Place'),            # a Markdown character: never matched
])
APPROVED = {p['id'] for p in DOC['places'] if p['review']['status'] == 'approved'}


def items(answer, docs=(DOC,)):
    return ent.link(answer, docs)


def pieces(answer, found):
    return [(answer[s:e], pid) for s, e, pid in found]


class Linker(unittest.TestCase):
    def test_names_and_aliases_are_linked_longest_first_and_in_order(self):
        answer = '上午去故宫博物院，然后去景山公园，晚上逛王府井大街。'
        self.assertEqual(pieces(answer, items(answer)), [('故宫博物院', 'pl_bj_gugong'), ('景山公园', 'pl_bj_jingshan'),
                                                       ('王府井大街', 'pl_bj_wangfujing')])

    def test_only_the_first_mention_of_a_place_is_linked(self):
        answer = '先去故宫，再去景山公园，回来还想再看一次故宫博物院。'
        self.assertEqual(pieces(answer, items(answer)), [('故宫', 'pl_bj_gugong'), ('景山公园', 'pl_bj_jingshan')])

    def test_english_names_are_case_folded_and_need_word_boundaries(self):
        answer = 'Start at the palace museum, see forbidden city walls, then Temple of Heaven.'
        self.assertEqual([p for _, p in pieces(answer, items(answer))], ['pl_bj_gugong', 'pl_bj_tiantan'])
        self.assertEqual(items('The Palace Museums are big and Xwangfujing is not a place.'), [])

    def test_a_place_in_markdown_bold_is_linked_without_the_asterisks(self):
        answer = '上午去**故宫**，下午去景山公园。'
        self.assertEqual(pieces(answer, items(answer))[0], ('故宫', 'pl_bj_gugong'))

    def test_no_link_inside_markdown_links_code_or_urls(self):
        for answer in ('看[故宫的介绍](https://example.com/故宫)吧', '用 `故宫` 这个词', '```\n故宫\n```', '见 https://example.com/jingshan景山公园 页面'):
            self.assertEqual(items(answer), [], answer)

    def test_a_long_run_of_unclosed_brackets_is_linear_and_an_overlong_answer_is_not_scanned(self):
        import time
        for filler in ('[', '[a', '```', '`x'):
            answer = filler * (ent.MAX_LINK_SCALARS // len(filler)) + '故宫'
            started = time.monotonic()
            items(answer)
            self.assertLess(time.monotonic() - started, 0.4, repr(filler))   # before the bound: about 0.9 s for '['
        self.assertEqual(items('故宫' + '。' * ent.MAX_LINK_SCALARS), [])                       # over the linker's own limit
        self.assertEqual(len(items('故宫' + '。' * (ent.MAX_LINK_SCALARS - 3))), 1)             # just under it
        self.assertEqual(items('看[' + '故宫' * 100 + '](https://example.com/x)吧'), [])         # a long link text is still skipped

    def test_a_stop_suffix_means_a_different_place(self):
        for answer in ('王府井站很近。', '故宫路很堵。', '天坛区域不错', 'Wangfujing Station is near.', '天坛机场不存在'):
            self.assertEqual(items(answer), [], answer)

    def test_a_gate_or_exit_word_before_station_is_a_station_too(self):
        for answer in ('天坛东门站很近。', '到天坛西南门站下车', '故宫北门站出来右转'):
            self.assertEqual(items(answer), [], answer)
        self.assertEqual(items('天坛东门很美，故宫北门也值得看。'), [(0, 2, 'pl_bj_tiantan'), (7, 9, 'pl_bj_gugong')])   # a gate without 站 is still the place

    def test_retired_unapproved_short_and_markdown_names_are_never_linked(self):
        self.assertEqual(items('老地方 Old Place 很好。星*号 Star*Place 井 Jin'), [])
        unreviewed = dict(DOC, places=[place('pl_bj_new', '新地方', 'New Place', status='pending')])
        self.assertEqual(items('新地方 New Place', (unreviewed,)), [])

    def test_a_flag_or_a_joiner_never_splits_and_emoji_shift_nothing(self):
        answer = '🇨🇳 欢迎，先去天坛看看😀，再去王府井走走。'
        found = items(answer)
        self.assertEqual(pieces(answer, found), [('天坛', 'pl_bj_tiantan'), ('王府井', 'pl_bj_wangfujing')])
        self.assertTrue(all(ent.span_ok(answer, s, e) for s, e, _ in found))

    def test_at_most_twenty_and_never_more_than_one_per_place(self):
        many = dict(DOC, places=[place(f'pl_bj_p{i}', f'地点{chr(0x4e00 + i)}号院', f'Place {i} Garden') for i in range(30)])
        answer = '，'.join(f'去地点{chr(0x4e00 + i)}号院' for i in range(30))
        self.assertEqual(len(items(answer, (many,))), ent.MAX_ENTITIES)

    def test_odd_input_never_raises(self):
        for answer in (None, 5, '', ' ', 'x' * 300000, '\ud800故宫', '😀' * 100):
            self.assertIsInstance(items(answer), list)

    def test_every_result_satisfies_the_contract_checker(self):
        for answer in ('上午去**故宫**，下午去景山公园看全景😀。\n\n晚上可以去王府井走走。', 'See the Forbidden City and Temple of Heaven.', '先去天坛，再去故宫。'):
            rows = [dict(type='place', start=s, end=e, place_id=p) for s, e, p in items(answer)]
            self.assertTrue(rows)
            contract.check(dict(version='LIO-answer-rich.1', entities=rows), answer)


class Effect(unittest.TestCase):
    def test_the_effect_binds_the_ranges_to_the_exact_answer(self):
        answer = '先去故宫，再去景山公园。'
        stored = ent.effect(answer, items(answer))
        self.assertTrue(stored.startswith('lio_entities:'))
        rows = ent.wire(stored, answer, APPROVED.__contains__)
        self.assertEqual([r['place_id'] for r in rows], ['pl_bj_gugong', 'pl_bj_jingshan'])
        self.assertEqual(ent.wire(stored, answer + ' ', APPROVED.__contains__), None)       # the answer changed: nothing
        self.assertEqual(ent.wire(stored, '先去故宫，再去景山公园！', APPROVED.__contains__), None)

    def test_a_place_that_is_no_longer_approved_is_dropped_alone(self):
        answer = '先去故宫，再去景山公园。'
        stored = ent.effect(answer, items(answer))
        rows = ent.wire(stored, answer, lambda pid: pid != 'pl_bj_gugong')
        self.assertEqual([r['place_id'] for r in rows], ['pl_bj_jingshan'])
        self.assertIsNone(ent.wire(stored, answer, lambda pid: False))

    def test_a_damaged_record_reads_as_nothing_and_never_raises(self):
        answer = '先去故宫。'
        good = json.loads(ent.effect(answer, items(answer)).removeprefix('lio_entities:'))
        broken = [
            'lio_entities:', 'lio_entities:not json', 'lio_entities:[]', 'lio_entities:{}',
            'lio_entities:' + json.dumps(dict(good, places='g2c-places.2')),
            'lio_entities:' + json.dumps(dict(good, items='x')),
            'lio_entities:' + json.dumps(dict(good, items=[[0, 1, 'pl_bj_gugong']])),            # one scalar
            'lio_entities:' + json.dumps(dict(good, items=[[3, 5, 'PL_BJ_GUGONG']])),
            'lio_entities:' + json.dumps(dict(good, items=[[3.0, 5, 'pl_bj_gugong']])),
            'lio_entities:' + json.dumps(dict(good, items=[[True, 5, 'pl_bj_gugong']])),
            'lio_entities:' + json.dumps(dict(good, extra=1)),
        ]
        for value in broken:
            self.assertIsNone(ent.wire(value, answer, lambda pid: True), value)
        for value in (None, 5, b'x'):
            self.assertIsNone(ent.wire(value, answer, lambda pid: True))
        self.assertIsNone(ent.wire(ent.effect(answer, items(answer)), None, lambda pid: True))

    def test_an_overlapping_entry_is_dropped_alone(self):
        answer = '先去故宫。'
        crossed = 'lio_entities:' + json.dumps(dict(answer_sha256=ent.answer_sha256(answer), places='g2c-places.1',
                                                   items=[[3, 5, 'pl_bj_gugong'], [4, 5, 'pl_bj_jingshan']]))
        self.assertEqual([r['place_id'] for r in ent.wire(crossed, answer, lambda pid: True)], ['pl_bj_gugong'])

    def test_read_checks_use_the_same_span_rules_as_the_writer(self):
        answer = '王府井站很近，也去天坛。'
        forged = 'lio_entities:' + json.dumps(dict(answer_sha256=ent.answer_sha256(answer), places='g2c-places.1',
                                                  items=[[0, 3, 'pl_bj_wangfujing'], [8, 10, 'pl_bj_tiantan']]))
        rows = ent.wire(forged, answer, lambda pid: True)
        self.assertEqual([r['place_id'] for r in rows], ['pl_bj_tiantan'])      # the station is dropped on read


class ApprovedIds(unittest.TestCase):
    """`approved_ids` keeps a complete read, and keeps an incomplete one only briefly (#2074)."""

    def setUp(self):
        ent.forget_approved_ids()
        self.addCleanup(ent.forget_approved_ids)

    def test_a_temporary_read_failure_is_not_kept_for_the_life_of_the_process(self):
        from cj_fact import places
        from cj_fact.policy import FactFailure
        calls = []

        def load(city, path=None):
            calls.append(city)
            if not unreadable:
                return DOC
            raise FactFailure('places_missing')

        unreadable = True
        with mock.patch.object(places, 'load_city', load), mock.patch.object(ent.time, 'monotonic', side_effect=lambda: clock[0]):
            clock = [100.0]
            self.assertEqual(ent.approved_ids(), frozenset())
            first = len(calls)
            self.assertEqual(ent.approved_ids(), frozenset())                       # within the retry window: not read again
            self.assertEqual(len(calls), first)
            unreadable = False
            clock[0] += ent.RETRY_SECONDS + 1
            self.assertEqual(ent.approved_ids(), APPROVED)                          # the library is back: seen again
            second = len(calls)
            clock[0] += 10 ** 6
            self.assertEqual(ent.approved_ids(), APPROVED)                          # a complete read stays for the process
            self.assertEqual(len(calls), second)


class ContextCity(unittest.TestCase):
    """#2072: the city this conversation's last planning context confirmed is a candidate city too."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {'CJ_LIO_ENTITIES': 'on'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_city_word_names_only_a_library_city(self):
        for word, city in (('北京', 'beijing'), (' Beijing ', 'beijing'), ('成都', 'chengdu'), ('重庆', 'chongqing')):
            self.assertEqual(ent.city_for_name(word), city, word)
        for word in ('杭州', 'Hangzhou', '北京市', '', None, 7, ['北京']):
            self.assertIsNone(ent.city_for_name(word), word)

    def test_a_conversation_with_a_confirmed_city_links_without_a_destination_this_turn(self):
        answer = '先去故宫，再去景山公园。'
        with mock.patch.object(ent, 'library_docs', lambda city: [DOC] if city == 'beijing' else []):
            self.assertIsNotNone(ent.entity_effect(answer, None, context_city='北京'))
            self.assertIsNone(ent.entity_effect(answer, None, context_city='杭州'))           # not a library city
            self.assertIsNone(ent.entity_effect(answer, None, context_city=None))             # a conversation with no confirmed city
            self.assertIsNone(ent.entity_effect(answer, None))

    def test_this_turns_destination_and_the_conversation_city_are_both_candidates_without_a_double_read(self):
        reads = []
        with mock.patch.object(ent, 'library_docs', lambda city: reads.append(city) or ([DOC] if city == 'beijing' else [])):
            ent.entity_effect('先去故宫。', '110000', context_city='北京')
            self.assertEqual(reads, ['beijing'])                                              # the same city twice reads once
            reads.clear()
            ent.entity_effect('先去故宫。', '310000', context_city='北京')
            self.assertEqual(reads, ['shanghai', 'beijing'])


class Switches(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ('CJ_LIO_ENTITIES', 'CJ_LIO_ANSWER_RICH'):
            os.environ.pop(name, None)

    def test_both_are_off_by_default_and_strict(self):
        self.assertFalse(ent.entities_enabled())
        self.assertFalse(ent.rich_enabled())
        os.environ['CJ_LIO_ENTITIES'] = 'on'
        os.environ['CJ_LIO_ANSWER_RICH'] = 'on'
        self.assertTrue(ent.entities_enabled() and ent.rich_enabled())
        for bad in ('', '1', 'ON', 'true'):
            os.environ['CJ_LIO_ENTITIES'] = bad
            with self.assertRaises(ValueError):
                ent.entities_enabled()

    def test_the_effect_needs_the_switch_a_confirmed_library_city_and_a_hit(self):
        answer = '先去故宫，再去景山公园。'
        self.assertIsNone(ent.entity_effect(answer, '110000', docs=[DOC]))           # switch off
        os.environ['CJ_LIO_ENTITIES'] = 'on'
        self.assertIsNotNone(ent.entity_effect(answer, '110000', docs=[DOC]))
        self.assertIsNone(ent.entity_effect('今天天气不错', '110000', docs=[DOC]))
        self.assertIsNone(ent.entity_effect('', '110000', docs=[DOC]))
        self.assertIsNone(ent.entity_effect(answer, '999999'))                         # not a library city: nothing read
        self.assertIsNone(ent.entity_effect(answer, None))
        self.assertIsNone(ent.entity_effect(answer, '110000'))                         # no library copy yet: nothing

    def test_destination_codes_map_to_the_library_cities(self):
        for adcode, city in (('110000', 'beijing'), ('110105', 'beijing'), ('310100', 'shanghai'), ('440100', 'guangzhou'),
                             ('440304', 'shenzhen'), ('510100', 'chengdu'), ('500100', 'chongqing'), ('330100', None), ('440600', None),
                             ('11', None), (None, None), (110000, None)):
            self.assertEqual(ent.city_for_adcode(adcode), city, adcode)


if __name__ == '__main__':
    unittest.main()
