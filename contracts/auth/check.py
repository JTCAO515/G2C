"""Offline executable examples, not product authentication tests."""
import json
from pathlib import Path
import unittest
from model import Client, server_decision


class AuthExamples(unittest.TestCase):
    def signed_in(self, principal='synthetic-A', instance='process-1'):
        client = Client(instance)
        ticket = client.begin(new_login=True)
        self.assertTrue(client.complete(ticket, 'valid', principal, 's1', 'allowed'))
        return client

    def test_server_examples(self):
        document = json.loads(Path(__file__).with_name('examples.json').read_text())
        self.assertEqual(document['scope'], 'synthetic-only-not-wire-format')
        for case in document['cases']:
            with self.subTest(case=case['name']):
                self.assertEqual(server_decision(case['authority'], case['owners'],
                                                 case.get('caller_owner')), case['expected'])

    def test_logout_late_result(self):
        c = self.signed_in(); binding = c.capture()
        self.assertTrue(c.deliver(binding, 'private A'))
        pending = c.begin()
        c.logout()
        self.assertFalse(c.complete(pending, 'valid', 'synthetic-A', 's1', 'allowed'))
        self.assertFalse(c.deliver(binding, 'late A'))
        self.assertEqual(c.visible, [])
        self.assertFalse(c.credentials_present)
        self.assertEqual(c.remote_logout, 'unknown')

    def test_switch_late_result_and_invalid(self):
        c = self.signed_in(); old = c.capture(); pending = c.begin()
        login = c.begin(new_login=True)
        c.complete(login, 'valid', 'synthetic-B', 's1', 'allowed')
        self.assertFalse(c.deliver(old, 'A'))
        self.assertFalse(c.complete(pending, 'invalid'))
        self.assertEqual(c.principal, 'synthetic-B')
        self.assertTrue(c.deliver(c.capture(), 'B'))
        self.assertEqual(c.visible, ['B'])

    def test_same_account_relogin(self):
        c = self.signed_in(); old = c.capture(); c.logout()
        c.complete(c.begin(new_login=True), 'valid', 'synthetic-A', 's1', 'allowed')
        self.assertFalse(c.deliver(old, 'same identity but old lifetime'))

    def test_restart_binding(self):
        old = self.signed_in(); new = self.signed_in(instance='process-2')
        self.assertFalse(new.deliver(old.capture(), 'old process'))

    def test_network_unknown_retains_credential(self):
        c = self.signed_in(); old = c.capture()
        c.complete(c.begin(), 'unknown')
        self.assertTrue(c.credentials_present)
        self.assertEqual(c.state, 'unknown')
        self.assertFalse(c.deliver(old, 'late'))
        c.complete(c.begin(), 'valid', 'synthetic-A', 's2', 'allowed')
        self.assertEqual(c.state, 'eligible')
        self.assertFalse(c.deliver(old, 'old session revision'))

    def test_authoritative_invalid(self):
        c = self.signed_in(); old = c.capture()
        c.complete(c.begin(), 'invalid')
        self.assertFalse(c.credentials_present)
        self.assertIsNone(c.principal)
        self.assertEqual(c.state, 'invalid')
        self.assertFalse(c.deliver(old, 'late'))

    def test_duplicate_and_out_of_order_refresh(self):
        c = self.signed_in(); first = c.begin(); second = c.begin()
        self.assertTrue(c.complete(second, 'valid', 'synthetic-A', 's2', 'allowed'))
        self.assertFalse(c.complete(first, 'invalid'))
        self.assertFalse(c.complete(second, 'invalid'))
        self.assertEqual(c.revision, 's2')
        self.assertTrue(c.credentials_present)

    def test_eligibility_separate_from_identity(self):
        for eligibility, state in [('denied', 'restricted'), ('unknown', 'eligibility_unknown')]:
            with self.subTest(eligibility=eligibility):
                c = self.signed_in(); old = c.capture()
                c.complete(c.begin(), 'valid', 'synthetic-A', 's1', eligibility)
                self.assertTrue(c.credentials_present)
                self.assertEqual(c.principal, 'synthetic-A')
                self.assertEqual(c.state, state)
                self.assertFalse(c.deliver(old, 'restricted'))
                self.assertIsNone(c.capture())
                self.assertEqual(c.visible, [])

    def test_refresh_cannot_switch_identity(self):
        c = self.signed_in()
        self.assertFalse(c.complete(c.begin(), 'valid', 'synthetic-B', 's2', 'allowed'))
        self.assertEqual(c.state, 'unknown')
        self.assertEqual(c.principal, 'synthetic-A')
        self.assertIsNone(c.capture())

    def test_anonymous_and_pending_cannot_read(self):
        c = Client('process-1')
        self.assertFalse(c.deliver(None, 'private'))
        c.begin(new_login=True)
        self.assertIsNone(c.capture())

    def test_recheck_before_dispatch_or_commit(self):
        v = dict(environment='synthetic-new-cj', identity='valid', principal='synthetic-A',
                 session='current', eligibility='allowed')
        self.assertEqual(server_decision(v, ['synthetic-A']), 'allow')
        v['eligibility'] = 'denied'
        self.assertEqual(server_decision(v, ['synthetic-A']), 'eligibility_denied')
        v['eligibility'] = 'allowed'; v['session'] = 'revoked'
        self.assertEqual(server_decision(v, ['synthetic-A']), 'session_denied')


if __name__ == '__main__':
    unittest.main(verbosity=2)
