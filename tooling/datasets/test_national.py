from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .convert import HERE, ROOT, canonical, load, sha, validate
from .national import BEHAVIORS, CITIES, DATA_VERSION, PROMPT_VERSION, catalog, run_national, seeds
from .teacher import FakeTeacher, FakeTools, cases, run_fake


class NationalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_fixed_seed_bytes_versions_full_city_language_behavior_matrix(self):
        rows = seeds()
        self.assertEqual(len(rows), 176)
        self.assertEqual(len({r['trip_family'] for r in rows}), 40)
        self.assertEqual(len({r['task_id'] for r in rows}), 48)
        self.assertEqual((HERE / 'national-seeds.v2.jsonl').read_bytes(),
                         ''.join(canonical(r) + '\n' for r in rows).encode())
        for city in CITIES:
            for language in ('zh', 'en'):
                for behavior in BEHAVIORS:
                    group = [r for r in rows if r['trip_family'] == f'f-national-v2/{city[0]}/{behavior}' and
                             r['language'] == language]
                    self.assertGreaterEqual(len(group), 2)
                    self.assertTrue(all((city[1] if language == 'zh' else city[2]) in
                                        ' '.join(m['content'] or '' for m in r['messages'] if m['role'] == 'user') for r in group))
        for r in rows:
            validate(r)
            self.assertEqual(r['source']['revision'], DATA_VERSION)
            self.assertEqual(r['versions']['prompt'], PROMPT_VERSION)

    def test_clarification_and_correction_keep_stated_city_dates_preferences(self):
        for city in CITIES:
            for language in ('zh', 'en'):
                for variant in (0, 1):
                    rows = seeds()
                    clarification = next(r for r in rows if r['sample_id'] == f'f-national-v2/{city[0]}/clarification/{language}/{variant}')
                    self.assertIn('2027', clarification['messages'][-1]['content'])
                    correction = next(r for r in rows if r['sample_id'] == f'f-national-v2/{city[0]}/correction/{language}/{variant}')
                    self.assertIn(city[5] if language == 'zh' else city[6], correction['messages'][-1]['content'])
                    self.assertIn('未知' if language == 'zh' else 'unknown', correction['messages'][-1]['content'])

    def test_distinct_c_public_acceptance_is_not_copied_or_used_as_prompts(self):
        acceptance = load((ROOT / 'eval/lio_national_cases.v1.json').read_bytes())
        self.assertTrue(acceptance['public_acceptance_not_holdout'])
        questions = {t for case in acceptance['cases'] for v in case['variants'].values() for t in v['turns']}
        actual = {m['content'] for r in seeds() for m in r['messages'] if m['role'] == 'user'}
        self.assertFalse(questions & actual)
        self.assertFalse(any('9:00' in t or '9 to 10' in t for t in actual))

    def test_failure_and_cancel_use_shared_detail_not_beijing_search(self):
        rows = seeds()
        for r in rows:
            for m in r['messages']:
                for c in m.get('tool_calls', []):
                    self.assertEqual(c['function']['name'], 'place_detail')
                    self.assertIn('SYNTH_NATIONAL_V2_', load(c['function']['arguments'])['provider_id'])
                    self.assertNotIn('city', load(c['function']['arguments']))
            if r['executions']:
                self.assertEqual(r['executions'][0]['result'], dict(state='unknown', value=None))
                self.assertEqual(r['run']['answer_state'], 'none')

    def test_new_handoff_versions_provenance_and_no_expected_labels_in_sidecars(self):
        output = self.root / 'national'
        report = run_national(output, 'f789-national-v2')
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['admission']['accepted'], 176)
        self.assertEqual(report['generation']['model_requests'], 272)
        self.assertEqual(report['generation']['tool_requests'], 32)
        h = load((output / 'handoff.json').read_bytes())
        self.assertEqual((h['version'], h['candidate_version'], h['data_version']),
                         ('G2C-teacher-handoff.2', 'F789-national-fake.2', DATA_VERSION))
        self.assertEqual(h['record_schema'], 'G2C-dataset.1')
        self.assertEqual(len(h['artifacts']), 17)
        for name, value in h['artifacts'].items():
            self.assertEqual(value['sha256'], sha((output / name).read_bytes()))
        for r in map(load, (output / 'candidates.jsonl').read_bytes().splitlines()):
            self.assertEqual(r['source']['revision'], DATA_VERSION)
            self.assertEqual(r['versions']['prompt'], PROMPT_VERSION)
        for e in map(load, (output / 'models.jsonl').read_bytes().splitlines()):
            self.assertEqual(e['prompt_version'], PROMPT_VERSION)
        inputs = load((output / 'national-inputs.v2.json').read_bytes())
        self.assertEqual(inputs['eligibility'], 'not_authorized_real_task_set')
        self.assertTrue(all(set(t) == {'city', 'language', 'trip_family', 'user_turns'} for t in inputs['tasks'].values()))
        self.assertEqual(h['quality_status'], 'UNRUN')
        self.assertEqual(h['training_status'], 'UNRUN')
        self.assertEqual(h['generation']['real_model_requests'], 0)

    def test_all_rewrites_and_languages_keep_one_group_and_source_lineage(self):
        output = self.root / 'groups'
        run_national(output, 'f789-national-v2')
        rows = {r['sample_id']: r for r in map(load, (output / 'candidates.jsonl').read_bytes().splitlines())}
        uses = {}
        for item in load((output / 'lineage.json').read_bytes()):
            r = rows[item['sample_id']]
            for key in ('task_id', 'trip_family', 'rewrite_family'):
                uses.setdefault((key, r[key]), set()).add((item['group_id'], item['split']))
        self.assertTrue(all(len(v) == 1 for v in uses.values()))
        self.assertEqual(len(load((output / 'handoff.json').read_bytes())['groups']), 40)

    def test_new_version_rebuild_is_identical_and_legacy_profile_is_retained(self):
        run_national(self.root / 'one', 'f789-national-v2')
        run_national(self.root / 'two', 'f789-national-v2')
        self.assertEqual({p.name: p.read_bytes() for p in (self.root / 'one').iterdir()},
                         {p.name: p.read_bytes() for p in (self.root / 'two').iterdir()})
        old = self.root / 'old'
        run_fake(old, 'f789-smoke-v1', cases(), FakeTeacher(), FakeTools())
        h = load((old / 'handoff.json').read_bytes())
        self.assertEqual((h['version'], h['candidate_version']), ('G2C-teacher-handoff.1', 'F789-fake.1'))
        self.assertNotIn('data_version', h)
        self.assertEqual(len(h['artifacts']), 13)
        self.assertEqual(load((old / 'report.json').read_bytes())['generation']['planned'], 21)

    def test_extra_artifacts_cannot_replace_evidence_or_escape_package(self):
        for name in ('tasks.json', 'handoff.json', '../outside.json'):
            with self.assertRaises(ValueError):
                run_fake(self.root / name.replace('/', '_'), 'test', cases(), FakeTeacher(), FakeTools(),
                         extra_artifacts={name: dict(fake='replacement')})

    def test_fake_national_uses_no_network(self):
        with patch('httpx.Client.send', side_effect=AssertionError('no network')), \
                patch('httpx.AsyncClient.send', side_effect=AssertionError('no network')):
            run_national(self.root / 'offline', 'f789-national-v2')


if __name__ == '__main__':
    unittest.main()
