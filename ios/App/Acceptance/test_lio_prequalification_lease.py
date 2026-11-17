import hashlib
import copy
import unittest
from datetime import datetime, timezone

from lio_basic_ui_driver import compact
from lio_prequalification_lease import validate_prequalification_lease, ReadOnlyApp


class NativeBoundary:
    simulator = '11111111-1111-4111-8111-111111111111'
    bundle = 'space.go2china.app'


class ReadOnlyLeaseTests(unittest.TestCase):
    def setUp(self):
        self.app = dict(source_commit='a' * 40, build='46', protocol='LIO-message.2', surface='simulator', fixture=False)
        self.sdk = dict(source_commit='b' * 40, controller_sha256='c' * 64)
        self.sims = dict(zh='11111111-1111-4111-8111-111111111111', en='22222222-2222-4222-8222-222222222222')
        self.identities = [dict(locale='zh', subject='synthetic-zh', default_conversation_id='existing-zh', default_generation='generation-zh'),
                           dict(locale='en', subject='synthetic-en', default_conversation_id='existing-en', default_generation='generation-en')]
        self.expected = dict(app=self.app, sdk=self.sdk, source='d' * 40, image='sha256:' + 'e' * 64,
                             simulator_udids=self.sims, identities=self.identities)
        self.value = dict(version='B-App-prequalification-lease.2', state='READ_ONLY_PREQUALIFICATION_ISSUED',
            purpose='C1048-basic14-official-App-read-only-prequalification', lease_id='synthetic-read-only',
            app=self.app, app_pin_sha256=hashlib.sha256(compact(self.app, sort_keys=True)).hexdigest(),
            sdk=self.sdk, sdk_pin_sha256=hashlib.sha256(compact(self.sdk, sort_keys=True)).hexdigest(),
            source=self.expected['source'], image=self.expected['image'], simulator_udids=self.sims,
            starts_at='2026-11-17T01:00:00Z', ends_at='2026-11-17T01:10:00Z', identities=self.identities,
            allowed_actions=['launch', 'activate', 'snapshot', 'open_existing_history', 'select_existing_default',
                             'earlier', 'scroll', 'audit_all', 'stop'])
        self.now = datetime(2026, 11, 17, 1, 1, tzinfo=timezone.utc)

    def check(self, value=None, *, raw=None, digest=None, now=None):
        raw = compact(self.value if value is None else value, sort_keys=True) if raw is None else raw
        return validate_prequalification_lease(raw, digest or hashlib.sha256(raw).hexdigest(),
                                             self.expected, now or self.now)

    def test_issued_read_only_packet_binds_the_complete_app_sdk_and_actual_default(self):
        identities = self.check()
        self.assertEqual(identities['zh'], self.identities[0])
        self.assertEqual(identities['en'], self.identities[1])

    def test_expired_future_naive_or_long_windows_never_grant_reads(self):
        changes = [dict(ends_at='2026-11-17T01:01:00Z'), dict(starts_at='2026-11-17T01:02:00Z'),
                   dict(ends_at='2026-11-17T01:10:01Z'),
                   dict(starts_at='2026-11-17T14:59:00Z', ends_at='2026-11-17T15:01:00Z'),
                   dict(starts_at='2026-11-17T01:00:00')]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.check(dict(self.value, **change))
        with self.assertRaises(ValueError):
            self.check(now=self.now.replace(tzinfo=None))

    def test_original_default_identity_is_not_an_optional_or_guessed_generation(self):
        for change in [dict(default_generation=None), dict(default_generation=1),
                       dict(default_generation=''), dict(default_conversation_id=''), dict(extra='not-approved')]:
            with self.subTest(change=change):
                identities = copy.deepcopy(self.identities)
                identities[0].update(change)
                self.expected['identities'] = identities
                with self.assertRaises(ValueError):
                    self.check(dict(self.value, identities=identities))
        same = [self.identities[0], self.identities[0]]
        self.expected['identities'] = same
        with self.assertRaises(ValueError):
            self.check(dict(self.value, identities=same))

    def test_complete_object_comparison_does_not_equate_false_with_zero(self):
        value = copy.deepcopy(self.value)
        value['app']['fixture'] = 0
        value['app_pin_sha256'] = hashlib.sha256(compact(value['app'], sort_keys=True)).hexdigest()
        with self.assertRaises(ValueError):
            self.check(value)

    def test_unknown_state_or_write_actions_cannot_be_used_as_read_permission(self):
        for change in [dict(version='B-App-login-lease.1'), dict(state='ACTIVE'),
                       dict(allowed_actions=self.value['allowed_actions'] + ['send']),
                       dict(allowed_actions=['official_sign_in']), dict(extra='unknown')]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.check(dict(self.value, **change))

    def test_malformed_freshness_pins_and_simulator_pair_fail_closed(self):
        cases = [dict(source='not-a-source'), dict(image='not-an-image'), dict(lease_id=''),
                 dict(simulator_udids=dict(zh='bad', en=self.sims['en'])),
                 dict(simulator_udids=dict(zh=self.sims['zh'], en=self.sims['zh']))]
        for change in cases:
            with self.subTest(change=change):
                expected = dict(self.expected, **{k: v for k, v in change.items() if k in self.expected})
                raw = compact(dict(self.value, **change), sort_keys=True)
                with self.assertRaises(ValueError):
                    validate_prequalification_lease(raw, hashlib.sha256(raw).hexdigest(), expected, self.now)

    def test_file_digest_strict_json_and_independent_sdk_pin_cannot_be_substituted(self):
        with self.assertRaises(ValueError):
            self.check(digest='0' * 64)
        for raw in [b'{"state":"ACTIVE",' + compact(self.value, sort_keys=True)[1:],
                    compact(self.value, sort_keys=True).replace(b'"fixture":false', b'"fixture":NaN')]:
            with self.assertRaises(ValueError):
                self.check(raw=raw)
        value = copy.deepcopy(self.value)
        value['sdk']['controller_sha256'] = 'f' * 64
        value['sdk_pin_sha256'] = hashlib.sha256(compact(value['sdk'], sort_keys=True)).hexdigest()
        with self.assertRaises(ValueError):
            self.check(value)

    def session(self, native, read=None, verify=lambda: None):
        raw = compact(self.value, sort_keys=True)
        return ReadOnlyApp(native, read or (lambda: raw), hashlib.sha256(raw).hexdigest(),
                           self.expected, 'zh', clock=lambda: self.now, verify_artifact=verify)

    def test_dispatch_has_fixed_read_only_selectors_and_cannot_type_tap_or_send(self):
        calls = []
        class Native(NativeBoundary):
            def command(self, kind, **fields):
                calls.append((kind, fields)); return {'kind': kind}
        session = self.session(Native())
        session.command('open_existing_history')
        session.command('earlier')
        session.command('scroll', direction='up')
        session.command('audit_all')
        self.assertEqual([(kind, fields.get('identifier')) for kind, fields in calls],
                         [('tap', 'lio.menu'), ('tap', 'lio.chat.history'), ('tap', 'lio.earlier'),
                          ('swipe_up', None), ('audit_all', None)])
        for action in ['type', 'tap', 'private_invite', 'send', 'new_chat']:
            before = len(calls)
            with self.assertRaises(ValueError): self.session(Native()).command(action)
            self.assertEqual(len(calls), before)

    def test_permission_change_between_menu_and_history_stops_before_the_second_tap(self):
        calls = []
        raw = compact(self.value, sort_keys=True)
        class Native(NativeBoundary):
            def command(self, kind, **fields): calls.append(kind); return {'kind': kind}
        session = self.session(Native(), read=lambda: raw if not calls else b'{}')
        with self.assertRaises(ValueError): session.command('open_existing_history')
        self.assertEqual(calls, ['tap'])
        with self.assertRaises(ValueError): session.command('snapshot')
        self.assertEqual(calls, ['tap'])

    def test_unknown_native_ack_is_sticky_and_does_not_retry(self):
        calls = []
        class Native(NativeBoundary):
            def command(self, kind, **fields):
                calls.append(kind); raise RuntimeError('Synthetic missing ACK')
        session = self.session(Native())
        with self.assertRaises(RuntimeError): session.command('activate')
        with self.assertRaises(ValueError): session.command('activate')
        self.assertEqual(calls, ['activate'])

    def test_changed_controller_device_cannot_use_another_locales_permission(self):
        calls = []
        class Native(NativeBoundary):
            def command(self, kind, **fields): calls.append(kind); return {'kind': kind}
        native = Native()
        native.simulator = self.sims['en']
        with self.assertRaises(ValueError): self.session(native).command('snapshot')
        native.simulator = self.sims['zh']; native.bundle = 'unrelated.app'
        with self.assertRaises(ValueError): self.session(native).command('launch')
        self.assertEqual(calls, [])

    def test_replaced_artifact_and_unmapped_default_stop_without_native_dispatch(self):
        calls = []
        class Native(NativeBoundary):
            def command(self, kind, **fields): calls.append(kind); return {'kind': kind}
        def changed_artifact(): raise ValueError('Synthetic changed binary')
        with self.assertRaises(ValueError): self.session(Native(), verify=changed_artifact).command('audit_all')
        with self.assertRaises(ValueError): self.session(Native()).command('select_existing_default')
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
