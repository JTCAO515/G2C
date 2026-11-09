"""Source-bound planning save for an explicitly admitted Lio publication."""
import json

from cj_agent.draft import DraftRejected, PROPOSAL_TTL_SECONDS, proposal_id_for
from cj_feasibility.trip_time_v2 import evaluate
from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.domain import CommitUnknown, Conflict, Denied, Proposal, ProposalDetail
from cj_trip.lio_history import PLAN_BASIS, TripHead, plan_action_id
from cj_trip.postgres import Repository

from .needs_context import ContextPublisher, ContextSource


class LioContextSource(ContextSource):
    def __init__(self, original, original_needs):
        super().__init__(original.reader, original.message_context, original.revision_lease,
                         original.token_supplier, max_revisions=original.max_revisions,
                         max_bytes=original.max_bytes, trip_repository=original.trip_repository)
        self.original_needs = original_needs

    def _needs_reference(self, binding, stored):
        # B validates the persisted Lio original and returns its exact bound
        # (needs_id, version, content_sha256) using the scoped runtime cursor.
        with self.trip_repository.connect() as connection:
            with connection.cursor() as cursor:
                reference = self.original_needs(cursor, binding)
        if reference is None or reference[2] is None:
            raise LeaseUnavailable('original Lio NEEDS binding unavailable')
        return reference


class LioPlanPublisher(ContextPublisher):
    def __init__(self, original, confirmation, original_needs, check_lio_original):
        if type(confirmation) is not ConfirmationSigner:
            raise ValueError('Lio planning requires the original Trip signer')
        repository = Repository(original.repository.connect, original.repository.scope,
                                confirmation, structured=True)
        super().__init__(repository, LioContextSource(original.source, original_needs), original.clock)
        self.check_lio_original = check_lio_original

    def publish_for_message(self, binding, original, current, reply, capture, *, before_publish=None):
        # B's registered Lio original is an additional fence. The original
        # message, NEEDS and publication leases are still required.
        context = self.source.contexts[binding]
        trip = None if context is None else context.trip
        expected = None if trip is None else TripHead.from_trip(trip)
        self.require_lio(binding, original, expected)
        content, candidate = self.validated_plan(binding, original, current, reply, capture, before_publish)
        if evaluate(content).status == 'CONFLICT':
            raise DraftRejected('explicit Trip time conflict')
        proposal = Proposal(proposal_id_for(binding.run_id),
                            'trip-' + binding.run_id if trip is None else trip.trip_id,
                            0 if trip is None else trip.version,
                            PLAN_BASIS,
                            int(self.clock()) + PROPOSAL_TTL_SECONDS, content)
        try:
            return self._commit_plan(binding, original, expected, capture, candidate, proposal, before_publish)
        except CommitUnknown as error:
            raise LeaseUnavailable('original Lio plan commit unknown; read the original receipt') from error
        except (Conflict, Denied) as error:
            raise DraftRejected('Lio Trip publication refused') from error

    def _commit_plan(self, binding, original, expected, capture, candidate, proposal, before_publish):
        repository = self.repository
        action_id = plan_action_id(binding.run_id)
        action = pending = None

        def final(cur):
            self.source.check(binding, capture)
            self.require_lio(binding, original, expected)
            # B runs its original source guards first and the original budget
            # deadline last. The Trip DB clock check belongs between them.
            trip_checked = False

            def check_trip():
                nonlocal trip_checked
                trip_checked = False
                repository._final_action_eligibility(cur, action, pending)
                trip_checked = True

            before_publish(check_trip=check_trip)
            if not trip_checked:
                raise LeaseUnavailable('Lio final Trip confirmation check required')

        with repository.transaction(before_commit=final) as cur:
            existing = repository._receipt(cur, action_id)
            if existing is not None:
                receipt, _ = existing
                stored, digest, status = repository._proposal(cur, receipt.proposal_id)
                if (receipt.kind != 'accept' or receipt.proposal_id != proposal.proposal_id
                        or receipt.candidate_hash != digest or status != 'accepted' or stored.basis_version != PLAN_BASIS
                        or receipt.trip_id != proposal.trip_id or stored.content != proposal.content
                        or receipt.committed_version != proposal.expected_version + 1):
                    raise Conflict('original Lio plan already differs')
                return receipt
            self.source.check(binding, capture)
            self.check_trip_context(cur, binding, capture)
            digest = self.publish_candidate(cur, proposal, binding, capture, candidate)
            action = repository.confirm.issue(repository.scope, ProposalDetail(proposal, digest, 'pending'),
                action_id=action_id, kind='accept', candidate_hash=digest).action
            receipt, pending = repository._act_in_tx(cur, action)
            value = json.loads(capture.raw)
            cur.execute('INSERT INTO cj_trip_needs_current(scope,needs_scope,needs_id,trip_id,trip_version) '
                        'VALUES(%s,%s,%s,%s,%s) ON CONFLICT(scope,needs_scope,needs_id) DO UPDATE '
                        'SET trip_id=EXCLUDED.trip_id,trip_version=EXCLUDED.trip_version',
                        (repository.scope, value['needs_scope'], value['needs_id'],
                         receipt.trip_id, receipt.committed_version))
            return receipt

    def require_lio(self, binding, original, expected):
        if self.check_lio_original(binding, original, expected) is not True:
            raise LeaseUnavailable('original Lio publication admission required')
