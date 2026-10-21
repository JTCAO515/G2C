"""Synthetic UI/AUTH seam requirements, NOT a Swift host adapter or UI execution."""
from copy import deepcopy
import unittest
from model import Client


def language_only(before, after):
    """Language may change; identity and private state may not change with it."""
    return {k: v for k, v in before.items() if k != 'language'} == {
        k: v for k, v in after.items() if k != 'language'}


def private_projection_cleared(view):
    # Abstract body projection: external in UI@1.0, inside presentation in UI@1.1.
    return (view['draft'] == '' and view['context'] == (None, None)
            and view['assistantBody'] is None and view['memoryPath'] == []
            and view['pageStates'] == ('notConnected',) * 3)


class UISeams(unittest.TestCase):
    def login(self):
        c = Client('synthetic-process')
        c.complete(c.begin(new_login=True), 'valid', 'synthetic-A', 's1', 'allowed')
        return c

    def test_account_route_is_inside_memory(self):
        # These are abstract navigation samples, not executable MemoryRoute values.
        allowed = lambda tab, route: tab == 'memory' and route == 'account'
        self.assertTrue(allowed('memory', 'account'))
        for tab in ('account', 'assistant', 'trips', 'plugins'):
            with self.subTest(tab=tab):
                self.assertFalse(allowed(tab, 'account'))

    def test_language_keeps_session_and_generation(self):
        c = self.login()
        before = dict(language='en', binding=c.capture(), draft='private A',
                      tab='memory', path=['account'], context=('conversation-A', 'trip-A'))
        after = deepcopy(before); after['language'] = 'zh-Hans'
        self.assertTrue(language_only(before, after))
        # Counterexample: keying host/session lifetime by language logs out/replaces it.
        c.logout(); after['binding'] = c.capture()
        self.assertFalse(language_only(before, after))
        for key, value in [('draft', ''), ('context', (None, None)), ('path', [])]:
            after = deepcopy(before); after[key] = value
            with self.subTest(key=key):
                self.assertFalse(language_only(before, after))

    def test_generation_reset_includes_host_body_and_all_private_projection(self):
        c = self.login(); old = c.capture(); c.logout()
        clean = dict(draft='', context=(None, None), assistantBody=None,
                     memoryPath=[], pageStates=('notConnected',) * 3)
        self.assertTrue(private_projection_cleared(clean))
        self.assertFalse(c.deliver(old, 'late private A'))
        # Every omission must fail, including the body slot outside ShellState.
        for key, value in [('draft', 'A draft'), ('context', ('A conversation', None)),
                           ('assistantBody', 'A body'), ('memoryPath', ['group(facts)']),
                           ('pageStates', ('empty', 'notConnected', 'notConnected'))]:
            dirty = deepcopy(clean); dirty[key] = value
            with self.subTest(key=key):
                self.assertFalse(private_projection_cleared(dirty))

    def test_unknown_page_is_not_identity_rejection_or_authority(self):
        c = self.login(); generation = c.generation
        c.complete(c.begin(), 'unknown')
        for page in ('unknown', 'offline', 'failed'):
            with self.subTest(page=page):
                self.assertTrue(c.credentials_present)
                self.assertEqual(c.generation, generation)
                self.assertEqual(c.state, 'unknown')
                self.assertIsNone(c.capture())
                # No page-state -> invalid transition is invoked. A presentational
                # enum cannot be a trusted verification result, even when named failed.
                pending = c.begin()
                with self.assertRaises(ValueError):
                    c.complete(pending, 'page:' + page)
                c.complete(pending, 'unknown')


class UI11BindingSeams(unittest.TestCase):
    """Two independent gates required of a future host, not a Swift implementation."""
    def setUp(self):
        self.auth = Client('synthetic-process')
        self.auth.complete(self.auth.begin(new_login=True), 'valid', 'synthetic-A', 's1', 'allowed')
        self.ui_token = object()  # synthetic opaque per-instance/reset token

    def permits(self, auth_binding, ui_token):
        return (auth_binding is not None and auth_binding == self.auth.capture()
                and ui_token is self.ui_token)

    def test_reset_rejects_old_token_even_with_current_auth(self):
        binding, old_token = self.auth.capture(), self.ui_token
        self.assertTrue(self.permits(binding, old_token))
        self.ui_token = object()
        self.assertFalse(self.permits(binding, old_token))
        self.assertTrue(self.permits(binding, self.ui_token))

    def test_other_instance_token_rejected(self):
        self.assertFalse(self.permits(self.auth.capture(), object()))

    def test_fresh_ui_token_cannot_relabel_old_account_result(self):
        old_binding = self.auth.capture()
        self.auth.logout()
        self.ui_token = object()
        self.auth.complete(self.auth.begin(new_login=True), 'valid', 'synthetic-B', 's1', 'allowed')
        # Even passing the current UI token cannot turn an A result into B data.
        self.assertFalse(self.permits(old_binding, self.ui_token))
        self.assertTrue(self.permits(self.auth.capture(), self.ui_token))

    def test_unchanged_ui_token_cannot_bypass_session_or_unknown(self):
        old_binding = self.auth.capture()
        self.auth.complete(self.auth.begin(), 'unknown')
        self.assertFalse(self.permits(old_binding, self.ui_token))
        self.assertTrue(self.auth.credentials_present)
        self.auth.complete(self.auth.begin(), 'valid', 'synthetic-A', 's2', 'allowed')
        self.assertFalse(self.permits(old_binding, self.ui_token))
        self.assertTrue(self.permits(self.auth.capture(), self.ui_token))


if __name__ == '__main__':
    unittest.main(verbosity=2)
