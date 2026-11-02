"""Explicit local cleanup host activation; never resolve a caller plugin path."""
import json
from pathlib import Path
import tempfile
import unittest

from cj_api.local_cleanup import load_configuration


class LocalCleanupConfigurationChecks(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.key=self.root/'cleanup.key'
        self.key.write_bytes(b'K'*32);self.key.chmod(0o600)
        self.path=self.root/'cleanup.json'
        self.value=dict(version='CJ-LOCAL-CLEANUP@1',key_file=str(self.key),key_id='local',
                        lifetime_seconds=3600,inventory=['business/message','external-processing'])

    def load(self,value):
        self.path.write_text(json.dumps(value));return load_configuration(self.path)

    def test_v1_keeps_explicit_old_hook_state_and_inventory(self):
        loaded=self.load(self.value)
        self.assertIsNone(loaded.extra_hooks)
        self.assertEqual(loaded.inventory,tuple(self.value['inventory']))
        self.assertEqual(loaded.keys,{'local':self.key.read_bytes()})

    def test_v2_installs_only_the_named_code_owned_factory(self):
        from cj_memory_withdrawal.account_cleanup import account_hooks
        loaded=self.load(self.value|dict(version='CJ-LOCAL-CLEANUP@2'))
        self.assertIs(loaded.extra_hooks,account_hooks)
        self.assertEqual(loaded.inventory,tuple(self.value['inventory']))
        self.assertEqual(loaded.registry_path.name,'storage-registry.json')

    def test_unknown_versions_or_hook_selectors_and_bad_keys_fail(self):
        for value in (self.value|dict(version='CJ-LOCAL-CLEANUP@3'),
                      self.value|dict(version='CJ-LOCAL-CLEANUP@2',extra_hooks='caller.module'),
                      {k:v for k,v in self.value.items() if k!='inventory'}):
            with self.subTest(fields=tuple(value)),self.assertRaises(ValueError):self.load(value)
        for version in ('CJ-LOCAL-CLEANUP@1','CJ-LOCAL-CLEANUP@2'):
            self.key.chmod(0o644)
            with self.subTest(version=version),self.assertRaises(ValueError):self.load(self.value|dict(version=version))
            self.key.chmod(0o600);self.key.write_bytes(b'wrong-length')
            with self.subTest(version=version),self.assertRaises(ValueError):self.load(self.value|dict(version=version))
            self.key.write_bytes(b'K'*32)


if __name__=='__main__':unittest.main()
