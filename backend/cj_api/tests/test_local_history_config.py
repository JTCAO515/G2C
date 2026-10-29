"""Local history key/configuration boundary, without database or external services."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cj_api.local_app import CompositionUnavailable, load_history_configuration, app_from_environment

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('local_history_dev_auth', ROOT / 'scripts/dev_auth.py')
dev_auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev_auth)


class LocalHistoryConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.key = self.directory / 'history-cursor.key'
        self.env = patch.dict(os.environ, {'CJ_ENV': 'local'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_create_and_preserve_existing_key(self):
        dev_auth.history_key(self.directory)
        original = self.key.read_bytes()
        self.assertEqual(len(original), 32)
        self.assertEqual(self.key.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(SystemExit):
            dev_auth.history_key(self.directory)
        self.assertEqual(self.key.read_bytes(), original)
        config = load_history_configuration(self.directory)
        self.assertEqual((config.max_page_limit, config.max_draft_bytes, config.max_private_response_bytes),
                         (20, 16384, 1_000_000))
        self.assertEqual((config.cursor_policy.ttl_seconds, config.cursor_policy.max_token_bytes), (300, 2048))

    def test_missing_and_invalid_length_fail(self):
        with self.assertRaises(CompositionUnavailable):
            load_history_configuration(self.directory)
        for length in (0, 31, 33, 4096):
            self.key.write_bytes(b'x' * length)
            self.key.chmod(0o600)
            with self.subTest(length=length), self.assertRaises(CompositionUnavailable):
                load_history_configuration(self.directory)

    def test_modes_and_symlink_rejected(self):
        self.key.write_bytes(b'x' * 32)
        for mode in (0o644, 0o660, 0o400, 0o700, 0o1600):
            self.key.chmod(mode)
            with self.subTest(mode=mode), self.assertRaises(CompositionUnavailable):
                load_history_configuration(self.directory)
        self.key.unlink()
        target = self.directory / 'target'
        target.write_bytes(b'y' * 32)
        target.chmod(0o600)
        self.key.symlink_to(target)
        with self.assertRaises(CompositionUnavailable):
            load_history_configuration(self.directory)
        with self.assertRaises(SystemExit):
            dev_auth.history_key(self.directory)
        self.assertEqual(target.read_bytes(), b'y' * 32)

    def test_nonlocal_rejected_before_creation_or_loading(self):
        for environment in ('production', ''):
            with patch.dict(os.environ, {'CJ_ENV': environment}):
                with self.assertRaises(SystemExit):
                    dev_auth.history_key(self.directory)
                with self.assertRaises(SystemExit):
                    dev_auth.init(self.directory, ['alice'])
                with self.assertRaises(CompositionUnavailable):
                    load_history_configuration(self.directory)
                with self.assertRaises(CompositionUnavailable):
                    app_from_environment()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_init_keys_are_distinct(self):
        dev_auth.init(self.directory, ['alice'])
        self.assertNotEqual(self.key.read_bytes(), (self.directory / 'trip-confirmation.key').read_bytes())
        self.assertNotEqual(self.key.read_bytes(), (self.directory / 'private.pem').read_bytes())
        self.assertEqual(self.key.stat().st_mode & 0o777, 0o600)
