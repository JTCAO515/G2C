"""Targeted message-page generation checks, synthetic memory only."""
import unittest
from model import Authority, Model, Rejected
from check import wire


class MessageCursorChecks(unittest.TestCase):
    def setUp(self):
        self.m = Model()
        self.a = Authority('fixture-a', email_status='verified')
        self.b = Authority('fixture-b', email_status='verified')
        self.m.s['auth'] = {'fixture-a': 1, 'fixture-b': 1}
        for actor, cid in ((self.a, 'a-chat'), (self.b, 'b-chat')):
            self.m.create(actor, cid)
            for mid in ('m1', 'm2'):
                self.m.receive(actor, wire(mid, cid=cid))
        self.token = self.m.page(self.a, 'a-chat', limit=1)['next_cursor']
        self.btoken = self.m.page(self.b, 'b-chat', limit=1)['next_cursor']

    def resync(self):
        with self.assertRaisesRegex(Rejected, '^resync_required$'):
            self.m.page(self.a, 'a-chat', self.token)

    def test_recreated_chat_rejects_old_message_cursor(self):
        del self.m.s['chats']['a-chat']  # Synthetic fault, not a cleanup API.
        self.m.create(self.a, 'a-chat')
        self.m = Model(self.m.image())
        self.resync()
        self.assertEqual(self.m.page(self.a, 'a-chat')['items'], [])
        self.assertEqual(self.m.page(self.b, 'b-chat', self.btoken)['items'][0]['message_id'], 'm2')

    def test_wrong_creation_generation_rejected(self):
        self.m.s['chats']['a-chat']['generation'] += 100
        self.resync()

    def test_legacy_binding_requires_explicit_resync(self):
        c = self.m.s['chats']['a-chat']
        self.m.s['cursors'][self.token]['binding'] = (self.a.principal, self.a.revision, 'a-chat', c['epoch'])
        self.resync()

    def test_append_and_other_account_recreation_do_not_invalidate(self):
        self.m.receive(self.a, wire('m3', cid='a-chat'))
        del self.m.s['chats']['b-chat']
        self.m.create(self.b, 'b-chat')
        self.m = Model(self.m.image())
        page = self.m.page(self.a, 'a-chat', self.token)
        self.assertEqual([x['message_id'] for x in page['items']], ['m2'])
        self.assertEqual(page, self.m.page(self.a, 'a-chat', self.token))
        self.assertEqual(page['snapshot_count'], 2)
        self.assertIsNone(page['next_cursor'])
        self.assertEqual(len(self.m.page(self.a, 'a-chat', limit=100)['items']), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
