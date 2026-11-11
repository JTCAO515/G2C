"""Public controls for ciphertext integrity and metadata leakage boundaries."""
from copy import deepcopy
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
            result = deny_probe(path, 'D')
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['decrypted_bytes'], 0)
            command = subprocess.run(
                [sys.executable, '-B', '-m', 'eval.optimization.custody', 'deny-probe',
                 '--ciphertext', str(path), '--session', 'D'], capture_output=True,
            )
            self.assertEqual(command.returncode, 0)
            self.assertNotIn(plain, command.stdout + command.stderr)
            self.assertEqual(json.loads(command.stdout)['status'], 'PASS')

    def test_metadata_contains_only_hash_denominators_and_purpose(self):
        public, _ = dataset()
        tasks = deepcopy(public['tasks'])
        for task in tasks:
            task['id'] = 'PUBLIC-CUSTODY-CONTROL-' + task['id']
            task['trip_family'] = 'PUBLIC-CUSTODY-CONTROL-' + task['trip_family']
            task['split'] = 'final'
            for variant in task['variants'].values():
                variant['turns'][0] = 'PUBLIC-CUSTODY-CONTROL ' + variant['turns'][0]
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
        tasks[0]['trip_family'] = public['tasks'][0]['trip_family']
        with self.assertRaises(InputError):
            final_metadata(json.dumps(document).encode())


if __name__ == '__main__':
    unittest.main()
