"""Admission behavior, artifact integrity and fail-closed configuration checks."""
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
import json

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/check-empty-db-init.py'
spec = importlib.util.spec_from_file_location('init_check', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InitializationTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(module.PLAN.read_text())

    def test_exact_accepted_sources_and_manifest(self):
        module.validate_sources(ROOT, self.plan)

    def test_tampered_hash_and_dependency_and_duplicate_refused(self):
        mutations = [lambda p: p['artifacts'][1].update(sha256='0'*64),
                     lambda p: p['artifacts'][1].update(sql_requires_artifact=['usage']),
                     lambda p: p['artifacts'].append(copy.deepcopy(p['artifacts'][1])),
                     lambda p: p.update(apply_enabled=True)]
        for mutate in mutations:
            plan = copy.deepcopy(self.plan)
            mutate(plan)
            with self.assertRaises(ValueError):
                module.validate_sources(ROOT, plan)

    def test_empty_repeat_and_nonempty_catalog(self):
        module.classify(dict(initialized=False, objects=False))
        for initialized, objects in [(True, True), (True, False), (False, True)]:
            with self.assertRaises(ValueError):
                module.classify(dict(initialized=initialized, objects=objects))

    def test_missing_config_and_apply_option_rejected(self):
        for args in [[], ['--source-repo', str(ROOT), '--inspect-target'],
                     ['--source-repo', str(ROOT), '--apply']]:
            result = subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                                    capture_output=True)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
