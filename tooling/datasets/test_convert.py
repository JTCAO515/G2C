from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from .convert import VERSION, canonical, convert, load, partition, sha, write_release
from .samples import examples, negative_examples, partial_failure


def batch(rows):
    return ''.join(canonical(row) + '\n' for row in rows).encode()


class DatasetTests(unittest.TestCase):
    def test_sample_release_and_negative_controls(self):
        positive = Path('tooling/datasets/samples.v1.jsonl').read_bytes()
        negative = Path('tooling/datasets/negative.v1.jsonl').read_bytes()
        self.assertEqual(positive, batch(examples()))
        self.assertEqual(negative, batch(negative_examples(examples())) +
                         b'{"version":"G2C-dataset.1","version":"duplicate"}\n{broken json\n')
        output, lineage, rejected, groups, report = convert(positive)
        self.assertEqual((report['accepted'], report['rejected']), (20, 0))
        self.assertTrue(all(output[s] for s in output))
        self.assertEqual(len(groups), 10)
        self.assertEqual(len(lineage), 20)
        self.assertEqual(rejected, [])
        result = convert(negative)
        self.assertEqual((result[-1]['accepted'], result[-1]['rejected']), (0, 14))
        self.assertEqual(result[-1]['status'], 'FAIL')

    def test_transitive_family_task_and_rewrite_links_precede_split(self):
        rows = deepcopy(examples()[:4])
        rows[1]['trip_family'] = rows[0]['trip_family']
        rows[2]['task_id'] = rows[1]['task_id']
        rows[3]['rewrite_family'] = rows[2]['rewrite_family']
        grouped = partition(rows, VERSION)
        self.assertEqual(len({(group, split) for _, group, split in grouped}), 1)

    def test_duplicate_content_connects_different_trips_and_keeps_lineage(self):
        a = examples()[0]
        b = deepcopy(a)
        b.update(sample_id='copy', task_id='other-task', trip_family='other-trip', rewrite_family='other-rewrite')
        b['source']['source_id'] = 'copy-source'
        output, lineage, rejected, groups, report = convert(batch([a, b]))
        self.assertEqual((report['accepted'], report['duplicates']), (1, 1))
        self.assertEqual(len({x['group_id'] for x in lineage}), 1)
        self.assertEqual(len({x['retained_sample_id'] for x in lineage}), 1)
        self.assertEqual({x['source']['source_id'] for x in lineage}, {a['source']['source_id'], 'copy-source'})
        self.assertEqual(rejected, [])

    def test_reorder_has_same_splits_and_content(self):
        rows = examples()
        a = convert(batch(rows))
        b = convert(batch(list(reversed(rows))))
        self.assertEqual(a[0], b[0])
        self.assertEqual(a[3:], b[3:])

    def test_ambiguous_sample_ids_reject_all_not_first_wins(self):
        a = examples()[0]
        b = deepcopy(a)
        b['messages'][0]['content'] = 'different input'
        result = convert(batch([a, b]))
        self.assertEqual(result[-1]['accepted'], 0)
        self.assertEqual([r['reason'] for r in result[2]], ['sample_id_collision'] * 2)

    def test_unknown_empty_and_failure_stay_distinct(self):
        rows = examples()
        empty = next(r for r in rows if r['task_id'] == 'f768-empty')
        payload = load(empty['executions'][0]['result']['value'])
        self.assertEqual((payload['outcome'], payload['places']), ('no_results', []))
        present = next(r for r in rows if r['task_id'] == 'f768-result')
        place = load(present['executions'][0]['result']['value'])['places'][0]
        self.assertEqual(place['address_zh'], dict(state='empty_array', value=None))
        self.assertEqual(place['official_name_en'], dict(state='unknown', value=None))
        unknown = next(r for r in rows if r['task_id'] == 'f768-unknown')
        failed = next(r for r in rows if r['task_id'] == 'f768-failure')
        self.assertEqual(unknown['executions'][0]['result'], dict(state='unknown', value=None))
        self.assertEqual(failed['executions'][0]['status'], 'failed')
        result = convert(batch([empty, present, unknown, failed]))
        self.assertEqual(result[-1]['rejected'], 0)
        self.assertEqual(sum(map(len, result[0].values())), 4)

    def test_domain_exceptions_reject_rows_without_aborting_batch(self):
        r = next(r for r in examples() if r['scenario'] == 'tool_failure')
        route = deepcopy(r)
        route['sample_id'] = 'bad-route'
        route['messages'][1]['tool_calls'][0]['function'] = dict(name='place_route', arguments=canonical(dict(
            origin_provider_id='x', origin_coordinate='invalid', origin_coordinate_role='poi_center',
            destination_provider_id='y', destination_coordinate='116.1,39.1',
            destination_coordinate_role='poi_center', mode='walking')))
        fact = deepcopy(r)
        fact['sample_id'] = 'bad-fact'
        fact['messages'][1]['tool_calls'][0]['function'] = dict(name='fact', arguments=canonical(dict(
            start_date='2026-11-12', end_date='2026-11-11')))
        result = convert(batch([route, fact, examples()[0]]))
        self.assertEqual((result[-1]['accepted'], result[-1]['rejected']), (1, 2))

    def test_old_receipt_and_source_binding_rejected(self):
        r = next(r for r in examples() if r['scenario'] == 'tool_result')
        value = load(r['executions'][0]['result']['value'])
        value['source']['request_ref'] = 'another-operation'
        r['executions'][0]['result']['value'] = canonical(value)
        tool = load(r['messages'][2]['content'])
        tool['results'][0]['result'] = value
        r['messages'][2]['content'] = canonical(tool)
        self.assertEqual(convert(batch([r]))[2][0]['reason'], 'result_receipt_association')

    def test_original_bytes_and_native_call_ids_preserved(self):
        rows = examples()
        output = convert(batch(rows))[0]
        by_id = {r['sample_id']: r for split in output.values() for r in split}
        self.assertEqual(by_id, {r['sample_id']: r for r in rows})

    def test_partial_batch_keeps_actual_result_out_of_model_messages(self):
        row = partial_failure('en')
        self.assertEqual([m['role'] for m in row['messages']], ['user', 'assistant'])
        self.assertEqual([e['status'] for e in row['executions']], ['received', 'unknown'])
        self.assertEqual(convert(batch([row]))[-1]['accepted'], 1)
        row['run']['status'] = 'completed'
        self.assertEqual(convert(batch([row]))[-1]['accepted'], 0)

    def test_supplier_id_matches_original_b_boundary(self):
        row = next(r for r in examples() if r['scenario'] == 'tool_failure')
        row['messages'][1]['tool_calls'][0]['id'] = 'contains spaces'
        self.assertEqual(convert(batch([row]))[2][0]['reason'], 'schema_invalid')

    def test_manifest_digests_reproducibility_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.jsonl'
            source.write_bytes(batch(examples()))
            for name in ('a', 'b'):
                write_release(source, root / name, VERSION)
            self.assertEqual({p.name: p.read_bytes() for p in (root / 'a').iterdir()},
                             {p.name: p.read_bytes() for p in (root / 'b').iterdir()})
            manifest = json.loads((root / 'a/manifest.json').read_text())
            for name, metadata in manifest['artifacts'].items():
                self.assertEqual(metadata['sha256'], sha((root / 'a' / name).read_bytes()))
            self.assertEqual(manifest['input_sha256'], sha(source.read_bytes()))
            with self.assertRaises(FileExistsError):
                write_release(source, root / 'a', VERSION)


if __name__ == '__main__':
    unittest.main()
