"""Source-held rich publication through the existing confirmation/sole act path.

The host supplies an actual code Assembly and issued code checks. The first
checks adapter is explicitly undated; this module does not invent dated/H facts,
source permissions, a fallback outcome, or legacy calendar conversion.
"""
from contextvars import ContextVar
from hashlib import sha256
import json

from cj_agent.draft import DraftRejected, PROPOSAL_TTL_SECONDS, proposal_id_for, trip_scope_for
from cj_feasibility.trip_time_v3 import evaluate as time_check
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.domain import Conflict, Denied, Proposal, packed
from cj_trip.lio_history import TripHead, plan_action_id
from cj_trip.rich_source import VERSION as SOURCE_VERSION, capture as capture_rich_source
from cj_trip.rich_history import PLAN_BASIS
from cj_trip.structured import SourceRejected
from cj_trip.structured_v4 import ITEM_EXTRA, calendar_validation_view, parse, validate_candidate
from cj_trip.calendar_conversion import source_window_conflicts, fixed_date_conflicts

from .calendar_plan import compose, FIRST_PLAN, REPLAN_DELTA
from .lio_calendar import needs_projection
from .lio_plan import LioPlanPublisher
from .needs_publisher import NeedsDraftPublisher

def protected_records(capture, current, checks):
    """Code projection of actual NEEDS/current Trip, never model source records."""
    snapshot, _ = capture.records()
    retained = None
    if current is not None:
        retained = json.loads(current.trip.content)
        if retained['content_version'] == 'structured.4':
            retained = calendar_validation_view(retained)
        elif retained['content_version'] != 'structured.3':
            raise SourceRejected('current_trip', 'legacy calendar conversion requires its explicit source bridge')
    if retained is None and not snapshot.fields.get('fixed_items'):
        return []
    model = dict(version=FIRST_PLAN if retained is None else REPLAN_DELTA, items=[], proposed_subjects={})
    if retained is None: model['title'] = 'Captured protected items'
    raw, _ = compose(packed(model), snapshot, capture.basis.day_indices(), capture.basis.day_count,
                     start_date=capture.basis.start_date, retained=retained, date_checks=checks)
    document = json.loads(raw)
    needs_projection(document, capture, {}, current)
    if document['calendar']['state'] == 'dated':
        dates = tuple(day['date'] for day in document['days'])
        if fixed_date_conflicts(document, dates, snapshot.fields.get('fixed_items', ())):
            raise SourceRejected('fixed_items', 'calendar conflicts with an original fixed date')
    by_id = {item['id']: item for item in document['items']}
    result = []
    def add(provider, kind, reference, item):
        payload = dict(item=item)
        result.append(dict(provider=provider, kind=kind, reference=reference,
                           sha256=sha256(packed(payload)).hexdigest(), payload=payload))
    for item in snapshot.fields.get('fixed_items', ()):
        add('needs', 'fixed_item', f'{snapshot.needs_id}:{snapshot.version}:{item["item_id"]}', by_id[item['item_id']])
    if retained is not None:
        for item in retained['items']:
            add('trip', 'retained_item', f'{current.trip.trip_id}:{current.trip.version}:{item["id"]}', item)
    return result


