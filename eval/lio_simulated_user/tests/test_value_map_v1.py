"""Representation controls only, never real baseline results."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from eval.lio_simulated_user import value_map_v1 as mapping


def fact(value, state='known'):
    return dict(value=value, state=state,
                sources=[dict(kind='message', message_id='fixture-mid', sequence=1,
                              quote='fixture original', offset=0)])


class PublicValueMap(unittest.TestCase):
    def test_whole_bilingual_product_forms_have_one_published_meaning(self):
        examples = [('city', '北京', 'beijing'), ('city', 'Beijing (北京)', 'beijing'),
                    ('season', '秋天', 'autumn'), ('season', 'FALL', 'autumn'),
                    ('pace', '慢节奏', 'relaxed'), ('pace', 'Leisurely', 'relaxed'),
                    ('party_type', 'family', 'family_with_child'),
                    ('party_type', 'With children', 'family_with_child'),
                    ('lodging_tier', 'simple', 'budget'),
                    ('lodging_tier', '经济型', 'budget')]
        for key, raw, expected in examples:
            with self.subTest(key=key, raw=raw):
                row = mapping.normalize_value(key, raw)
                self.assertEqual((row['status'], row['value']), ('NORMALIZED', expected))
                self.assertEqual(row['raw_value'], raw)

    def test_cities_do_not_use_substrings_fuzzy_matches_or_ambiguous_pinyin(self):
        for raw in ('Taizhou', '苏州', 'Beijing or Shanghai', 'not Beijing', '去北京玩',
                    'beijin', 'New Beijing', "Xi'an"):
            with self.subTest(raw=raw):
                row = mapping.normalize_value('city', raw)
                self.assertEqual(row['status'], 'UNAVAILABLE')
                self.assertEqual(row['raw_value'], raw)

    def test_type_identity_does_not_turn_booleans_into_numbers(self):
        for key, raw in [('duration_days', True), ('duration_days', 3.0),
                         ('duration_days', '3'), ('first_visit', 1),
                         ('first_visit', 'First visit')]:
            with self.subTest(key=key, raw=raw):
                self.assertEqual(mapping.normalize_value(key, raw)['status'], 'UNAVAILABLE')
        self.assertIs(mapping.normalize_value('first_visit', False)['value'], False)
        self.assertEqual(mapping.normalize_value('duration_days', 5)['value'], 5)

    def test_arrays_retain_every_item_order_and_duplicate(self):
        row = mapping.normalize_value('interests', ['美食', 'History', '当地美食'])
        self.assertEqual(row['value'], ['food', 'history', 'food'])
        self.assertEqual(mapping.normalize_value('dietary', ['素食', '不吃辣'])['value'],
                         ['vegetarian', 'mild'])
        self.assertEqual(mapping.normalize_value('dietary', [])['value'], [])

    def test_array_unknowns_do_not_get_dropped_or_replaced_by_category(self):
        for key, raw in [('interests', 'food'), ('dietary', 'vegetarian'),
                         ('must_see', ['故宫博物院']), ('must_see', ['museum', 'unknown']),
                         ('avoid', [True]), ('interests', ['not history'])]:
            with self.subTest(key=key, raw=raw):
                result = mapping.normalize_value(key, raw)
                self.assertEqual(result['status'], 'UNAVAILABLE')
                self.assertEqual(result['raw_value'], raw)
                self.assertIsNone(result['value'])

    def test_null_missing_and_explicit_no_restriction_stay_distinct(self):
        raw = dict(mobility=fact(None), dietary=fact([]))
        result = mapping.normalize_profile(raw, native_profile_complete=True)
        self.assertEqual(result['factors']['mobility']['reason'], 'explicit_null')
        self.assertEqual(result['factors']['dietary']['status'], 'NORMALIZED')
        self.assertIn('arrival', result['missing_factors'])
        self.assertNotIn('mobility', result['missing_factors'])
        self.assertTrue(result['native_profile_complete'])
        self.assertFalse(result['normalization_complete'])

    def test_coarse_times_never_invent_day_clock_or_transport(self):
        for key in ('arrival', 'departure'):
            for raw in ('morning', '下午到达', '09:00', dict(day=1, time='09:00', mode='flight')):
                with self.subTest(key=key, raw=raw):
                    result = mapping.normalize_value(key, raw)
                    self.assertEqual(result['reason'], 'precise_temporal_source_required')
                    self.assertEqual(result['raw_value'], raw)

    def test_state_and_provenance_are_never_upgraded_or_aliased(self):
        for state in ('known', 'not_needed', 'inferred', 'default', 'memory', 'from_memory'):
            raw = dict(pace=fact('slow', state))
            raw['pace']['extra_original_reference'] = 'fixture:kept'
            before = deepcopy(raw)
            result = mapping.normalize_profile(raw, native_profile_complete=False)
            self.assertEqual(raw, before)
            self.assertEqual(result['factors']['pace']['raw_fact'], before['pace'])
            self.assertFalse(result['native_profile_complete'])
            result['factors']['pace']['raw_fact']['sources'].clear()
            self.assertEqual(raw, before)

    def test_no_result_certifies_custody_a_trace_or_a_score(self):
        result = mapping.normalize_profile(dict(city=fact('北京')), native_profile_complete=True)
        self.assertEqual(result['version'], 'LIO-normalized-profile.1')
        self.assertEqual(result['catalog_version'], 'LIO-profile-value-map.1')
        self.assertEqual(result['catalog_sha256'], mapping.CATALOG_SHA256)
        self.assertFalse(result['normalization_complete'])
        for key in ('profile', 'G2', 'G3', 'PASS', 'exploration_complete', 'questions_complete',
                    'memory_observation', 'observation_ref', 'custody_verified'):
            self.assertNotIn(key, result)

    def test_external_shape_errors_fail_closed(self):
        for profile, complete in (([], True), ({'city': fact('北京')}, 1),
                                  ({'unknown': fact('北京')}, True),
                                  ({'city': {'value': '北京', 'state': 'known'}}, True),
                                  ({'city': fact(float('nan'))}, True)):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                mapping.normalize_profile(profile, native_profile_complete=complete)
        for key in ('hidden_answers', 'profile_id', 'unknown'):
            with self.assertRaises(ValueError): mapping.normalize_value(key, '北京')

    def test_converter_has_no_persona_backend_actor_or_scorer_dependency(self):
        tree = ast.parse(Path(mapping.__file__).read_text())
        imported = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertEqual(set(imported), {'copy', 'hashlib', 'pathlib', 'cj_strict_json'})
        catalog = json.loads(mapping.CATALOG.read_bytes())
        self.assertEqual(len(catalog['factors']), 14)
        self.assertEqual(len(mapping.CATALOG_SHA256), 64)
        self.assertTrue(all(row['path'].startswith(('backend/', 'docs/quality/'))
                            for row in catalog['sources']))

    def test_malformed_or_ambiguous_catalog_is_not_silently_loaded(self):
        catalog = json.loads(mapping.CATALOG.read_bytes())
        changes = [lambda v: v.update(version='LIO-profile-value-map.0'),
                   lambda v: v.update(factors=['city']),
                   lambda v: v['aliases']['city'].update(chengdu=['北京']),
                   lambda v: v['aliases']['city'].update(beijing=['']),
                   lambda v: v['aliases']['city'].update(beijing=[True])]
        for change in changes:
            changed = deepcopy(catalog); change(changed)
            with patch.object(Path, 'read_bytes', return_value=json.dumps(changed).encode()), self.assertRaises(ValueError):
                mapping._load_catalog()
        for raw in (b'{"version":1,"version":2}', b'{"version":NaN}'):
            with patch.object(Path, 'read_bytes', return_value=raw), self.assertRaises(ValueError):
                mapping._load_catalog()


if __name__ == '__main__': unittest.main()
