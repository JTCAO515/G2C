"""Public controls for ciphertext integrity and metadata leakage boundaries."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from evaluation.cj028.evaluate import InputError
from .custody import PURPOSE, FINAL_VERSION, age_io, deny_probe, final_metadata, seal
from .score import dataset


class CustodyTests(unittest.TestCase):
    def test_real_age_roundtrip_tamper_and_missing_passphrase(self):
        plain = b'PUBLIC ENCRYPTION CONTROL ONLY'
        password = b'public-test-password-not-a-custody-password'
        ciphertext = age_io(['--encrypt', '--passphrase'], plain, password)
        self.assertEqual(age_io(['--decrypt'], ciphertext, password), plain)
        with self.assertRaises(RuntimeError):
            age_io(['--decrypt'], ciphertext, b'public-deliberately-wrong-password')
        with self.assertRaises(RuntimeError):
            age_io(['--decrypt'], ciphertext[:-1] + bytes([ciphertext[-1] ^ 1]), password)
        with tempfile.TemporaryDirectory(prefix='g2c-public-crypto-control-') as folder:
            path = Path(folder) / 'control.age'
            path.write_bytes(ciphertext)
            manifest = dict(plaintext_sha256=sha256(plain).hexdigest(), ciphertext_sha256=sha256(ciphertext).hexdigest(),
                            purpose=PURPOSE, denominators=dict(tasks=1, zh=1, en=1))
            result = deny_probe(path, 'D', manifest)
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['decrypted_bytes'], 0)
            manifest_path = Path(folder) / 'public-manifest.json'
            manifest_path.write_text(json.dumps(manifest))
            for invalid in (b'', b'PUBLIC NON-CIPHERTEXT CONTROL', ciphertext[:-1]):
                path.write_bytes(invalid)
                wrong = dict(manifest, ciphertext_sha256=sha256(invalid).hexdigest())
                with self.assertRaises(InputError):
                    deny_probe(path, 'D', manifest)
                if not invalid.startswith(b'age-encryption.org/v1'):
                    with self.assertRaises(InputError):
                        deny_probe(path, 'D', wrong)
            path.write_bytes(ciphertext)
            command = subprocess.run(
                [sys.executable, '-B', '-m', 'eval.optimization.custody', 'deny-probe',
                 '--ciphertext', str(path), '--manifest', str(manifest_path), '--session', 'D'], capture_output=True,
            )
            self.assertEqual(command.returncode, 0)
            self.assertNotIn(plain, command.stdout + command.stderr)
            self.assertEqual(json.loads(command.stdout)['status'], 'PASS')

    def test_metadata_contains_only_hash_denominators_and_purpose(self):
        public, _ = dataset()
        sample_plan = json.loads(Path(__file__).with_name('comparison-plan.v1.json').read_text())['samples']
        references = {task['kind']: task for task in public['tasks']}
        tasks = []
        for kind, quantity in sample_plan['task_allocation'].items():
            for index in range(quantity):
                task = deepcopy(references[kind])
                task['id'] = f'PUBLIC-CUSTODY-CONTROL-{kind}-{index}'
                task['trip_family'] = task['id']
                task['split'] = 'final'
                task['known_fields'] = dict(task_clock='2026-11-11', travel=dict(city='Public control',
                                             start_date=None, days=2, daily_budget_cny=100))
                for variant in task['variants'].values():
                    variant['turns'][0] = 'PUBLIC-CUSTODY-CONTROL ' + variant['turns'][0]
                tasks.append(task)
        document = dict(version=FINAL_VERSION, purpose=PURPOSE, tasks=tasks)
        payload = json.dumps(document, ensure_ascii=False).encode()
        metadata = final_metadata(payload)
        self.assertEqual(set(metadata), {'plaintext_sha256', 'purpose', 'denominators'})
        self.assertEqual(metadata['denominators']['zh'], len(tasks))
        self.assertNotIn('PUBLIC-CUSTODY-CONTROL', json.dumps(metadata))
        with tempfile.TemporaryDirectory(prefix='g2c-public-output-control-') as folder:
            output = Path(folder) / 'existing.age'
            output.write_bytes(b'public-existing-artifact')
            with self.assertRaises(InputError):
                seal(payload, output)
            self.assertEqual(output.read_bytes(), b'public-existing-artifact')
            subprocess.run(['git', 'init', '--quiet', folder], check=True, capture_output=True)
            with self.assertRaises(InputError):
                seal(payload, Path(folder) / 'forbidden.age')
            self.assertFalse((Path(folder) / 'forbidden.age').exists())
        for field, bad in (('behavior', {'not_a_scoring_rule': True}), ('state', {'not_a_state_rule': 'PASS'}),
                           ('state', {'plan_context': False})):
            broken = deepcopy(document)
            broken['tasks'][0]['variants']['zh'][field] = bad
            with self.assertRaises(InputError):
                final_metadata(json.dumps(broken).encode())
        clarified = deepcopy(document)
        target = next(task for task in clarified['tasks'] if task['kind'] == 'clarification')
        target['known_fields']['travel']['start_date'] = '2026-11-18'
        with self.assertRaises(InputError):
            final_metadata(json.dumps(clarified).encode())
        with self.assertRaises(InputError):
            final_metadata(json.dumps(dict(document, tasks=tasks[:-1])).encode())
        tasks[0]['trip_family'] = public['tasks'][0]['trip_family']
        with self.assertRaises(InputError):
            final_metadata(json.dumps(document).encode())


if __name__ == '__main__':
    unittest.main()
