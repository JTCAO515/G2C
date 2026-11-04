"""Approved cleanup composition; offline only, never touches a cloud credential."""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import os
import unittest

from cj_api.supabase_test_database import HOST,REF
from cj_api.supabase_cleanup import SupabaseCleanupConfiguration,SupabaseCleanupRuntime
from cj_api.local_cleanup import Configuration
from cj_api.composition import CompositionUnavailable
from psycopg.pq import TransactionStatus


class CloudCleanupBoundaries(unittest.TestCase):
    def configuration(self,guard):
        base=Configuration({'synthetic':b'01234567890123456789012345678901'},'synthetic',3600,('business/message',),Path('synthetic-registry'))
        return SupabaseCleanupConfiguration(base,'postgresql://cj_local_cleanup.'+REF+':synthetic-only@'+HOST+':5432/postgres',Path('synthetic-ca'),guard)

    def test_missing_transaction_barrier_is_rejected(self):
        with self.assertRaises(ValueError):self.configuration(None)

    def test_cleanup_connection_must_have_own_login_and_database_tls(self):
        with patch.dict(os.environ,{'CJ_ENV':'local'},clear=True):
            config=self.configuration(lambda cursor:None)
            with patch('cj_api.supabase_cleanup.Runtime.__init__',return_value=None):runtime=SupabaseCleanupRuntime(None,config,None)
            connection=MagicMock();connection.execute.return_value.fetchone.return_value=('cj_m1_runtime','cj_m1_runtime',True)
            with patch('cj_api.supabase_cleanup.pin_ca',return_value=nullcontext(SimpleNamespace(name='synthetic-ca'))),patch('cj_api.supabase_cleanup.psycopg.connect',return_value=connection):
                with self.assertRaises(CompositionUnavailable):runtime.connect()
            connection.close.assert_called_once()
            sql=connection.execute.call_args.args[0]
            self.assertNotIn('set_config',sql);self.assertNotIn('SET ROLE',sql)

    def test_original_store_checks_release_before_installing_cleanup_scope(self):
        events=[]
        def guard(cursor):events.append('barrier');raise ValueError('synthetic source not released')
        with patch.dict(os.environ,{'CJ_ENV':'local'},clear=True):
            config=self.configuration(guard)
            with patch('cj_api.supabase_cleanup.Runtime.__init__',return_value=None):runtime=SupabaseCleanupRuntime(None,config,None)
        connection=MagicMock();connection.autocommit=False;connection.info.transaction_status=TransactionStatus.IDLE
        with patch.object(runtime,'connect',return_value=connection):
            store=runtime.store('a'*64)
            with self.assertRaises(ValueError):
                with store.transaction('synthetic-original'):self.fail('unreleased cleanup yielded authority')
        self.assertEqual(events,['barrier']);connection.commit.assert_not_called();connection.rollback.assert_called_once()
        connection.cursor.return_value.__enter__.return_value.execute.assert_not_called()


if __name__=='__main__':unittest.main()
