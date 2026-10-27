"""Only new guarded-consumption cases against fixed canonical 0045 and fresh PG."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent/'memory'), str(ROOT.parent/'auth')]
from cj_auth.interfaces import TrustedPrincipal
from cj_memory.domain import Service as MemoryService, Conflict, InvalidInput
from cj_memory.operation import OperationWithheld
from cj_memory.postgres import Repository as MemoryRepository
from cj_memory_management.guarded import ADAPTER, GuardedService
from cj_memory_management.postgres import Repository
from cj_memory_management.service import Service

CONFIG = json.loads(Path(sys.argv.pop(1)).read_text())
for key in tuple(os.environ):
    if key.startswith('PG'):
        del os.environ[key]
A = TrustedPrincipal('synthetic', 'A', 'test', 1, 1, 9999999999)
B = TrustedPrincipal('synthetic', 'B', 'test', 1, 1, 9999999999)


def connect():
    return psycopg.connect(**CONFIG)


class Guard:
    def __init__(self, scope='A'):
        self.principal = A if scope == 'A' else B
        self.scope = scope
        self.stages = []
        self.fail_at = None
    def __call__(self, stage):
        self.stages.append(stage)
        if self.fail_at == stage:
            raise asyncio.CancelledError('synthetic fresh guard cancelled')
        return self.principal, self.scope


def guarded(factory=connect, scope='A'):
    return GuardedService(MemoryRepository(factory, scope))


def domain(scope='A'):
    return Service(Repository(connect, scope))


def encode(receipt):
    return json.dumps(asdict(receipt) if receipt is not None else None).encode()


def action(name, operation='pause', version=1):
    return json.dumps(dict(action_id=operation+'-'+name, operation=operation,
                          item_id=name, expected_version=version,
                          expected_source_version=1), indent=2).encode()+b'\n'


def seed(name):
    obj = dict(operation_id='save-'+name, item_id=name, subject='self', slot=name,
               kind='preference', text='合成内容 / synthetic fact', extent='long_term',
               context_id=None, source_id='source-'+name, source_version=1,
               occurred_at='date unknown')
    raw = json.dumps(obj, ensure_ascii=False).encode()
    with connect() as conn:
        conn.execute("INSERT INTO cj_memory_source VALUES ('A',%s,1,%s,true,true,true,true,clock_timestamp()+interval '1 hour')", (obj['source_id'], raw))
    MemoryService(MemoryRepository(connect, 'A')).save(raw)


def item(name):
    return MemoryService(MemoryRepository(connect, 'A')).detail(name)


class Checks(unittest.TestCase):
    def test_01_restricted_context_apply_query_same_transaction(self):
        seed('guard-success')
        count = 0
        def counted():
            nonlocal count
            count += 1
            return connect()
        guard = Guard()
        def project(ctx):
            self.assertFalse(hasattr(ctx, 'save'))
            self.assertFalse(hasattr(ctx, 'repository'))
            return encode(ctx.apply(action('guard-success')))
        saved = guarded(counted).with_operation(guard, project)
        self.assertEqual(count, 1)  # apply + canonical ledger verification share one tx.
        self.assertEqual(guard.stages, ['entry','transaction','transaction_ready','precommit','private_return','return'])
        self.assertEqual(saved, guarded().with_operation(Guard(), lambda ctx: encode(ctx.query('pause-guard-success'))))
        self.assertEqual(json.loads(saved)['input_sha256'], hashlib.sha256(action('guard-success')).hexdigest())
        resumed = guarded().with_operation(Guard(), lambda ctx: encode(ctx.apply(action('guard-success', 'resume', 2))))
        self.assertEqual(json.loads(resumed)['status'], 'active')
        self.assertEqual(item('guard-success').version, 3)

    def test_02_precommit_cancellation_rollback_sticky_when_caught(self):
        seed('guard-precommit')
        guard = Guard()
        guard.fail_at = 'precommit'
        def catch(ctx):
            try:
                ctx.apply(action('guard-precommit'))
            except BaseException:
                pass
            return b'{}'
        with self.assertRaises(OperationWithheld) as caught:
            guarded().with_operation(guard, catch)
        self.assertFalse(caught.exception.commit_possible)
        self.assertEqual(caught.exception.operation_id, 'pause-guard-precommit')
        self.assertIsNone(domain().query('pause-guard-precommit'))
        self.assertEqual(item('guard-precommit').version, 1)

    def test_03_committed_ack_faults_keep_original_action(self):
        for error in (OSError, asyncio.CancelledError, KeyboardInterrupt):
            name = 'guard-ack-'+error.__name__
            seed(name)
            class Lost:
                def __init__(self): self.conn = connect()
                def __getattr__(self, key): return getattr(self.conn, key)
                def commit(self):
                    self.conn.commit()
                    raise error('synthetic committed ACK fault')
            with self.assertRaises(OperationWithheld) as caught:
                guarded(Lost).with_operation(Guard(), lambda ctx: encode(ctx.apply(action(name))))
            e = caught.exception
            self.assertEqual((e.operation_id,e.commit_possible,e.recovery), ('pause-'+name,True,'reconcile_original'))
            recovered = guarded().with_operation(Guard(), lambda ctx: encode(ctx.query(e.operation_id)))
            self.assertEqual(json.loads(recovered)['version'], 2)

    def test_04_identity_change_on_commit_or_close_withholds_durable_result(self):
        for stage in ('commit','close'):
            name = 'guard-'+stage
            seed(name)
            guard = Guard()
            class Changed:
                def __init__(self): self.conn = connect()
                def __getattr__(self, key): return getattr(self.conn, key)
                def commit(self):
                    self.conn.commit()
                    if stage == 'commit': guard.principal = B
                def close(self):
                    self.conn.close()
                    if stage == 'close': guard.principal = B
            with self.assertRaises(OperationWithheld) as caught:
                guarded(Changed).with_operation(guard, lambda ctx: encode(ctx.apply(action(name))))
            self.assertEqual(caught.exception.stage, 'private_return')
            self.assertEqual(caught.exception.operation_id, 'pause-'+name)
            self.assertTrue(caught.exception.commit_possible)
            self.assertIsNotNone(domain().query('pause-'+name))
            self.assertIn('private_return', guard.stages)

    def test_05_projection_final_identity_failure_keeps_receipt(self):
        seed('guard-projection')
        guard = Guard()
        def project(ctx):
            receipt = ctx.apply(action('guard-projection'))
            encoded = encode(receipt)
            guard.principal = B
            return encoded
        with self.assertRaises(OperationWithheld) as caught:
            guarded().with_operation(guard, project)
        self.assertEqual(caught.exception.stage, 'return')
        self.assertTrue(caught.exception.commit_possible)
        self.assertEqual(caught.exception.operation_id, 'pause-guard-projection')
        self.assertIsNotNone(domain().query('pause-guard-projection'))

    def test_06_callback_cancel_or_deferred_output_after_commit(self):
        for mode in ('cancel','generator','coroutine'):
            name = 'guard-output-'+mode
            seed(name)
            async def deferred(): return b'{}'
            def project(ctx):
                ctx.apply(action(name))
                if mode == 'cancel': raise asyncio.CancelledError()
                if mode == 'generator': return (x for x in [b'{}'])
                return deferred()
            with self.assertRaises(OperationWithheld) as caught:
                guarded().with_operation(Guard(), project)
            self.assertEqual(caught.exception.operation_id, 'pause-'+name)
            self.assertTrue(caught.exception.commit_possible)
            self.assertIsNotNone(domain().query('pause-'+name))

    def test_07_escape_other_thread_and_query_cannot_apply(self):
        seed('guard-lifetime')
        saved = []
        def project(ctx):
            saved.append(ctx)
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaises(RuntimeError):
                    pool.submit(ctx.query, 'pause-guard-lifetime').result()
            return encode(ctx.query('pause-guard-lifetime'))
        self.assertEqual(guarded().with_operation(Guard(), project), b'null')
        for fn,arg in [(saved[0].apply,action('guard-lifetime')),
                       (saved[0].query,'pause-guard-lifetime')]:
            with self.assertRaises(RuntimeError): fn(arg)
        def no_retry(ctx):
            self.assertIsNone(ctx.query('pause-guard-lifetime'))
            try: ctx.apply(action('guard-lifetime'))
            except InvalidInput: pass
            return b'{}'
        with self.assertRaises(OperationWithheld):
            guarded().with_operation(Guard(), no_retry)
        self.assertIsNone(domain().query('pause-guard-lifetime'))
        self.assertEqual(item('guard-lifetime').version, 1)

    def test_08_same_raw_replay_changed_raw_and_single_write(self):
        seed('guard-replay')
        raw = action('guard-replay')
        first = guarded().with_operation(Guard(), lambda ctx: encode(ctx.apply(raw)))
        self.assertEqual(first, guarded().with_operation(Guard(), lambda ctx: encode(ctx.apply(raw))))
        with self.assertRaises(Conflict):
            guarded().with_operation(Guard(), lambda ctx: encode(ctx.apply(raw+b' ')))
        def two(ctx):
            ctx.apply(raw)
            try: ctx.apply(raw)
            except InvalidInput: pass
            return b'{}'
        with self.assertRaises(OperationWithheld) as caught:
            guarded().with_operation(Guard(), two)
        self.assertTrue(caught.exception.commit_possible)
        self.assertEqual(item('guard-replay').version, 2)

    def test_09_wrong_scope_and_principal_drift_before_commit(self):
        seed('guard-isolation')
        # Scope B can see neither A's action receipt nor its item.
        self.assertEqual(guarded(scope='B').with_operation(Guard('B'), lambda ctx: encode(ctx.query('pause-guard-isolation'))), b'null')
        def none(): raise AssertionError('wrong binding must not open DB')
        with self.assertRaises(OperationWithheld):
            guarded(none).with_operation(Guard('B'), lambda ctx: b'{}')
        guard = Guard()
        def change(stage):
            if stage == 'precommit': guard.principal = B
            return guard(stage)
        with self.assertRaises(OperationWithheld) as caught:
            guarded().with_operation(change, lambda ctx: encode(ctx.apply(action('guard-isolation'))))
        self.assertFalse(caught.exception.commit_possible)
        self.assertIsNone(domain().query('pause-guard-isolation'))

    def test_10_adapter_and_repository_replacement_withholds(self):
        seed('guard-replace')
        for replaced in ('repository','lifecycle_adapter'):
            service = guarded()
            def project(ctx):
                result = ctx.query('pause-guard-replace')
                if replaced == 'repository': service.repository = MemoryRepository(connect, 'A')
                else: service.lifecycle_adapter = None
                return encode(result)
            with self.assertRaises(OperationWithheld):
                service.with_operation(Guard(), project)
        with self.assertRaises(ValueError): GuardedService(MemoryRepository(connect, 'A'), lifecycle_adapter=None)
        self.assertIs(guarded().lifecycle_adapter, ADAPTER)

    def test_11_query_is_read_only_and_original_save_receipt_unchanged(self):
        seed('guard-query')
        guarded().with_operation(Guard(), lambda ctx: encode(ctx.apply(action('guard-query'))))
        with connect() as conn:
            before = conn.execute("SELECT epoch FROM cj_memory_scope WHERE scope='A'").fetchone()[0]
        saved = MemoryService(MemoryRepository(connect, 'A')).query('save-guard-query')
        self.assertEqual(saved.version, 1)
        for _ in range(2):
            queried = guarded().with_operation(Guard(), lambda ctx: encode(ctx.query('pause-guard-query')))
            self.assertEqual(json.loads(queried)['version'], 2)
        with connect() as conn:
            self.assertEqual(before,conn.execute("SELECT epoch FROM cj_memory_scope WHERE scope='A'").fetchone()[0])
        # The refactored trusted-domain entry shares exact adapter logic.
        self.assertEqual(domain().apply(action('guard-query')).version, 2)
        self.assertEqual(domain().query('pause-guard-query'), domain().apply(action('guard-query')))

    def test_12_restart_fixture(self):
        seed('guard-restart')
        guarded().with_operation(Guard(), lambda ctx: encode(ctx.apply(action('guard-restart'))))


def restart():
    raw = action('guard-restart')
    result = json.loads(guarded().with_operation(Guard(),lambda ctx: encode(ctx.query('pause-guard-restart'))))
    assert result['version'] == 2 and result['status'] == 'disabled'
    assert result['input_sha256'] == hashlib.sha256(raw).hexdigest()
    assert item('guard-restart').version == 2
    print('PASS guarded query after actual new server/process restart; original receipt/hash and disabled item')


if __name__ == '__main__':
    if '--restart' in sys.argv: restart()
    else: unittest.main(verbosity=2)