class LioRichPublisher(LioPlanPublisher):
    content_version = 'structured.4'
    publication_policy = 'LIO-rich-pipeline.1'
    plan_source_version = 'TRIP-RICH-PLAN-SOURCE.1'

    def __init__(self, original, confirmation, source, check_lio_original, code_checks):
        repository = source.trip_repository
        if source.plan_source_version != self.plan_source_version:
            raise ValueError('explicit matching source/publisher version required')
        if (type(confirmation) is not ConfirmationSigner or repository.confirm is not confirmation
                or not repository.rich or code_checks is None):
            raise ValueError('explicit rich repository/original signer/code-check reader required')
        NeedsDraftPublisher.__init__(self, repository, source, original.clock)
        self.check_lio_original = check_lio_original
        self.code_checks = code_checks
        self._rich_plan = ContextVar('active_rich_candidate', default=None)

    def conditional_source(self, binding, capture, checks, document):
        """Conditional data for the assembler while the real source is held."""
        self.source.check(binding, capture)
        with self.source.message_context.hold_for_effect(binding) as message, \
                self.code_checks.hold(binding, checks, message) as check:
            check(document)
        current = self.source.contexts[binding]
        records = [*capture.provider_records, *checks.records,
                   *protected_records(capture, current, checks.checks)]
        profile = capture.profile
        raw = packed(dict(version=SOURCE_VERSION, original=profile.original, plan_now=profile.plan_now,
            policy=profile.policy, profile_states=profile.profile_states, records=records))
        return capture_rich_source(raw, expected_original=profile.original, expected_plan_now=profile.plan_now,
            expected_policy=profile.policy, accepted_profile_states=profile.profile_states, eligible_records=records)

    def publish_assembly_for_message(self, binding, original, current, assembly, capture, *,
                                     checks, proposed_subjects, before_publish):
        self.source.check(binding, capture)
        if (current is None or current != original or capture.binding != binding or before_publish is None
                or self.repository.scope != trip_scope_for(binding.scope)
                or assembly.content is None
                or assembly.status not in ('CONDITIONAL_SCHEDULE', 'UNCONFIRMED_SKELETON')
                or assembly.date_checks_must_be_recomputed):
            raise DraftRejected('actual complete source-held rich assembly required')
        document = parse(assembly.content)
        if assembly.status == 'UNCONFIRMED_SKELETON':
            if (not assembly.unconfirmed_items
                    or not set(assembly.unconfirmed_items) <= {item['id'] for item in document['items']}
                    or not set(assembly.unconfirmed_items) <= self.source.unavailable_targets(binding, capture)
                    or any(item['place']['state'] != 'unconfirmed' for item in document['items']
                           if item['id'] in assembly.unconfirmed_items)):
                raise DraftRejected('actual terminal tool outcomes must cover every unconfirmed fallback target')
        elif assembly.unconfirmed_items:
            raise DraftRejected('unconfirmed fallback needs its explicit assembly result')
        context = self.source.contexts[binding]
        expected = None if context is None else TripHead.from_trip(context.trip)
        self.require_lio(binding, original, expected)
        rich = self.conditional_source(binding, capture, checks, document)
        validate_candidate(document, rich)
        by_id = {item['id']: item for item in document['items']}
        for record in rich.document['records']:
            if (record['provider'], record['kind']) in (('needs', 'fixed_item'), ('trip', 'retained_item')):
                item = record['payload']['item']
                actual = by_id.get(item['id'])
                if actual is None or packed({k: v for k, v in actual.items() if k not in ITEM_EXTRA}) != packed(item):
                    raise SourceRejected('items', 'complete unchanged protected base set required')
        calendar = calendar_validation_view(document)
        snapshot, _ = capture.records()
        if source_window_conflicts(calendar, snapshot.fields) or time_check(packed(calendar)).status == 'CONFLICT':
            raise DraftRejected('known rich source/time conflict')
        candidate, _ = needs_projection(calendar, capture, proposed_subjects, context)
        proposal = Proposal(proposal_id_for(binding.run_id),
            'trip-'+binding.run_id if context is None else context.trip.trip_id,
            0 if context is None else context.trip.version, PLAN_BASIS,
            int(self.clock())+PROPOSAL_TTL_SECONDS, assembly.content)
        basis = json.loads(capture.raw)
        basis.update(version=self.plan_source_version, rich_source=json.loads(rich.raw),
                     provider_outcomes=self.source.provider_outcomes(binding, capture))
        raw_basis = packed(basis)
        if len(raw_basis) > self.source.max_bytes:
            raise DraftRejected('rich retained source exceeds original byte bound')
        with self.source.message_context.hold_for_effect(binding) as message, \
                self.code_checks.hold(binding, checks, message) as check:
            check(document)
            def final(*, check_trip=None):
                check(document)
                before_publish(check_trip=check_trip)  # Actual Trip eligibility, then original deadline last.
            token = self._rich_plan.set((binding, capture, raw_basis))
            try:
                return self._save(binding, original, expected, capture, candidate, proposal,
                                  plan_action_id(binding.run_id), final)
            finally:
                self._rich_plan.reset(token)

    def publish_candidate(self, cursor, proposal, binding, capture, candidate):
        """Retain the complete new source basis in the existing immutable table."""
        self.source.check(binding, capture)
        state = self._rich_plan.get()
        if state is None or state[0] != binding or state[1] is not capture:
            raise Denied('actual rich candidate frame required')
        raw = state[2]
        value = json.loads(raw)
        digest = self.repository._publish_in_tx(cursor, proposal)
        cursor.execute('SELECT source_sha256,proposed_input FROM cj_trip_needs_basis WHERE scope=%s AND proposal_id=%s',
                       (self.repository.scope, proposal.proposal_id))
        prior = cursor.fetchone()
        if prior is not None:
            if prior != (sha256(raw).hexdigest(), candidate.content):
                raise Conflict('immutable rich source basis changed')
        else:
            cursor.execute('INSERT INTO cj_trip_needs_basis(scope,proposal_id,message_scope,run_id,needs_scope,needs_id,needs_version,source_input,source_sha256,proposed_input) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (self.repository.scope, proposal.proposal_id, binding.scope, binding.run_id,
                 value['needs_scope'], value['needs_id'], value['revision'], raw, sha256(raw).hexdigest(), candidate.content))
        self.retain_trip_context(cursor, proposal, binding, capture)
        return digest
