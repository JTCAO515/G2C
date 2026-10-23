"""Guard seam only, integrating read-only CJ019 fixed6e11 without changing its tree."""
import asyncio
from contextlib import contextmanager
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
import psycopg

ROOT = Path(__file__).resolve().parents[1]
PG = Path('/opt/homebrew/opt/postgresql@17/bin')
MANAGEMENT_REPO = ROOT.parents[2] / 'cj-019-memory-management'
FIXED = '6e11d48815259bc3d879e63cd794e37e67694b86'
PRIVATE = Path(tempfile.mkdtemp(prefix='lifecycle-', dir=ROOT / '.local'))
SOCKET = Path(tempfile.mkdtemp(prefix='cj011-lifecycle-', dir='/tmp'))
SNAPSHOT = PRIVATE / 'fixed-management'
MODULE = SNAPSHOT / 'cj_memory_management'
MODULE.mkdir(parents=True)
manifest = {}
for name in ('__init__.py', 'domain.py', 'service.py', 'postgres.py'):
    path = 'backend/memory_management/cj_memory_management/' + name
    data = subprocess.run(['git', '-C', str(MANAGEMENT_REPO), 'show', FIXED + ':' + path], check=True, capture_output=True).stdout
    (MODULE / name).write_bytes(data)
    manifest[path] = hashlib.sha256(data).hexdigest()
management_sql = subprocess.run(['git', '-C', str(MANAGEMENT_REPO), 'show', FIXED + ':backend/memory_management/schema.sql'], check=True, capture_output=True).stdout
(PRIVATE / 'fixed-manifest.json').write_text(json.dumps({'head': FIXED, 'sha256': manifest}, indent=2))
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'auth'), str(ROOT / 'tests'), str(SNAPSHOT)]
from cj_auth.interfaces import TrustedPrincipal
from cj_memory.domain import Service, Conflict, InvalidInput, Unavailable
from cj_memory.lifecycle import LifecycleAdapter, INTERFACE_VERSION
from cj_memory.operation import OperationWithheld
from cj_memory.postgres import Repository
from cj_memory_management.domain import Action
from cj_memory_management.postgres import Transaction as ManagementTransaction
from cj_memory_management.service import Service as ManagementService
from pg_checks import command
ENV = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
PASSFILE = PRIVATE / 'empty.pgpass'
PASSFILE.touch(mode=0o600)
PORT = 56117


def connect():
    return psycopg.connect(host=str(SOCKET), port=PORT, user='cj011_lifecycle',
                          dbname='postgres', passfile=str(PASSFILE), password='', connect_timeout=3)


def run_pg(*args):
    return subprocess.run([str(PG / args[0]), *args[1:]], env=ENV, check=True,
                          capture_output=True, text=True, timeout=15)


def fixed_management(tx):
    # Test-only bridge delegates the UNCHANGED fixed CJ019 service on the very
    # same cursor/scope. It never opens, commits or closes another connection.
    class BoundRepository:
        scope = tx.scope
        @contextmanager
        def transaction(self):
            yield ManagementTransaction(tx.cur, tx.scope)
    return ManagementService(BoundRepository())


def adapter(*, apply=None, query=None):
    return LifecycleAdapter(
        action_id=lambda raw: Action.parse(raw).action_id,
        apply=apply or (lambda tx, raw: fixed_management(tx).apply(raw)),
        query=query or (lambda tx, aid: fixed_management(tx).query(aid)),
    )


def encode(receipt):
    return json.dumps(asdict(receipt) if receipt is not None else None).encode()


