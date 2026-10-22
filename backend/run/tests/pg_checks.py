"""Explicit task-private Unix-socket PG checks; no environment DSN is accepted."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import unittest
import psycopg
from cj_run.core import Binding, Event, Service, Conflict, Denied, ResyncRequired
from cj_run.postgres import Repository, CommitUnknown

ROOT = Path(__file__).resolve().parents[1]
SOCKET = ROOT / '.local/socket'


def connect():
    return psycopg.connect(host=str(SOCKET), dbname='postgres', connect_timeout=3)


def repository(scope, factory=connect, expiry=None):
    return Repository(factory, scope, expires_at=expiry or datetime.now(timezone.utc)+timedelta(hours=1),
                      statement_timeout_ms=3000, lock_timeout_ms=2000)


class PgTests(unittest.TestCase):
    def setUp(self):
        self.scope = self.id()
        with connect() as c:
            c.execute('INSERT INTO cj_run_scope VALUES (%s,%s,true)', (self.scope, 'epoch1'))
        self.b = Binding(self.scope, 'chat', 'gen', 'm1', 'r1', 1)
        self.repo = repository(self.scope)
        self.service = Service(self.repo, lambda _: True)
        self.service.accept(self.b)

    def event(self, kind, sequence, value='', event_id=None, binding=None):
        return Event(binding or self.b, sequence, event_id or f'e{sequence}', kind, value)

    def test_persisted_rebuild_duplicate_and_cancel(self):
        for e in [self.event('started',1), self.event('text_delta',2,'partial'),
                  self.event('effect_committed',3,'fixture-receipt'), self.event('cancelled',4)]:
            self.service.apply(e)
        rebuilt = Service(repository(self.scope), lambda _: True)
        state = rebuilt.snapshot(self.b)
        self.assertEqual((state.status,state.text,state.effects), ('cancelled','partial',('fixture-receipt',)))
        self.assertEqual(rebuilt.apply(self.event('cancelled',4)), state)
        with self.assertRaises(Conflict): rebuilt.apply(self.event('completed',5))
        self.assertEqual(self.repo.recover(self.b).action, 'terminal')

    def test_binding_conflict_scope_and_expiry(self):
        for b in (replace(self.b,message_id='m2'),replace(self.b,run_id='r2'),
                  replace(self.b,conversation_id='different')):
            with self.assertRaises(Conflict): self.service.accept(b)
        with self.assertRaises(Denied): self.service.snapshot(replace(self.b,scope='other'))
        with connect() as c:
            c.execute("UPDATE cj_run_record SET expires_at=clock_timestamp()-interval '1 second' WHERE scope=%s",(self.scope,))
        with self.assertRaises(ResyncRequired): self.service.accept(self.b)
        with self.assertRaises(ResyncRequired): self.repo.recover(self.b)

    def test_gap_and_conflicting_duplicate_rollback(self):
        with self.assertRaises(ResyncRequired): self.service.apply(self.event('started',2))
        self.service.apply(self.event('started',1))
        with self.assertRaises(Conflict): self.service.apply(self.event('cancelled',1))
        self.assertEqual(self.service.snapshot(self.b).sequence,1)

    def test_same_chat_and_unknown_barrier(self):
        b2 = replace(self.b, message_id='m2',run_id='r2',message_sequence=2)
        b3 = replace(self.b, message_id='m3',run_id='r3',message_sequence=3)
        self.service.accept(b3)
        with self.assertRaises(Conflict): self.service.apply(self.event('started',1,binding=b3))
        self.service.apply(self.event('cancelled',1))
        self.service.accept(b2)
        self.service.apply(self.event('started',1,binding=b2))
        self.service.apply(self.event('unknown',2,binding=b2))
        with self.assertRaises(Conflict): self.service.apply(self.event('started',1,binding=b3))
        self.assertEqual(self.repo.recover(b2).action,'query_only')

    def test_two_connections_terminal_race(self):
        self.service.apply(self.event('started',1))
        def apply(kind):
            try:
                return Service(repository(self.scope),lambda _: True).apply(self.event(kind,2,event_id=kind)).status
            except Conflict:
                return 'conflict'
        with ThreadPoolExecutor(2) as pool:
            result = list(pool.map(apply,('completed','cancelled')))
        self.assertEqual(result.count('conflict'),1)
        self.assertEqual(self.service.snapshot(self.b).sequence,2)

    def test_replayed_accept_race(self):
        def accept(_): return Service(repository(self.scope)).accept(self.b)
        with ThreadPoolExecutor(3) as pool:
            result = list(pool.map(accept,range(6)))
        self.assertTrue(all(s==result[0] for s in result))
        with connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM cj_run_record WHERE scope=%s',(self.scope,)).fetchone()[0],1)

    def test_highwater_epoch_expiry(self):
        self.service.apply(self.event('started',1))
        self.service.apply(self.event('text_delta',2,'x'))
        recovery = self.repo.recover(self.b)
        self.service.apply(self.event('completed',3))
        rows, cursor = self.repo.events(recovery.cursor,limit=1)
        self.assertEqual(rows[0].sequence,1)
        rows, end = self.repo.events(cursor,limit=1)
        self.assertEqual(rows[0].sequence,2)
        self.assertIsNone(end)
        with connect() as c:
            c.execute('UPDATE cj_run_scope SET epoch=%s WHERE scope=%s',('epoch2',self.scope))
        with self.assertRaises(ResyncRequired): self.repo.events(recovery.cursor,limit=1)

    def test_commit_ack_unknown_queries_original(self):
        class LostAck:
            def __init__(self): self.inner=connect()
            def __getattr__(self,name): return getattr(self.inner,name)
            def commit(self):
                self.inner.commit()
                raise OSError('synthetic lost commit ACK')
        lost = Service(repository(self.scope,LostAck),lambda _:True)
        with self.assertRaises(CommitUnknown): lost.apply(self.event('started',1))
        state = self.repo.recover(self.b).state
        self.assertEqual((state.status,state.sequence),('running',1))
        self.assertEqual(self.service.apply(self.event('started',1)),state)

    def test_database_terminal_constraint(self):
        self.service.apply(self.event('cancelled',1))
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with connect() as c:
                c.execute("INSERT INTO cj_run_event VALUES (%s,'r1',2,'late','completed','')",(self.scope,))

    def test_corrupt_gap_is_not_success(self):
        self.service.apply(self.event('started',1))
        self.service.apply(self.event('completed',2))
        # Explicit synthetic corruption in this private fixture database only.
        with connect() as c:
            c.execute('DELETE FROM cj_run_event WHERE scope=%s AND sequence=1',(self.scope,))
        with self.assertRaises(ResyncRequired): self.repo.recover(self.b)

    def test_revocation_and_default_context(self):
        with self.assertRaises(Denied): Service(self.repo).apply(self.event('started',1))
        with connect() as c:
            c.execute('UPDATE cj_run_scope SET active=false WHERE scope=%s',(self.scope,))
        with self.assertRaises(Denied): self.repo.recover(self.b)


if __name__ == '__main__':
    with connect() as c:
        assert c.execute('SHOW listen_addresses').fetchone()[0] == ''
        assert c.execute('SHOW server_version').fetchone()[0].startswith('16.15')
        c.execute((ROOT/'sql/candidate.sql').read_text())
    unittest.main()
