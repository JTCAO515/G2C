"""L1 disposable PG: real owner deletion producers -> backup/recovery gates."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ['CJ_ENV'] = 'local'
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'backend/cj_api/tests'),
                str(ROOT / 'backend/memory_withdrawal/tests')]

import psycopg
from fastapi.testclient import TestClient
import migrate
import pg_suites
from deploy import recovery
from deploy.entrypoint import schema
from cj_cleanup.coordinator import Coordinator
from cj_api.local_app import ISSUER, LocalDatabase, scope_for
from account_retention_pg import main as account_exercise
from manual_history_erasure_pg import exercise as memory_exercise


def main():
    with tempfile.TemporaryDirectory(prefix='g2c-recovery-') as directory:
        root = Path(directory)
        control = root / 'control'
        control.mkdir()
        secret = root / 'recovery.key'
        secret.write_bytes(os.urandom(32))
        secret.chmod(0o600)
        os.environ['CJ_DEPLOY_RECOVERY_KEY_FILE'] = str(secret)
        os.environ['PATH'] = str(pg_suites.bindir()) + os.pathsep + os.environ['PATH']
        with pg_suites.cluster('deploy-recovery', port=55865, role='cj_recovery_operator',
                              root=root / 'pg', socket=root / 's') as config:
            path = root / 'conn.json'
            path.write_text(json.dumps(config))
            with psycopg.connect(**config, autocommit=True) as conn:
                chain = migrate.load()
                migrate.up(conn, chain, chain[-1]['version'])
            account_root, memory_root = root / 'account', root / 'memory'
            account_root.mkdir()
            memory_root.mkdir()
            base, safety = root / 'base', root / 'safety'
            captured = []
            original_post, original_create = TestClient.post, Coordinator.create

            def post(client, url, *args, **kwargs):
                if url == '/v1/memory-erasures' and not captured:
                    with psycopg.connect(**config) as conn:
                        assert conn.execute("SELECT count(*) FROM cj_memory_item WHERE item_id='explicit-item'").fetchone() == (1,)
                        assert conn.execute('SELECT count(*) FROM cj_account_fence').fetchone() == (0,)
                        assert conn.execute('SELECT count(*) FROM cj_message_receipt').fetchone()[0] > 1
                    recovery.backup(config, base, control)
                    captured.append(True)
                return original_post(client, url, *args, **kwargs)

            def create(coordinator, operation, *args, **kwargs):
                if operation == 'real-b-domain-erasure':
                    with patch.object(TestClient, 'post', post):
                        memory_exercise(memory_root, path, phase='unknown')
                return original_create(coordinator, operation, *args, **kwargs)

            with patch.object(Coordinator, 'create', create):
                account_exercise(account_root, path)
            assert captured == [True]
            latest = recovery.backup(config, safety, control, base=base)
            assert latest['fences']['cj_account_fence'] and latest['fences']['cj_memory_erasure_fence']
            target = dict(config, dbname='restored')
            with psycopg.connect(**config, autocommit=True) as conn:
                conn.execute('CREATE DATABASE restored TEMPLATE template0')
            # Old/incomplete packages cannot silently reacquire availability.
            try:
                recovery.restore(target, base, base, control)
            except ValueError:
                pass
            else:
                raise AssertionError('old backup released without latest deletion state')
            assert not (control / 'release.json').exists()
            recovery.restore(target, base, safety, control)
            recovery.require_release(target, control)
            with psycopg.connect(**target) as conn:
                original_identity=recovery.identity(conn)
                conn.execute('UPDATE cj.deployment_identity SET instance=gen_random_uuid()')
            try:recovery.require_release(target,control)
            except ValueError:pass
            else:raise AssertionError('replacement database instance accepted old release')
            with psycopg.connect(**target) as conn:
                conn.execute('UPDATE cj.deployment_identity SET instance=%s',(original_identity,))
            owner, other = scope_for(ISSUER, 'retention-a'), scope_for(ISSUER, 'retention-b')
            with psycopg.connect(**target) as conn, psycopg.connect(**config) as source:
                assert conn.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s', (owner,)).fetchone() == (0,)
                assert conn.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s', (other,)).fetchone() == (1,)
                assert conn.execute("SELECT count(*) FROM cj_memory_item WHERE item_id='explicit-item'").fetchone() == (0,)
                assert conn.execute('SELECT scope_id,ledger FROM cj_usage_ledger_candidate ORDER BY scope_id').fetchall() == source.execute(
                    'SELECT scope_id,ledger FROM cj_usage_ledger_candidate ORDER BY scope_id').fetchall()
                assert recovery.fence_state(conn) == recovery.fence_state(source)
                schema(conn)
                with patch.object(migrate, 'load', lambda: chain[:-1]):
                    try:
                        schema(conn)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('old application schema accepted')
            target_path = root / 'restored.json'
            target_path.write_text(json.dumps(target))
            database = LocalDatabase(target_path)
            with database.connect(other) as conn:
                try:conn.execute('UPDATE cj.deployment_identity SET instance=gen_random_uuid()')
                except psycopg.errors.InsufficientPrivilege:conn.rollback()
                else:raise AssertionError('runtime changed database instance identity')
            with database.connect(owner) as conn:
                assert conn.execute('SELECT count(*) FROM cj_message_receipt').fetchone() == (0,)
                try:
                    conn.execute('INSERT INTO cj_message_scope(scope) VALUES(%s)', (owner,))
                except psycopg.Error:
                    conn.rollback()
                else:
                    raise AssertionError('retired account namespace recreated after recovery')
            with psycopg.connect(**target, autocommit=True) as conn:
                try:
                    migrate.down(conn, chain, 47)
                except psycopg.Error:
                    pass
                else:
                    raise AssertionError('populated rollback accepted')
            # A mutated safety artifact fails authentication/hash before any write.
            with (safety / 'database.dump').open('ab') as stream:
                stream.write(b'corrupt')
            try:
                recovery.restore(target, base, safety, control)
            except ValueError:
                pass
            else:
                raise AssertionError('modified archive accepted')
            assert not (control / 'release.json').exists()
    print('PASS L1 old backup + newer actual account/item deletion checkpoint -> new empty PG; '
          'physical erasure, permanent fences, other owner, exact accounting/UNKNOWN, old app schema, '
          'populated down refusal, old/missing/tampered safety keep unavailable')


if __name__ == '__main__':
    main()
