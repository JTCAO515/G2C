"""Offline configuration/activation boundaries; no Keychain or real DB."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch,MagicMock

from cj_api.composition import CompositionUnavailable
from cj_api.supabase_test_database import decode_uri,SupabaseTestDatabase,HOST,REF


def uri(**changes):
    values=dict(user='cj_m1_runtime.'+REF,host=HOST,port='5432',dbname='postgres')
    values.update(changes)
    return 'postgresql://'+values['user']+':synthetic-only@'+values['host']+':'+values['port']+'/'+values['dbname']


class SupabaseBoundaries(unittest.TestCase):
    def test_session_fixed_project_runtime_only(self):
        with patch.dict(os.environ,dict(CJ_ENV='local'),clear=True):
            config=decode_uri(uri())
            self.assertEqual(config['sslmode'],'verify-full')
            for change in (dict(port='6543'),dict(host='other.invalid'),dict(user='postgres.'+REF),dict(dbname='other')):
                with self.subTest(change=change),self.assertRaises(CompositionUnavailable):decode_uri(uri(**change))
            self.assertEqual(decode_uri(uri(user='postgres.'+REF),operator=True)['user'],'postgres.'+REF)
    def test_dsn_alias_and_ambient_pg_refused(self):
        with patch.dict(os.environ,dict(CJ_ENV='local'),clear=True):
            for suffix in ('?hostaddr=127.0.0.1','?service=other','?options=-crole%3Dpostgres','?sslmode=disable'):
                with self.subTest(suffix=suffix),self.assertRaises(CompositionUnavailable):decode_uri(uri()+suffix)
        with patch.dict(os.environ,dict(CJ_ENV='local',PGHOST='other'),clear=True),self.assertRaises(CompositionUnavailable):decode_uri(uri())
    def test_unencrypted_or_wrong_role_never_reset_or_reach_business(self):
        for identity in (('cj_m1_runtime',False),('postgres',True),None):
            obj=SupabaseTestDatabase.__new__(SupabaseTestDatabase);obj._ca=None;obj._empty_passfile=None;obj.conninfo={}
            connection=MagicMock();connection.execute.return_value.fetchone.return_value=identity
            with patch('cj_api.supabase_test_database.psycopg.connect',return_value=connection),self.assertRaises(CompositionUnavailable):obj._open_runtime_connection()
            connection.close.assert_called_once()
            self.assertEqual(connection.execute.call_count,1)
    def test_tls_runtime_discards_and_checks_clean_authority(self):
        obj=SupabaseTestDatabase.__new__(SupabaseTestDatabase);obj._ca=None;obj._empty_passfile=None;obj.conninfo={}
        connection=MagicMock();connection.execute.return_value.fetchone.return_value=('cj_m1_runtime',True)
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value=(None,)*9
        with patch('cj_api.supabase_test_database.psycopg.connect',return_value=connection):
            self.assertIs(obj._open_runtime_connection(),connection)
        self.assertEqual(connection.execute.call_args_list[1].args,('DISCARD ALL',))
        connection.close.assert_not_called()


if __name__=='__main__':unittest.main()