class Checks(unittest.TestCase):
    def setUp(self):
        self.scope = self._testMethodName
        self.principal = TrustedPrincipal('test', self.scope, 'test', 1, 1, 9999999999)
        with connect() as conn:
            conn.execute('INSERT INTO cj_memory_scope(scope) VALUES (%s)', (self.scope,))
        self.adapter = adapter()
        self.s = Service(Repository(connect, self.scope), lifecycle_adapter=self.adapter)
        r = command('item', kind='preference')
        with connect() as conn:
            conn.execute("INSERT INTO cj_memory_source VALUES (%s,'source-item',1,%s,true,true,true,true,clock_timestamp()+interval '1 hour')", (self.scope, r))
        self.s.save(r)

    def guard(self, stage):
        return self.principal, self.scope

    def raw(self, aid='pause', operation='pause', version=1):
        return json.dumps(dict(action_id=aid, operation=operation, item_id='item-item',
                               expected_version=version, expected_source_version=1), indent=2).encode() + b'\n'

    def apply(self, raw=None, *, service=None, guard=None):
        return (service or self.s).with_operation(guard or self.guard, lambda ctx: encode(ctx.apply_lifecycle(raw or self.raw())))

    def query(self, aid, *, service=None, guard=None):
        return (service or self.s).with_operation(guard or self.guard, lambda ctx: encode(ctx.query_lifecycle(aid)))

    def absent(self, aid='pause'):
        self.assertEqual(self.query(aid), b'null')
        self.assertEqual(self.s.detail('item-item').status, 'active')

    def test_01_actual_fixed_domain_same_tx_apply_query_replay(self):
        transactions = []
        def apply(tx, raw):
            transactions.append(tx)
            return fixed_management(tx).apply(raw)
        def query(tx, aid):
            transactions.append(tx)
            return fixed_management(tx).query(aid)
        self.s.lifecycle_adapter = adapter(apply=apply, query=query)
        raw = self.raw()
        saved = json.loads(self.apply(raw))
        self.assertIs(transactions[0], transactions[1])
        self.assertEqual(saved['operation_id'], 'pause')
        self.assertEqual(saved['status'], 'disabled')
        self.assertEqual(saved['input_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(json.loads(self.query('pause')), saved)
        self.assertEqual(json.loads(self.apply(raw)), saved)
        with self.assertRaises(Conflict):
            self.apply(raw + b' ')
        resumed = json.loads(self.apply(self.raw('resume', 'resume', 2)))
        self.assertEqual(resumed['status'], 'active')
        self.assertEqual(resumed['version'], 3)
        self.assertEqual(json.loads(self.query('pause')), saved)

    def test_02_precommit_unknown_rolls_back_action_and_state(self):
        def denied(stage):
            return None if stage == 'precommit' else self.guard(stage)
        with self.assertRaises(OperationWithheld) as caught:
            self.apply(guard=denied)
        self.assertFalse(caught.exception.commit_possible)
        self.assertEqual(caught.exception.operation_id, 'pause')
        self.absent()

    def test_03_commit_cancel_preserves_action_reconcile(self):
        class Lost:
            def __init__(self): self.conn = connect()
            def __getattr__(self, key): return getattr(self.conn, key)
            def commit(self):
                self.conn.commit()
                raise asyncio.CancelledError()
        s = Service(Repository(Lost, self.scope), lifecycle_adapter=self.adapter)
        with self.assertRaises(OperationWithheld) as caught:
            self.apply(service=s)
        self.assertTrue(caught.exception.commit_possible)
        self.assertEqual(caught.exception.operation_id, 'pause')
        self.assertEqual(caught.exception.recovery, 'reconcile_original')
        self.assertEqual(json.loads(self.query('pause'))['status'], 'disabled')

    def test_04_precommit_cancel_cannot_be_swallowed(self):
        def cancel(stage):
            if stage == 'precommit': raise asyncio.CancelledError()
            return self.guard(stage)
        def outer(ctx):
            try: ctx.apply_lifecycle(self.raw())
            except BaseException: pass
            return b'false-success'
        with self.assertRaises(OperationWithheld):
            self.s.with_operation(cancel, outer)
        self.absent()

    def test_05_after_close_adapter_replacement_withholds_committed(self):
        original = self.adapter
        s = None
        class CloseChangesAdapter:
            def __init__(self): self.conn = connect()
            def __getattr__(self, key): return getattr(self.conn, key)
            def close(self):
                self.conn.close()
                s.lifecycle_adapter = adapter()
        s = Service(Repository(CloseChangesAdapter, self.scope), lifecycle_adapter=original)
        with self.assertRaises(OperationWithheld) as caught:
            self.apply(service=s)
        self.assertTrue(caught.exception.commit_possible)
        self.assertEqual(caught.exception.operation_id, 'pause')
        self.assertEqual(json.loads(self.query('pause'))['status'], 'disabled')

    def test_06_final_projection_identity_or_repo_changes(self):
        for mode in ('identity', 'repository'):
            changed = False
            s = Service(Repository(connect, self.scope), lifecycle_adapter=self.adapter)
            def guard(stage):
                if changed and mode == 'identity':
                    return TrustedPrincipal('test', 'B', 'test', 1, 1, 9999999999), self.scope
                return self.guard(stage)
            def outer(ctx):
                nonlocal changed
                value = ctx.apply_lifecycle(self.raw())
                changed = True
                if mode == 'repository': s.repository = Repository(connect, self.scope)
                return encode(value)
            with self.assertRaises(OperationWithheld) as caught:
                s.with_operation(guard, outer)
            self.assertTrue(caught.exception.commit_possible)
            self.assertEqual(caught.exception.operation_id, 'pause')
        self.assertEqual(json.loads(self.query('pause'))['status'], 'disabled')

    def test_07_adapter_replacement_before_commit_rolls_back(self):
        def apply(tx, raw):
            result = fixed_management(tx).apply(raw)
            self.s.lifecycle_adapter = adapter()
            return result
        self.s.lifecycle_adapter = adapter(apply=apply)
        with self.assertRaises(OperationWithheld) as caught:
            self.apply()
        self.assertFalse(caught.exception.commit_possible)
        self.absent()

    def test_08_expired_context_thread_and_transaction_closed(self):
        captured = []
        transactions = []
        def apply(tx, raw):
            transactions.append(tx)
            return fixed_management(tx).apply(raw)
        self.s.lifecycle_adapter = adapter(apply=apply)
        def outer(ctx):
            captured.append(ctx)
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaises(RuntimeError):
                    pool.submit(ctx.query_lifecycle, 'pause').result(timeout=2)
            return encode(ctx.apply_lifecycle(self.raw()))
        self.s.with_operation(self.guard, outer)
        with self.assertRaises(RuntimeError): captured[0].query_lifecycle('pause')
        self.assertTrue(transactions[0].cur.closed)
        with self.assertRaises(psycopg.OperationalError) as closed:
            transactions[0].cur.execute('SELECT 1')
        self.assertIn('connection is closed', str(closed.exception))

    def test_09_reentry_and_deferred_adapter_rejected(self):
        for mode in ('reentry', 'deferred'):
            captured = []
            async def later(): return None
            def apply(tx, raw):
                if mode == 'deferred': return later()
                try: captured[0].groups()
                except RuntimeError: pass
                return fixed_management(tx).apply(raw)
            s = Service(Repository(connect, self.scope), lifecycle_adapter=adapter(apply=apply))
            def outer(ctx):
                captured.append(ctx)
                try: ctx.apply_lifecycle(self.raw())
                except BaseException: pass
                return b'false-success'
            with self.assertRaises(OperationWithheld): s.with_operation(self.guard, outer)
            self.absent()

    def test_10_query_only_same_scope_and_identity_guarded(self):
        self.apply()
        calls = []
        def no_apply(tx, raw): raise AssertionError('query must not call apply')
        def query(tx, aid):
            calls.append(aid)
            return fixed_management(tx).query(aid)
        s = Service(Repository(connect, self.scope), lifecycle_adapter=adapter(apply=no_apply, query=query))
        self.assertEqual(json.loads(self.query('pause', service=s))['operation_id'], 'pause')
        self.assertEqual(calls, ['pause'])
        with connect() as conn:
            conn.execute("INSERT INTO cj_memory_scope(scope) VALUES (%s)", (self.scope + '-B',))
        b = Service(Repository(connect, self.scope + '-B'), lifecycle_adapter=self.adapter)
        self.assertEqual(self.query('pause', service=b, guard=lambda _: (self.principal, self.scope + '-B')), b'null')
        with self.assertRaises(OperationWithheld):
            self.query('pause', service=s, guard=lambda stage: None if stage == 'precommit' else self.guard(stage))
        self.assertEqual(self.s.detail('item-item').version, 2)

    def test_11_missing_adapter_and_mismatched_receipt(self):
        with self.assertRaises(Unavailable): self.apply(service=Service(Repository(connect, self.scope)))
        def bad_apply(tx, raw):
            receipt = fixed_management(tx).apply(raw)
            return replace(receipt, input_sha256='0' * 64)
        with self.assertRaises(Unavailable):
            self.apply(service=Service(Repository(connect, self.scope), lifecycle_adapter=adapter(apply=bad_apply)))
        self.absent()

    def test_12_one_write_namespace_and_query_no_auto_retry(self):
        def outer(ctx):
            receipt = ctx.apply_lifecycle(self.raw())
            self.assertEqual(ctx.query_lifecycle('pause'), receipt)
            try: ctx.apply_lifecycle(self.raw('second'))
            except InvalidInput: pass
            return b'false-success'
        with self.assertRaises(OperationWithheld) as caught:
            self.s.with_operation(self.guard, outer)
        self.assertTrue(caught.exception.commit_possible)
        self.assertEqual(caught.exception.operation_id, 'pause')
        self.assertEqual(self.query('missing'), b'null')
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_management_action WHERE scope=%s', (self.scope,)).fetchone()[0], 1)


def main():
    started = False
    result = None
    try:
        run_pg('initdb', '-D', str(PRIVATE / 'pg'), '-U', 'cj011_lifecycle', '--auth=trust', '--no-locale', '--encoding=UTF8')
        run_pg('pg_ctl', '-D', str(PRIVATE / 'pg'), '-l', str(PRIVATE / 'server.log'), '-o', f"-k {SOCKET} -p {PORT} -c listen_addresses=''", 'start')
        started = True
        with connect() as conn:
            conn.execute((ROOT / 'schema.sql').read_text())
            conn.execute(management_sql.decode())
            identity = conn.execute("SELECT current_user,current_database(),current_setting('listen_addresses'),current_setting('port')").fetchone()
        with (PRIVATE / 'test.log').open('w') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
        print((PRIVATE / 'test.log').read_text())
        print(json.dumps({'private': str(PRIVATE), 'socket': str(SOCKET), 'identity': identity, 'fixedCJ019': FIXED,
                          'interface': INTERFACE_VERSION, 'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors)}))
    finally:
        if started: run_pg('pg_ctl', '-D', str(PRIVATE / 'pg'), 'stop', '-m', 'fast')
        print('Private lifecycle PG stopped; data/evidence retained:', PRIVATE)
    return 0 if result is not None and result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
