"""Signed calendar read/storage over real limited-role PG, not seeded rows."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'backend/trip/tests'), str(ROOT/'backend/draft/tests'),
               str(ROOT/'backend/agent/tests'), str(ROOT/'backend/cj_api/tests'), str(ROOT/'scripts')]
import needs_actions_pg as needs_fixture
from e2e_local import Harness, CONNINFO
from registered_host_support import RegisteredHost
from cj_trip.local_calendar_read import create_local_calendar_read_app, VERSION
from cj_trip.local_structured_read import create_local_structured_read_app
from cj_trip.postgres import Repository
from cj_trip.domain import Proposal, packed
from cj_trip.confirmation import ConfirmationSigner
from cj_agent.draft import trip_scope_for
from cj_api.local_app import scope_for, ISSUER
from cj_message.travel import ABI
import dev_auth

FIXTURES = json.loads((ROOT/'contracts/trip/structured-examples.3.json').read_bytes())


class CalendarReadChecks(unittest.TestCase):
    headers = Harness.headers
    setup_source = needs_fixture.NeedsActionChecks.setup_source
    worker = needs_fixture.NeedsActionChecks.worker
    plan = needs_fixture.NeedsActionChecks.plan
    action = needs_fixture.NeedsActionChecks.action
    post = needs_fixture.NeedsActionChecks.post

    @classmethod
    def setUpClass(cls):
        Harness.setUpClass.__func__(cls)
        cls.host = RegisteredHost(cls.auth/'calendar', Path(CONNINFO),
            {s: (12, 2, 30000) for s in ('calendar', 'calendar-foreign', 'calendar-revoke')})
        cls.env = dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1', CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1')
        cls.signer = ConfirmationSigner(b'synthetic-calendar-pg-signer-123456789')
        for subject in cls.host.subjects:
            dev_auth.activate_travel(Path(CONNINFO), subject, cls.host.profiles[subject][1], ABI)

    tearDownClass = classmethod(Harness.tearDownClass.__func__)

    def reader(self, subject='calendar', **options):
        return create_local_calendar_read_app(conninfo_path=CONNINFO, auth_dir=self.host.auth,
            run_context=self.host.profiles[subject][1], **options)

    def saved(self):
        app, outcome, database = self.plan('calendar')
        with TestClient(app) as writer:
            accepted = self.post(writer, 'calendar', self.action('calendar', outcome, 'accept'))
            self.assertEqual(accepted.status_code, 200, accepted.text)
            legacy_id = accepted.json()['receipt']['trip_id']
        owner = scope_for(ISSUER, 'calendar')
        repository = Repository(lambda: database.connect(owner), trip_scope_for(owner), self.signer,
                                structured=True, calendar=True)
        content = packed(FIXTURES['base'])
        proposal = Proposal('calendar-pg-'+uuid.uuid4().hex, 'calendar-trip-'+uuid.uuid4().hex,
                            0, 'synthetic-calendar-read', int(time.time())+300, content)
        digest = repository.publish(proposal)
        signed = self.signer.issue(repository.scope, repository.proposal_detail(proposal.proposal_id),
            action_id='calendar-save-'+uuid.uuid4().hex, kind='accept', candidate_hash=digest)
        receipt = repository.act(signed.action)
        self.assertEqual(receipt.committed_version, 1)
        return legacy_id, proposal.trip_id, content

    def test_actual_signed_read_retains_three_days_legacy_and_owner_partition(self):
        legacy_id, trip_id, raw = self.saved()
        with TestClient(self.reader()) as client:
            response = client.get('/v6/trip-structured', params={'trip_id': trip_id}, headers=self.host.headers['calendar'])
            self.assertEqual(response.status_code, 200, response.text)
            trip = response.json()['trip']
            self.assertEqual(trip['content_sha256'], sha256(raw).hexdigest())
            self.assertEqual(packed(trip['content']), raw)
            self.assertEqual(trip['content']['days'], [{'day_index': 1}, {'day_index': 2}, {'day_index': 3}])
            page = client.get('/v2/trip-structured-list', headers=self.host.headers['calendar']).json()
            self.assertEqual(page['version'], VERSION)
            rows = {r['trip_id']: r for r in page['trips']}
            self.assertEqual(rows[trip_id]['calendar'], {'state': 'undated'})
            self.assertEqual(rows[trip_id]['day_count'], 3)
            self.assertIsNone(rows[legacy_id]['calendar'])
            self.assertIsNone(rows[legacy_id]['day_count'])
            foreign = client.get('/v6/trip-structured', params={'trip_id': trip_id}, headers=self.host.headers['calendar-foreign'])
            self.assertEqual(foreign.status_code, 200, foreign.text)
            self.assertIsNone(foreign.json()['trip'])
        old = create_local_structured_read_app(conninfo_path=CONNINFO, auth_dir=self.host.auth,
                                               run_context=self.host.profiles['calendar'][1])
        with TestClient(old) as client:
            unsupported = client.get('/v5/trip-structured', params={'trip_id': trip_id}, headers=self.host.headers['calendar'])
            self.assertEqual(unsupported.status_code, 503)
            self.assertNotIn('trip', unsupported.json())
            self.assertEqual(client.get('/v5/trip-structured', params={'trip_id': legacy_id}, headers=self.host.headers['calendar']).status_code, 200)
        with TestClient(self.reader(max_response_bytes=1)) as bounded:
            result = bounded.get('/v6/trip-structured', params={'trip_id': trip_id}, headers=self.host.headers['calendar'])
            self.assertEqual(result.status_code, 503)
            self.assertNotIn(trip_id, result.text)

    def test_revoked_identity_after_encoding_withholds_the_whole_page(self):
        from cj_trip import local_calendar_read as api
        invited = self.host.auth/'invited.json'
        original = invited.read_bytes()
        encode = api.compact

        def revoke(value):
            raw = encode(value)
            if value.get('version') == VERSION:
                invited.write_text(json.dumps([s for s in json.loads(original) if s != 'calendar-revoke']))
            return raw

        try:
            with TestClient(self.reader('calendar-revoke')) as client, patch.object(api, 'compact', revoke):
                response = client.get('/v2/trip-structured-list', headers=self.host.headers['calendar-revoke'])
                self.assertEqual(response.status_code, 503, response.text)
                self.assertNotIn('trips', response.json())
        finally:
            invited.write_bytes(original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
