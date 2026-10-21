"""Offline synthetic behavior checks: python3 -B contracts/message/check.py."""
import json
import unittest
from model import Authority, Model, Rejected, LostAck, parse


def wire(mid='m1', cid='c1', **kw):
    return json.dumps(dict(version='MESSAGE-draft.1', conversation_id=cid,
                           message_id=mid, text='你好 / Hello', trip_id=None,
                           creation_intent='consider_trip', **kw), ensure_ascii=False).encode()


class Checks(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Authority('fixture-a', email_status='verified'), Authority('fixture-b', email_status='verified')
        self.m = Model()
        self.m.s['auth'] = {'fixture-a': 1, 'fixture-b': 1}
        self.m.create(self.a, 'c1')

    def reject(self, reason, fn):
        with self.assertRaisesRegex(Rejected, '^' + reason + '$'):
            fn()

    def test_original_receipt_and_bytes(self):
        raw = wire()
        r = self.m.receive(self.a, raw)
        self.m.deliver(self.a, 'm1')
        self.m.finish(self.a, 'm1', {'terminal': 'completed'})
        self.assertEqual(r, self.m.receive(self.a, raw))
        self.reject('input_conflict', lambda: self.m.receive(self.a, raw + b' '))
        self.m.create(self.a, 'c2')
        self.reject('input_conflict', lambda: self.m.receive(self.a, wire(cid='c2')))
        self.assertEqual(len(self.m.s['jobs']), 1)

    def test_unknown_before_commit_queries_original(self):
        with self.assertRaises(LostAck):
            self.m.receive(self.a, wire(), 'before_commit')
        self.m = Model(self.m.image())
        self.assertEqual(self.m.query(self.a, 'm1'), {'state': 'not_received'})
        self.m.receive(self.a, wire())
        self.assertEqual(len(self.m.s['actions']), 1)

    def test_commit_before_dispatch_recovery(self):
        with self.assertRaises(LostAck):
            self.m.receive(self.a, wire(), 'after_commit')
        self.m = Model(self.m.image())
        self.assertEqual(self.m.query(self.a, 'm1')['state'], 'accepted_pending')
        r = self.m.deliver(self.a, 'm1')
        self.assertEqual(r, self.m.query(self.a, 'm1')['receipt']['run_id'])

    def test_run_accept_lost_ack_no_second_run(self):
        self.m.receive(self.a, wire())
        with self.assertRaises(LostAck):
            self.m.deliver(self.a, 'm1', 'after_run_accept')
        self.m = Model(self.m.image())
        self.m.deliver(self.a, 'm1')
        self.assertEqual(len(self.m.s['runs']), 1)
        self.m.finish(self.a, 'm1', {'terminal': 'cancelled'})
        self.reject('invalid_transition', lambda: self.m.finish(self.a, 'm1', {'terminal': 'completed'}))

    def test_identity_and_eligibility_fences(self):
        self.m.receive(self.a, wire())
        self.reject('unavailable', lambda: self.m.page(self.b, 'c1'))
        self.reject('unavailable', lambda: self.m.page(self.b, 'missing'))
        self.assertEqual(self.m.query(self.b, 'm1'), self.m.query(self.b, 'missing'))
        self.reject('unavailable', lambda: self.m.receive(Authority('fixture-a', eligible=False), wire()))
        self.m.s['auth']['fixture-a'] = 2
        self.reject('unavailable', lambda: self.m.deliver(self.a, 'm1'))
        self.assertEqual(self.m.s['runs'], {})

    def test_nullable_trip_and_no_fake_authority(self):
        raw = wire()
        self.m.receive(self.a, raw)
        p = parse(wire('m2')); p['trip_id'] = 'not-verified'
        self.reject('trip_authority_required', lambda: self.m.receive(self.a, json.dumps(p).encode()))
        self.assertIsNone(parse(raw)['trip_id'])

    def test_draft_and_history_checkpoint(self):
        self.m.draft(self.a, 'c1', '未发送'.encode())
        self.m = Model(self.m.image())
        self.assertEqual(self.m.draft(self.a, 'c1'), '未发送'.encode())
        self.assertEqual(self.m.page(self.a, 'c1')['items'], [])
        self.reject('unavailable', lambda: self.m.draft(self.b, 'c1'))

    def test_snapshot_paging_append_restart_and_replay(self):
        for i in range(3): self.m.receive(self.a, wire(str(i)))
        p = self.m.page(self.a, 'c1', limit=1)
        token = p['next_cursor']
        self.m.receive(self.a, wire('later'))
        self.m = Model(self.m.image())
        tail = self.m.page(self.a, 'c1', token)
        self.assertEqual([x['message_id'] for x in tail['items']], ['1', '2'])
        self.assertIsNone(tail['next_cursor'])
        self.assertEqual(tail, self.m.page(self.a, 'c1', token))
        self.assertEqual(len(self.m.page(self.a, 'c1', limit=100)['items']), 4)

    def test_invalid_expired_and_cross_scope_cursors(self):
        for i in range(3): self.m.receive(self.a, wire(str(i)))
        token = self.m.page(self.a, 'c1', limit=1)['next_cursor']
        self.m.create(self.a, 'c2')
        self.reject('resync_required', lambda: self.m.page(self.a, 'c2', token))
        self.reject('resync_required', lambda: self.m.page(self.a, 'c1', 'forged'))
        self.m.s['chats']['c1']['epoch'] += 1
        self.reject('resync_required', lambda: self.m.page(self.a, 'c1', token))
        self.reject('invalid_input', lambda: self.m.page(self.a, 'c1', limit=True))

    def test_conversation_paging_scope(self):
        self.m.create(self.a, 'c2'); self.m.create(self.b, 'private-b')
        p = self.m.conversations(self.a, limit=1)
        self.m.create(self.a, 'later')
        self.assertEqual(self.m.conversations(self.a, p['next_cursor'])['items'], ['c2'])
        self.reject('resync_required', lambda: self.m.conversations(self.b, p['next_cursor']))

    def test_end_summary_crash_redelivery_checkpoint(self):
        for i in range(3):
            self.m.receive(self.a, wire(str(i))); self.m.deliver(self.a, str(i))
            self.m.finish(self.a, str(i), {'terminal': 'completed'})
        boundary = self.m.end(self.a, 'c1')
        batch = self.m.summary_batch(self.a, 'c1')
        self.m = Model(self.m.image())
        self.assertEqual(boundary, self.m.end(self.a, 'c1'))
        self.assertEqual(batch, self.m.summary_batch(self.a, 'c1'))
        self.reject('checkpoint_conflict', lambda: self.m.ack_summary(self.a, 'c1', batch, None))
        self.m.ack_summary(self.a, 'c1', batch, 'fixture-memory-receipt')
        self.m = Model(self.m.image())
        tail = self.m.summary_batch(self.a, 'c1')
        self.assertEqual((tail['after'], tail['through']), (2, 3))
        self.assertEqual(tail['sources'][0]['raw'], wire('2'))
        self.reject('checkpoint_conflict', lambda: self.m.ack_summary(self.a, 'c1', batch, 'old'))
        self.reject('conversation_ended', lambda: self.m.receive(self.a, wire('new')))
        self.assertTrue(self.m.receive(self.a, wire('0'))['accepted'])

    def test_summary_waits_for_original_run_and_empty_end(self):
        self.m.receive(self.a, wire()); self.m.end(self.a, 'c1')
        self.reject('run_result_pending', lambda: self.m.summary_batch(self.a, 'c1'))
        self.m.create(self.a, 'empty'); self.m.end(self.a, 'empty')
        self.assertEqual(self.m.summary_batch(self.a, 'empty')['sources'], [])

    def test_email_invitation_unknown_never_authorizes(self):
        for a in (Authority('fixture-a'),
                  Authority('fixture-a', email_status='unverified'),
                  Authority('fixture-a', email_status='verified', eligible=False),
                  Authority('fixture-a', email_status='verified', eligible=None),
                  Authority('fixture-a', email_status='verified', identity_status='unknown'),
                  Authority('fixture-a', email_status='verified', identity_status='invalid')):
            self.reject('unavailable', lambda: self.m.receive(a, wire()))
            self.reject('unavailable', lambda: self.m.query(a, 'm1'))
        self.assertEqual(self.m.s['jobs'], {})

    def test_acceptance_is_not_dispatch_and_rechecks_email(self):
        self.m.receive(self.a, wire())
        self.assertEqual(self.m.s['runs'], {})
        blocked = Authority('fixture-a', email_status='unknown')
        self.reject('unavailable', lambda: self.m.deliver(blocked, 'm1'))
        self.assertEqual(self.m.query(self.a, 'm1')['state'], 'accepted_pending')

    def test_same_conversation_dispatch_order(self):
        self.m.receive(self.a, wire('first')); self.m.receive(self.a, wire('second'))
        self.reject('prior_run_pending', lambda: self.m.deliver(self.a, 'second'))
        self.m.deliver(self.a, 'first')
        self.m.finish(self.a, 'first', {'terminal': 'failed'})
        self.m.deliver(self.a, 'second')
        self.assertEqual(len(self.m.s['runs']), 2)

    def test_recovery_expiry_never_means_not_received(self):
        self.m.receive(self.a, wire())
        self.m.s['expired'].add((self.a.principal, 'receive', 'm1'))
        self.assertEqual(self.m.query(self.a, 'm1')['state'], 'recovery_expired')
        self.reject('recovery_expired', lambda: self.m.receive(self.a, wire()))

    def test_input_negative_examples(self):
        for raw in (b'null', b'{}', b'\xff', b'{"text":"a","text":"b"}'):
            self.reject('invalid_input', lambda raw=raw: parse(raw))
        p = parse(wire()); p['owner'] = 'forged'
        self.reject('invalid_input', lambda: parse(json.dumps(p).encode()))
        p = parse(wire()); p['version'] = 'future'
        self.reject('unsupported_version', lambda: parse(json.dumps(p).encode()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
