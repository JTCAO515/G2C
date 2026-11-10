"""Source-bound planning save for an explicitly admitted Lio publication."""
from datetime import time
import json

from cj_agent.draft import DraftRejected, PROPOSAL_TTL_SECONDS, proposal_id_for
from cj_feasibility.scoped_trip import check as check_scoped
from cj_feasibility.trip_time_v2 import evaluate
from cj_manual_edit.scoped import Request, preview, resolve
from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.domain import CommitUnknown, Conflict, Denied, Proposal, ProposalDetail, packed
from cj_trip.lio_history import EDIT_BASIS, PLAN_BASIS, TripHead, edit_action_id, plan_action_id
from cj_trip.needs_plan import MODEL_VERSION, parse_model
from cj_trip.postgres import Repository
from cj_trip.structured import FieldRejected, SourceRejected

from .needs_context import ContextPublisher, ContextSource


LIO_REPLAN_DELTA = 'TRIP-lio-replan-delta.1'
LIO_REPLAN_DELTA_V2 = 'TRIP-lio-replan-delta.2'


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
    system = ContextPublisher.system + (
        f' When current_trip is present in TRIP-source-input.2, use response version {LIO_REPLAN_DELTA_V2} '
        'instead of TRIP-model-plan.1. In that mode, return exactly version, items and proposed_subjects. '
        'Omit title. The server retains the saved title and every item in current_trip.content.items in saved '
        'order. Do not return any of those items or IDs. Return only new suggestions and any newly '
        'declared fixed NEEDS items absent from the saved Trip. Return items:[] and proposed_subjects:{} when '
        'the saved Trip already covers the request. In either format, copy the description of a required fixed '
        'NEEDS item absent from the current Trip verbatim as text and set source_category to "user_provided". '
        'Concise labels in the question language apply only to new suggestions.'
    )

    def __init__(self, original, confirmation, original_needs, check_lio_original):
        if type(confirmation) is not ConfirmationSigner:
            raise ValueError('Lio planning requires the original Trip signer')
        repository = Repository(original.repository.connect, original.repository.scope,
                                confirmation, structured=True)
        super().__init__(repository, LioContextSource(original.source, original_needs), original.clock)
        self.check_lio_original = check_lio_original

    def _model_plan(self, raw, context):
        value = parse_model(raw, versions=(MODEL_VERSION, LIO_REPLAN_DELTA, LIO_REPLAN_DELTA_V2),
                            source_title_versions=(LIO_REPLAN_DELTA_V2,))
        if type(value['items']) is not list:
            raise FieldRejected('items', 'Lio replan items must be a list')
        retained = json.loads(context.trip.content)
        if retained['sources']:
            raise SourceRejected('sources', 'Lio replan cannot omit retained Trip sources')
        if value['version'] == MODEL_VERSION:
            retained_ids = {item['id'] for item in retained['items']}
            echoed = [item for item in value['items'] if type(item) is dict
                      and type(item.get('id')) is str and item['id'] in retained_ids]
            if echoed != retained['items']:
                raise SourceRejected('items', 'legacy Lio replan changed retained Trip items')
            return value
        # Reuse the existing structured.2 and source checks on the composed
        # candidate. A model ID matching a retained ID fails as a duplicate.
        title = retained['title'] if value['version'] == LIO_REPLAN_DELTA_V2 else value['title']
        return dict(value, version=MODEL_VERSION, title=title, items=retained['items'] + value['items'])

    def build_plan(self, raw, capture):
        content, candidate, report = super().build_plan(raw, capture)
        snapshot, _ = capture.records()
        declared = {item['item_id'] for item in snapshot.fields.get('fixed_items', ())}
        context = self.source.contexts[capture.binding]
        if context is not None:
            declared.update(item['id'] for item in json.loads(context.trip.content)['items'])
        document = json.loads(content)
        for index, item in enumerate(document['items']):
            if item['id'] not in declared:
                start, end = item['schedule']['start'], item['schedule']['end']
                if (start['date']['state'] != 'known' or start['date'] != end['date']
                        or start['timezone']['state'] != 'known' or start['timezone'] != end['timezone']
                        or start['time']['state'] != 'known' or end['time']['state'] != 'known'
                        or time.fromisoformat(start['time']['value']) >= time.fromisoformat(end['time']['value'])):
                    raise SourceRejected(f'items[{index}].schedule', 'new Lio stop requires a same-day planned interval')
                # Only a new system suggestion has an application-owned edit
                # policy. Its canonical NEEDS/booking evidence stays unknown.
                item['fixed'] = {'state': 'known', 'value': False}
        return packed(document), candidate, report

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
        return self._save(binding, original, expected, capture, candidate, proposal,
                          plan_action_id(binding.run_id), before_publish)

    def publish_edit_for_message(self, binding, original, current, request_raw, edit_raw, capture, *,
                                 limits, before_publish):
        """Save one exact replacement selected by B from the original Lio turn."""
        self.source.check(binding, capture)
        context = self.source.contexts[binding]
        if current is None or current != original or capture.binding != binding or context is None:
            raise DraftRejected('original Lio edit context required')
        trip = context.trip
        expected = TripHead.from_trip(trip)
        self.require_lio(binding, original, expected)
        try:
            request = Request.parse(request_raw)
            if (request.text != json.loads(original.raw)['text'] or request.kind != 'items'
                    or len(request.selected) != 1):
                raise Conflict('edit requires one original item selection')
            result = preview(resolve(trip, request), edit_raw)
            candidate = result.candidate
            if (candidate is None or candidate.edit.order is not None
                    or len(candidate.edit.changes) != 1 or candidate.edit.changes[0][1] != 'text'):
                raise Conflict('only a single selected replacement is supported')
            replacement = json.loads(candidate.edit.changes[0][2])
            if replacement not in request.text:
                raise Conflict('replacement must come from the original message')
            same_snapshot = json.loads(context.needs_source)['snapshot'] == json.loads(capture.raw)['snapshot']
            needs, report, _ = check_scoped(candidate.content, capture, json.loads(context.proposed),
                                            result.scope.selected_ids, limits, retain_adopted=same_snapshot)
            if not any(check.code == 'PROTECTED_SCOPE_UNCHANGED' and check.status == 'PASS'
                       for check in report.checks):
                raise Conflict('original Needs protection could not be verified')
        except (Conflict, Denied, ValueError, KeyError, TypeError) as error:
            raise DraftRejected('Lio Trip edit refused') from error
        proposal = Proposal(proposal_id_for(binding.run_id), trip.trip_id, trip.version, EDIT_BASIS,
                            int(self.clock()) + PROPOSAL_TTL_SECONDS, candidate.content)
        return self._save(binding, original, expected, capture, needs, proposal,
                          edit_action_id(binding.run_id), before_publish)

    def _save(self, binding, original, expected, capture, candidate, proposal, action_id, before_publish):
        try:
            return self._commit(binding, original, expected, capture, candidate, proposal, action_id, before_publish)
        except CommitUnknown as error:
            raise LeaseUnavailable('original Lio Trip commit unknown; read the original receipt') from error
        except (Conflict, Denied) as error:
            raise DraftRejected('Lio Trip publication refused') from error

    def _commit(self, binding, original, expected, capture, candidate, proposal, action_id, before_publish):
        repository = self.repository
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
                        or receipt.candidate_hash != digest or status != 'accepted' or stored.basis_version != proposal.basis_version
                        or receipt.trip_id != proposal.trip_id or stored.content != proposal.content
                        or receipt.committed_version != proposal.expected_version + 1):
                    raise Conflict('original Lio Trip commit already differs')
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
