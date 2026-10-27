import base64
from dataclasses import replace
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from cj_auth.interfaces import Fact
from cj_api.app import create_app
from cj_api.trip_composition import build_trip_boundary, TripWireConfiguration
from cj_trip.auth_boundary import Boundary
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.domain import Action, Proposal, ProposalDetail, Conflict, Denied, packed
from test_composition import SyntheticFixture


def proposal():
    return Proposal('p1', 't1', 0, 'basis', 1000, packed({'title': 'Synthetic', 'items': [
        {'id': 'i1', 'text': 'Pending', 'verification': 'pending', 'evidence': []}]}))


class SignerChecks(unittest.TestCase):
    def test_binding_expiry_and_redacted_repr(self):
        clock = [100.0]
        signer = ConfirmationSigner(b'synthetic-key-not-a-real-secret!!', 30, lambda: clock[0])
        p = proposal(); detail = ProposalDetail(p, p.digest('A'), 'pending')
        prepared = signer.issue('A', detail, action_id='a1', kind='accept', candidate_hash=detail.candidate_hash)
        self.assertEqual(prepared.expires_at, 130)
        self.assertTrue(signer('A', prepared.action, p))
        self.assertFalse(signer('B', prepared.action, p))
        for change in ({'action_id': 'other'}, {'kind': 'reject'}, {'proposal_id': 'other'},
                       {'candidate_hash': '0' * 64}, {'confirmation_ref': 'caller-invented'}):
            self.assertFalse(signer('A', replace(prepared.action, **change), p))
        self.assertFalse(signer('A', prepared.action, replace(p, expected_version=1)))
        self.assertFalse(ConfirmationSigner(b'x' * 32, clock=lambda: 100)('A', prepared.action, p))
        clock[0] = 130
        self.assertFalse(signer('A', prepared.action, p))
        with self.assertRaises(Denied):
            signer.check_before_commit('A', prepared.action, p, 130)
        self.assertNotIn('synthetic-key', repr(signer))
        self.assertNotIn(prepared.action.confirmation_ref, repr(prepared))

    def test_issuance_rejects_stale_or_wrong_candidate(self):
        signer = ConfirmationSigner(b'x' * 32, clock=lambda: 900)
        p = proposal(); d = ProposalDetail(p, p.digest('A'), 'pending')
        result = signer.issue('A', d, action_id='a1', kind='reject', candidate_hash=d.candidate_hash)
        self.assertEqual(result.expires_at, p.expires_at)
        for detail, digest in [(replace(d, status='accepted'), d.candidate_hash), (d, '0' * 64),
                               (replace(d, candidate_hash='0' * 64), '0' * 64)]:
            with self.assertRaises(Conflict):
                signer.issue('A', detail, action_id='a1', kind='accept', candidate_hash=digest)
        with self.assertRaises(ValueError): ConfirmationSigner(b'short')
        with self.assertRaises(ValueError): ConfirmationSigner(b'x' * 32, True)
        with self.assertRaises(Denied):
            ConfirmationSigner(b'x' * 32, clock=lambda: float('nan')).issue(
                'A', d, action_id='a1', kind='accept', candidate_hash=d.candidate_hash)


class ConfirmationWireChecks(SyntheticFixture):
    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {'CJ_ENV': 'local'}); self.env.start(); self.addCleanup(self.env.stop)
        self.signer = ConfirmationSigner(b'x' * 32, clock=lambda: 100)
        self.connected = False
        def connect(): self.connected = True; raise AssertionError('no DB in wire fixture')
        self.boundary, self.modules = build_trip_boundary(environment='local', jwt_configuration=self.config,
            verification_keys=self.keys, access_provider=self.policy,
            resolve=lambda _: (connect, 'fixture-scope'), confirmation_validator=self.signer)
        self.options = TripWireConfiguration(1024, 2, 65536)
        self.app = create_app(_trip_boundary=self.boundary, _trip_configuration=self.options,
            _trip_modules=self.modules, _trip_confirmation_signer=self.signer)
        self.client = TestClient(self.app); self.addCleanup(self.client.close)
        self.headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}
        self.p = proposal()
        self.command = dict(action_id='a1', kind='accept', proposal_id='p1', candidate_hash=self.p.digest('fixture-scope'))

    def post(self, raw=None):
        return self.client.post('/v1/trip-confirmations', content=raw or json.dumps(self.command).encode(), headers=self.headers)

    def test_preparation_returns_bound_bytes_without_act(self):
        owner = self
        class Context:
            metadata = SimpleNamespace(scope='fixture-scope')
            def query_action(self, aid): return None
            def proposal_detail(self, pid): return ProposalDetail(owner.p, owner.command['candidate_hash'], 'pending')
            def act(self, _): raise AssertionError('prepare must never write a Trip')
        with patch.object(Boundary, 'with_operation', side_effect=lambda token, fn: fn(Context())):
            response = self.post(); self.assertEqual(response.status_code, 200, response.text)
            body = response.json(); action = Action(*json.loads(base64.b64decode(body['action_utf8_base64'])))
            self.assertTrue(self.signer('fixture-scope', action, self.p))
            self.assertEqual(body['request_id'], response.headers['X-Request-ID'])
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(body['proposal']['candidate_hash'], action.candidate_hash)
            self.assertEqual(body['expires_at'], 400)
        self.assertFalse(self.connected)

    def test_bad_input_and_real_auth_denial(self):
        for raw in (b'{}', b'[]', b'{"action_id":"a","action_id":"a"}', b'\xff',
                    json.dumps(dict(self.command, owner='attacker')).encode()):
            self.assertEqual(self.post(raw).status_code, 400)
        self.assertEqual(self.post(b'x' * 1025).status_code, 413)
        for invited in (Fact.NO, Fact.UNKNOWN):
            self.policy.invited = invited
            self.assertEqual(self.post().status_code, 503)
        self.assertFalse(self.connected)
        self.assertEqual(self.client.post('/v1/trip-confirmations', json=self.command).status_code, 401)
        with TestClient(create_app()) as disconnected:
            self.assertEqual(disconnected.post('/v1/trip-confirmations', json=self.command).status_code, 503)

    def test_committed_action_cannot_get_replacement_bytes(self):
        ctx = SimpleNamespace(query_action=lambda _: object())
        with patch.object(Boundary, 'with_operation', side_effect=lambda token, fn: fn(ctx)):
            result = self.post()
        self.assertEqual(result.status_code, 409)
        self.assertNotIn('action_utf8_base64', result.json())

    def test_changed_transaction_validator_disables_issuance(self):
        self.boundary.confirm = lambda *args: True
        self.assertEqual(self.post().status_code, 503)
        self.assertFalse(self.connected)


if __name__ == '__main__':
    unittest.main()
