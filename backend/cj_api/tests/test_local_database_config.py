"""Local runtime DB configuration must never inherit old provider/credential routes."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cj_api.local_app import LocalDatabase
from cj_api.composition import CompositionUnavailable


class LocalDatabaseConfigTests(unittest.TestCase):
    def test_explicit_unix_configuration_drops_initializer_credentials(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'CJ_ENV': 'local'}, clear=True):
            path = Path(root) / 'conn.json'
            path.write_text(json.dumps(dict(host=root, user='initializer', password='synthetic-only', passfile='old-cache')))
            with patch('psycopg.connect', side_effect=AssertionError('construction must not connect')):
                database = LocalDatabase(path)
            self.assertEqual(database.conninfo['user'], 'cj_m1_runtime')
            passfile = Path(database.conninfo['passfile'])
            self.assertEqual(passfile.read_bytes(), b'')
            self.assertEqual(passfile.stat().st_mode & 0o777, 0o600)
            self.assertNotEqual(str(passfile), 'old-cache')
            self.assertNotIn('password', database.conninfo)

    def test_remote_service_and_ambient_libpq_routes_fail_before_connection(self):
        with tempfile.TemporaryDirectory() as root, patch('psycopg.connect', side_effect=AssertionError('network forbidden')):
            path = Path(root) / 'conn.json'
            cases = [({'host': 'db.invalid'}, {}), ({'host': root, 'hostaddr': '192.0.2.1'}, {}),
                     ({'host': root, 'service': 'old-service'}, {}), ({'host': root}, {'PGHOSTADDR': '192.0.2.1'}),
                     ({'host': root}, {'PGPASSWORD': 'synthetic-old'}), ({'host': root}, {'CJ_ENV': 'production'})]
            for config, extra in cases:
                with self.subTest(config=config, keys=tuple(extra)), patch.dict(os.environ, {'CJ_ENV': 'local', **extra}, clear=True):
                    path.write_text(json.dumps(config))
                    with self.assertRaises(CompositionUnavailable): LocalDatabase(path)
