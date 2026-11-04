"""Credential operator boundaries; no real Keychain or cloud access."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch,MagicMock

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
import supabase_runtime_credential as operator
from cj_api.supabase_test_database import HOST,REF


class CredentialBoundaries(unittest.TestCase):
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
                with self.assertRaisesRegex(ValueError,'database_side_TLS_required'):operator.apply(Path('synthetic-ca'))
            conn.pgconn.encrypt_password.assert_not_called()
            self.assertEqual(conn.execute.call_count,1)
            self.assertEqual(keychain.call_count,1)
            self.assertFalse((Path(directory)/'state.json').exists())


if __name__=='__main__':unittest.main()
