"""Opt-in structured content still uses the original Proposal/confirmation/act."""
import time
import pytest
from test_trip import empty, connect, repo
from test_operation import Checker
from test_structured import document
from cj_trip.auth_boundary import Boundary
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.domain import Action, Denied, Proposal, packed
from cj_trip.postgres import Repository


def test_structured_only_versioned_host_sole_writer_and_old_read_refuses():
    signer = ConfirmationSigner(b'synthetic-private-fixture-key-1234567890')
    writer = Repository(connect, 'A', signer, structured=True)
    proposal = Proposal('structured-1', 'trip-structured', 0, 'manual-unbound',
                        int(time.time())+300, packed(document()))
    digest = writer.publish(proposal)
    with pytest.raises(Denied): repo().publish(proposal)
    with pytest.raises(Denied): repo().proposal_detail(proposal.proposal_id)
    boundary = Boundary(Checker(), lambda _:(connect, 'A'), signer, structured=True)
    def accept(ctx):
        prepared = signer.issue(ctx.metadata.scope, ctx.proposal_detail(proposal.proposal_id),
                                action_id='structured-save-1', kind='accept', candidate_hash=digest)
        receipt = ctx.act(prepared.action)
        assert receipt.committed_version == 1
        assert ctx.detail(proposal.trip_id).content == proposal.content
        assert ctx.query_action(receipt.action_id) == receipt
        return b'{}'
    assert boundary.with_operation('synthetic', accept) == b'{}'
    with pytest.raises(Denied): repo().detail(proposal.trip_id)
    with pytest.raises(Denied): repo().list_trips()
    assert writer.detail(proposal.trip_id).content == proposal.content
    assert repo('B').detail(proposal.trip_id) is None
    assert repo('B').query_action('structured-save-1') is None
    with pytest.raises(Denied): Repository(connect,'B',signer,structured=True).proposal_detail(proposal.proposal_id)
