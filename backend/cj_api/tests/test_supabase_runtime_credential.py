"""Credential operator boundaries; no real Keychain or cloud access."""
import json
import hashlib
import os
from datetime import datetime,timezone
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch,MagicMock

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
import supabase_runtime_credential as operator
from cj_api.supabase_test_database import HOST,REF
from cj_api import supabase_test_database as boundary
from cj_api.composition import CompositionUnavailable


class CredentialBoundaries(unittest.TestCase):
    def setUp(self):
        self.time=patch.object(boundary,'datetime',SimpleNamespace(now=lambda tz:datetime(2026,11,4,tzinfo=timezone.utc)))
        self.time.start();self.addCleanup(self.time.stop)
    def test_unknown_existing_change_is_read_only_not_new_password(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(operator,'ROOT',Path(directory)):
            state=dict(state='PASSWORD_CHANGE_UNKNOWN',project_ref=REF,role='cj_m1_runtime',credential_sha256='a'*64,sql_change_attempts=1)
            (Path(directory)/'state.json').write_text(json.dumps(state))
            with patch.object(operator,'inspect',return_value={'verified_original':True}) as inspect,patch.object(operator.subprocess,'run') as keychain,patch.object(operator.psycopg,'connect') as connect:
                result=operator.apply(Path('synthetic-ca'))
                self.assertEqual(result['mode'],'READ_ONLY_ORIGINAL')
                inspect.assert_called_once();keychain.assert_not_called();connect.assert_not_called()

    def test_database_side_plaintext_blocks_key_creation_and_password_change(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(operator,'ROOT',Path(directory)),patch.dict(os.environ,{'CJ_ENV':'local'},clear=True):
            conn=MagicMock();conn.execute.return_value.fetchone.return_value=(False,)
            uri='postgresql://postgres.'+REF+':synthetic-operator@'+HOST+':5432/postgres'
            pinned=MagicMock();pinned.__enter__.return_value=SimpleNamespace(name='synthetic-pinned-ca')
            with patch.object(operator,'pin_ca',return_value=pinned),patch.object(operator,'keychain',return_value=uri),patch.object(operator.subprocess,'run',return_value=SimpleNamespace(returncode=44)) as keychain,patch.object(operator.psycopg,'connect') as connect:
                connect.return_value.__enter__.return_value=conn
                with self.assertRaises(CompositionUnavailable):operator.apply(Path('synthetic-ca'))
            conn.pgconn.encrypt_password.assert_not_called()
            self.assertEqual(conn.execute.call_count,1)
            self.assertEqual(keychain.call_count,1)
            self.assertFalse((Path(directory)/'state.json').exists())

    def test_role_membership_or_ownership_drift_is_checked_before_mutation(self):
        safe=[True,False,False,False,False,False,False,False,False,0]
        for index in (1,2,3,4,5,6,7,8,9):
            row=list(safe);row[index]=True if index<9 else 1
            conn=MagicMock();conn.execute.return_value.fetchone.return_value=tuple(row)
            with self.subTest(index=index),self.assertRaisesRegex(ValueError,'restricted_runtime_role'):operator.role_safety(conn)
            conn.pgconn.encrypt_password.assert_not_called()

    def test_credential_readback_requires_database_TLS(self):
        uri='postgresql://cj_m1_runtime.'+REF+':synthetic-runtime@'+HOST+':5432/postgres'
        state={'credential_sha256':hashlib.sha256(uri.encode()).hexdigest()}
        conn=MagicMock();conn.execute.return_value.fetchone.return_value=('cj_m1_runtime','cj_m1_runtime',False)
        pinned=MagicMock();pinned.__enter__.return_value=SimpleNamespace(name='synthetic-pinned-ca')
        with patch.dict(os.environ,{'CJ_ENV':'local'},clear=True),patch.object(operator,'pin_ca',return_value=pinned),patch.object(operator,'keychain',return_value=uri),patch.object(operator.psycopg,'connect') as connect:
            connect.return_value.__enter__.return_value=conn
            with self.assertRaises(CompositionUnavailable):operator.inspect(Path('synthetic-ca'),state)


if __name__=='__main__':unittest.main()
