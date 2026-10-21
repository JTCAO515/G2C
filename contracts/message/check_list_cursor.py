"""P2 targeted synthetic cursor invalidation checks; no real cleanup/DB."""
import unittest
from model import Authority, Model, Rejected


class ListCursorChecks(unittest.TestCase):
    def setUp(self):
        self.m = Model()
        self.a = Authority('fixture-a', email_status='verified')
        self.b = Authority('fixture-b', email_status='verified')
        self.m.s['auth'] = {'fixture-a': 1, 'fixture-b': 1}
        for cid in ('a1', 'a2', 'a3'):
            self.m.create(self.a, cid)
        for cid in ('b1', 'b2'):
            self.m.create(self.b, cid)
        self.token = self.m.conversations(self.a, limit=1)['next_cursor']
        self.btoken = self.m.conversations(self.b, limit=1)['next_cursor']

    def resync(self, token):
        with self.assertRaisesRegex(Rejected, '^resync_required$'):
            self.m.conversations(self.a, token)

    def test_deleted_unread_entry_rejects_old_snapshot(self):
        self.m.s['chats']['a2']['epoch'] += 1
        del self.m.s['chats']['a2']  # fault injection; not a production cleanup API
        self.m = Model(self.m.image())
        self.resync(self.token)
        self.assertEqual(self.m.conversations(self.a)['items'], ['a1', 'a3'])
        self.assertEqual(self.m.conversations(self.b, self.btoken)['items'], ['b2'])

    def test_epoch_change_without_delete_rejects(self):
        self.m.s['chats']['a2']['epoch'] += 1
        self.resync(self.token)

    def test_recreated_id_does_not_revive_old_cursor(self):
        del self.m.s['chats']['a2']
        self.m.create(self.a, 'a2')
        self.resync(self.token)

    def test_other_account_and_append_do_not_invalidate(self):
        self.m.s['chats']['b2']['epoch'] += 1
        del self.m.s['chats']['b2']
        self.m.create(self.a, 'new-a')
        self.assertEqual(self.m.conversations(self.a, self.token)['items'], ['a2', 'a3'])
        self.assertEqual(self.m.conversations(self.a, self.token)['items'], ['a2', 'a3'])

    def test_unknown_expired_and_foreign_cursor_explicit_resync(self):
        self.resync('unknown-fixture-token')
        self.resync(self.btoken)
        del self.m.s['cursors'][self.token]
        self.resync(self.token)

    def test_legacy_cursor_requires_explicit_resync(self):
        self.m.s['cursors'][self.token]['snapshot'] = ['a1', 'a2', 'a3']
        self.resync(self.token)

    def test_changed_ownership_does_not_leak_entry(self):
        self.m.s['chats']['a2']['owner'] = self.b.principal
        self.resync(self.token)


if __name__ == '__main__':
    unittest.main(verbosity=2)
