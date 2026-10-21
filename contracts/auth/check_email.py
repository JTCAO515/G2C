"""Offline policy samples; not real registration, mail delivery or recovery tests."""
import unittest
from email_policy import email_business_decision, flow_outcome
from model import Client


class EmailPolicyExamples(unittest.TestCase):
    def authority(self, **changes):
        return dict(environment='synthetic-new-cj', identity='valid', principal='synthetic-A',
                    session='current', eligibility='allowed', email_status='verified', **{}) | changes

    def test_verified_invited_can_access_own_resource(self):
        self.assertEqual(email_business_decision(self.authority(), ['synthetic-A']), 'allow')

    def test_email_and_invitation_are_separate(self):
        for email, eligibility, expected in [
            ('unverified', 'allowed', 'email_verification_required'),
            ('unknown', 'allowed', 'email_verification_unknown'),
            ('verified', 'denied', 'eligibility_denied'),
            ('verified', 'unknown', 'eligibility_unknown')]:
            with self.subTest(email=email, eligibility=eligibility):
                self.assertEqual(email_business_decision(self.authority(email_status=email,
                                 eligibility=eligibility), []), expected)

    def test_missing_email_check_is_not_verified(self):
        v = self.authority(); del v['email_status']
        self.assertEqual(email_business_decision(v, []), 'email_verification_unknown')

    def test_client_flags_cannot_grant_invitation_or_email(self):
        v = self.authority(eligibility='denied', caller_invited=True)
        self.assertEqual(email_business_decision(v, [], 'synthetic-A'), 'eligibility_denied')
        v = self.authority(email_status='unverified', caller_email_verified=True)
        self.assertEqual(email_business_decision(v, []), 'email_verification_required')

    def test_verification_does_not_bypass_identity_or_ownership(self):
        for changes, owners, expected in [
            ({'session': 'expired'}, [], 'session_denied'),
            ({'identity': 'invalid'}, [], 'identity_denied'),
            ({'identity': 'unknown'}, [], 'identity_unknown'),
            ({'environment': 'synthetic-old-product'}, [], 'identity_denied'),
            ({}, ['synthetic-B'], 'resource_denied')]:
            with self.subTest(expected=expected):
                self.assertEqual(email_business_decision(self.authority(**changes), owners), expected)

    def test_invitation_removed_before_dispatch(self):
        v = self.authority()
        self.assertEqual(email_business_decision(v, []), 'allow')
        v['eligibility'] = 'denied'
        self.assertEqual(email_business_decision(v, []), 'eligibility_denied')

    def test_success_samples_do_not_grant_business_access(self):
        samples = [('registration', 'accepted', 'verification_pending'),
                   ('verification', 'confirmed', 'reauthentication_required'),
                   ('recovery_request', 'accepted', 'recovery_request_acknowledged'),
                   ('password_reset', 'confirmed', 'password_changed_reauthenticate')]
        for flow, event, expected in samples:
            with self.subTest(flow=flow):
                self.assertEqual(flow_outcome(flow, event), expected)
                self.assertNotEqual(flow_outcome(flow, event), 'allow')

    def test_invalid_link_not_invalid_current_session(self):
        for flow, expected in [('verification', 'verification_link_invalid'),
                               ('password_reset', 'recovery_link_invalid')]:
            self.assertEqual(flow_outcome(flow, 'link_invalid'), expected)
        self.assertEqual(flow_outcome('login', 'session_invalid'), 'session_invalid')
        self.assertEqual(flow_outcome('login', 'rejected'), 'login_rejected')
        self.assertEqual(flow_outcome('login', 'unverified'), 'email_verification_required')

    def test_cancel_and_unknown_are_distinct_for_each_flow(self):
        for flow in ('registration', 'verification', 'login', 'recovery_request', 'password_reset'):
            with self.subTest(flow=flow):
                self.assertEqual(flow_outcome(flow, 'network_unknown'), 'outcome_unknown')
                self.assertEqual(flow_outcome(flow, 'user_cancelled'), 'cancelled_locally')

    def test_recovery_unknown_does_not_erase_existing_credentials(self):
        c = Client('synthetic-process')
        c.complete(c.begin(new_login=True), 'valid', 'synthetic-A', 's1', 'allowed')
        before = (c.generation, c.principal, c.credentials_present)
        self.assertEqual(flow_outcome('recovery_request', 'network_unknown'), 'outcome_unknown')
        self.assertEqual((c.generation, c.principal, c.credentials_present), before)
        # Semantic isolation only: there is no real SDK/session mutation in this fixture.

    def test_unsupported_flow_or_event_rejected(self):
        for flow, event in [('magic_default', 'accepted'), ('login', 'caller_invited'),
                            ('password_reset', 'allow')]:
            with self.assertRaises(ValueError):
                flow_outcome(flow, event)


if __name__ == '__main__':
    unittest.main(verbosity=2)
