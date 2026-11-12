"""Calendar storage uses the same fresh private PG fixture as legacy Trip tests."""
import json
from pathlib import Path
import time
import pytest
from cj_trip.domain import Denied, Proposal, packed
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.postgres import Repository
from cj_trip.auth_boundary import Boundary
from cj_trip.operation import OperationWithheld
from test_trip import empty, connect
from test_operation import Checker
ROOT = Path(__file__).resolve().parents[3]
FIXTURES = json.loads((ROOT / 'contracts/trip/structured-examples.3.json').read_bytes())

def test_calendar_repository_is_explicit_and_uses_the_existing_signed_commit():
    content = packed(FIXTURES['base'])
    signer = ConfirmationSigner(b'synthetic-calendar-unit-signer-1234567890')
    proposal = Proposal('calendar-proposal', 'calendar-trip', 0, 'calendar-unit', int(time.time())+300, content)
    for legacy in (Repository(connect, 'A', signer), Repository(connect, 'A', signer, structured=True)):
        with pytest.raises(Denied):
            legacy.publish(proposal)
    writer = Repository(connect, 'A', signer, structured=True, calendar=True)
    digest = writer.publish(proposal)
    boundary = Boundary(Checker(), lambda _: (connect, 'A'), signer, structured=True, calendar=True)

    def accept(ctx):
        detail = ctx.proposal_detail(proposal.proposal_id)
        signed = signer.issue(ctx.metadata.scope, detail, action_id='calendar-save', kind='accept', candidate_hash=digest)
        receipt = ctx.act(signed.action)
        assert receipt.committed_version == 1
        assert ctx.detail(proposal.trip_id).content == content
        return b'{}'

    assert boundary.with_operation('synthetic', accept) == b'{}'
    assert writer.detail(proposal.trip_id).content == content
    with pytest.raises(Denied):
        Repository(connect, 'A', signer, structured=True).detail(proposal.trip_id)
    assert Repository(connect, 'B', signer, structured=True, calendar=True).detail(proposal.trip_id) is None


def test_calendar_capability_change_is_caught_before_publishing_bytes():
    boundary = Boundary(Checker(), lambda _: (connect, 'A'), structured=True, calendar=True)

    def change(_):
        boundary.calendar = False
        return b'{"private":"withhold"}'

    with pytest.raises((Denied, OperationWithheld)):
        boundary.with_operation('synthetic', change)
