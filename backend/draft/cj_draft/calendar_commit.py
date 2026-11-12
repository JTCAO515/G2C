"""Version3 wrappers share the original signer/_act_in_tx sole writer.

Legacy Lio publication is deliberately unchanged. This wrapper additionally
retains exact typed-operation bytes in the existing original-action ledger.
"""
import json

from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.domain import Conflict, ProposalDetail
from cj_trip.calendar_conversion import source_window_conflicts
from cj_trip.needs_action_store import NeedsActions


def commit(publisher, binding, original, expected, capture, candidate, proposal, action_id,
           before_publish, *, request=None, kind='accept'):
    repository = publisher.repository
    action = pending = None

    def final(cursor):
        publisher.source.check(binding, capture)
        publisher.require_lio(binding, original, expected)
        trip_checked = False

        def check_trip():
            nonlocal trip_checked
            trip_checked = False
            repository._final_action_eligibility(cursor, action, pending)
            trip_checked = True

        before_publish(check_trip=check_trip)
        if not trip_checked:
            raise LeaseUnavailable('calendar final Trip eligibility check required')

    with repository.transaction(before_commit=final) as cursor:
        if request is not None:
            previous = NeedsActions._previous(repository, cursor, request)
            if previous is not None:
                return previous
        else:
            previous = repository._receipt(cursor, action_id)
            if previous is not None:
                receipt, _ = previous
                stored, digest, status = repository._proposal(cursor, receipt.proposal_id)
                if (receipt.kind != kind or receipt.proposal_id != proposal.proposal_id
                        or receipt.candidate_hash != digest or status != 'accepted'
                        or stored.basis_version != proposal.basis_version or receipt.trip_id != proposal.trip_id
                        or stored.content != proposal.content or receipt.committed_version != proposal.expected_version+1):
                    raise Conflict('original calendar publication differs')
                return receipt
        publisher.source.check(binding, capture)
        publisher.check_trip_context(cursor, binding, capture)
        if kind == 'accept':
            snapshot, _ = capture.records()
            if source_window_conflicts(json.loads(proposal.content), snapshot.fields):
                raise Conflict('confirmed calendar source window rejected')
        digest = publisher.publish_candidate(cursor, proposal, binding, capture, candidate)
        action = repository.confirm.issue(repository.scope, ProposalDetail(proposal, digest, 'pending'),
            action_id=action_id, kind=kind, candidate_hash=digest).action
        receipt, pending = repository._act_in_tx(cursor, action)
        if request is not None:
            cursor.execute('INSERT INTO cj_trip_needs_action(scope,action_id,proposal_id,original_input,original_action) '
                'VALUES(%s,%s,%s,%s,%s)', (repository.scope, request.action_id, proposal.proposal_id, request.raw, action.raw()))
        if receipt.committed_version is not None:
            source = json.loads(capture.raw)
            cursor.execute('INSERT INTO cj_trip_needs_current(scope,needs_scope,needs_id,trip_id,trip_version) '
                'VALUES(%s,%s,%s,%s,%s) ON CONFLICT(scope,needs_scope,needs_id) DO UPDATE '
                'SET trip_id=EXCLUDED.trip_id,trip_version=EXCLUDED.trip_version',
                (repository.scope, source['needs_scope'], source['needs_id'], receipt.trip_id, receipt.committed_version))
        return receipt
