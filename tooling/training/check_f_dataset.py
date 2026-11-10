"""Integration against F's actual synthetic corpus. Use the root locked env.

This file is separate from isolated ms-swift unit tests: importing F requires
the existing root domain dependencies, not new copies in the training env.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from f_dataset import VERSION, check_dataset
from tooling.datasets import convert as f
from tooling.datasets.samples import examples


class FConsumerTests(unittest.TestCase):
    def check_rows(self, rows, version=VERSION, expected_hash=None):
        with tempfile.TemporaryDirectory(prefix='g2c-g-f-check-') as directory:
            path = Path(directory) / 'input.jsonl'
            raw = ''.join(f.canonical(row) + '\n' for row in rows).encode()
            path.write_bytes(raw)
            return check_dataset(path, version, expected_hash or hashlib.sha256(raw).hexdigest())

    def test_actual_f_corpus_preserves_split_and_controls(self):
        rows = examples()
        result, code = self.check_rows(rows)
        expected = f.convert(''.join(f.canonical(row) + '\n' for row in rows).encode(), VERSION)[-1]
        self.assertEqual(code, 0)
        self.assertEqual(result['report'], expected)
        self.assertEqual(result['report']['accepted'], 22)
        self.assertEqual(result['report']['split_counts'], {'train': 18, 'validation': 2, 'test': 2})
        self.assertGreater(sum(result['control_only_counts'].values()), 0)
        self.assertEqual(result['training_readiness'], 'UNRUN')
        self.assertEqual(result['formal_data_quality'], 'UNKNOWN')

    def test_missing_field_rejected_by_f(self):
        row = deepcopy(examples()[0])
        del row['source']
        result, code = self.check_rows([row])
        self.assertEqual(code, 1)
        self.assertEqual(result['report']['accepted'], 0)
        self.assertEqual(result['rejections'][0]['reason'], 'schema_invalid')

    def test_wrong_tool_receipt_rejected_by_f(self):
        row = next(deepcopy(row) for row in examples() if any(
            message['role'] == 'tool' for message in row['messages']))
        tool = next(message for message in row['messages'] if message['role'] == 'tool')
        tool['tool_call_id'] = 'another-call'
        result, code = self.check_rows([row])
        self.assertEqual(code, 1)
        self.assertEqual(result['rejections'][0]['reason'], 'tool_result_association')

    def test_unknown_version_and_mismatched_input_pin(self):
        result, code = self.check_rows(examples(), version='invented-v2')
        self.assertEqual((code, result['code']), (2, 'UNKNOWN_DATA_VERSION'))
        result, code = self.check_rows(examples(), expected_hash='0' * 64)
        self.assertEqual((code, result['code']), (1, 'INPUT_SHA256_MISMATCH'))
        result, code = self.check_rows([])
        self.assertEqual((code, result['code']), (1, 'EMPTY_DATASET'))

    def test_changed_schema_is_rejected_before_f_import(self):
        with tempfile.TemporaryDirectory(prefix='g2c-g-pin-check-') as directory:
            root = Path(directory)
            training, datasets = root / 'tooling/training', root / 'tooling/datasets'
            training.mkdir(parents=True)
            datasets.mkdir(parents=True)
            for name in ('preflight.py', 'f_dataset.py'):
                shutil.copyfile(Path(__file__).with_name(name), training / name)
            for name in ('__init__.py', 'convert.py'):
                shutil.copyfile(f.HERE / name, datasets / name)
            (datasets / 'schema.v1.json').write_text('{invalid JSON')
            command = [sys.executable, '-B', str(training / 'preflight.py'), 'dataset',
                       str(f.HERE / 'samples.v1.jsonl'), '--version', VERSION,
                       '--input-sha256', hashlib.sha256((f.HERE / 'samples.v1.jsonl').read_bytes()).hexdigest()]
            result = subprocess.run(command, capture_output=True, text=True, cwd=root)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(json.loads(result.stdout)['code'], 'UNREVIEWED_F_REVISION')


if __name__ == '__main__':
    unittest.main()
