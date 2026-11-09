"""Offline configuration/activation boundaries; no Keychain or real DB."""
import os
from datetime import datetime,timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch,MagicMock

from cj_api.composition import CompositionUnavailable
from cj_api.supabase_test_database import decode_uri,SupabaseTestDatabase,HOST,REF
from cj_api import supabase_test_database as boundary
from cj_api.local_app import create_local_app


def uri(**changes):
    values=dict(user='cj_m1_runtime.'+REF,host=HOST,port='5432',dbname='postgres')
    values.update(changes)
    return 'postgresql://'+values['user']+':synthetic-only@'+values['host']+':'+values['port']+'/'+values['dbname']


class SupabaseBoundaries(unittest.TestCase):
    def setUp(self):
        self.time=patch.object(boundary,'datetime',SimpleNamespace(now=lambda tz:datetime(2026,11,4,tzinfo=timezone.utc)))
        self.time.start();self.addCleanup(self.time.stop)
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

    def test_hk_socket_role_and_transport_are_explicit(self):
        base='postgresql://cj_m1_runtime:'+('a'*43)+'@/postgres?host=%2Frun%2Fg2c-pg&port=5432&sslmode=disable'
        with patch.dict(os.environ,dict(CJ_ENV='local'),clear=True):
            self.assertEqual(boundary.decode_hk_socket_uri(base,'cj_m1_runtime')['host'],boundary.HK_SOCKET)
            for changed in (base.replace('%2Frun%2Fg2c-pg','127.0.0.1'),base.replace('5432','6543'),
                            base.replace('disable','require'),base+'&hostaddr=127.0.0.1',
                            base.replace('cj_m1_runtime','cj_local_cleanup'),base.replace('a'*43,'weak')):
                with self.assertRaises(CompositionUnavailable):
                    boundary.decode_hk_socket_uri(changed,'cj_m1_runtime')
            with self.assertRaises(CompositionUnavailable):decode_uri(base)

    def test_hk_socket_refuses_network_or_role_drift_before_reset(self):
        for row in (('cj_m1_runtime','cj_m1_runtime','127.0.0.1',''),
                    ('cj_m1_runtime','cj_m1_runtime',None,'*'),('cj_m1_runtime','cj',None,'')):
            connection=MagicMock()
            connection.execute.return_value.fetchone.return_value=row
            with patch.dict(os.environ,dict(CJ_ENV='local'),clear=True),self.assertRaises(CompositionUnavailable):
                boundary.prepare_hk_socket_session(connection,'cj_m1_runtime')
            self.assertEqual(connection.execute.call_count,1)
    def test_unencrypted_or_wrong_role_never_reset_or_reach_business(self):
        for identity in (('cj_m1_runtime','cj_m1_runtime',False),('postgres','postgres',True),('cj_m1_runtime','postgres',True),None):
            obj=SupabaseTestDatabase.__new__(SupabaseTestDatabase);obj._ca=None;obj._empty_passfile=None;obj.conninfo={}
            connection=MagicMock();connection.execute.return_value.fetchone.return_value=identity
            with patch('cj_api.supabase_test_database.psycopg.connect',return_value=connection),self.assertRaises(CompositionUnavailable):obj._open_runtime_connection()
            connection.close.assert_called_once()
            self.assertEqual(connection.execute.call_count,1)
    def test_tls_runtime_discards_and_checks_clean_authority(self):
        obj=SupabaseTestDatabase.__new__(SupabaseTestDatabase);obj._ca=None;obj._empty_passfile=None;obj.conninfo={}
        connection=MagicMock();connection.execute.return_value.fetchone.return_value=('cj_m1_runtime','cj_m1_runtime',True)
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value=(None,)*9
        with patch('cj_api.supabase_test_database.psycopg.connect',return_value=connection):
            self.assertIs(obj._open_runtime_connection(),connection)
        self.assertEqual(connection.execute.call_args_list[1].args,('DISCARD ALL',))
        connection.close.assert_not_called()

    def test_reset_identity_drift_and_late_environment_are_refused(self):
        obj=SupabaseTestDatabase.__new__(SupabaseTestDatabase);obj._ca=None;obj._empty_passfile=None;obj.conninfo={}
        connection=MagicMock();connection.execute.return_value.fetchone.side_effect=[('cj_m1_runtime','cj_m1_runtime',True),('postgres','postgres',True)]
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value=(None,)*9
        with patch('cj_api.supabase_test_database.psycopg.connect',return_value=connection),self.assertRaises(CompositionUnavailable):obj._open_runtime_connection()
        connection.close.assert_called_once()
        with patch.dict(os.environ,dict(CJ_ENV='local',PGHOSTADDR='127.0.0.1'),clear=True),patch('cj_api.supabase_test_database.psycopg.connect') as connect,self.assertRaises(CompositionUnavailable):obj._open_runtime_connection()
        connect.assert_not_called()

    def test_cloud_local_cleanup_combination_is_closed(self):
        obj=SupabaseTestDatabase.__new__(SupabaseTestDatabase);obj._ca=None;obj._empty_passfile=None
        with patch.dict(os.environ,dict(CJ_ENV='local'),clear=True),self.assertRaisesRegex(CompositionUnavailable,'cleanup identity'):
            create_local_app(conninfo_path=None,auth_dir='unused',database=obj,cleanup_configuration=object())

    def test_authorization_expiry_is_checked(self):
        with patch.object(boundary,'datetime',SimpleNamespace(now=lambda tz:datetime(2026,12,1,tzinfo=timezone.utc))),patch.dict(os.environ,dict(CJ_ENV='local'),clear=True),self.assertRaises(CompositionUnavailable):decode_uri(uri())


if __name__=='__main__':unittest.main()
