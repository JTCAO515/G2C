"""Opt-in ordinal planning over the original source/signer/sole commit seam."""
from copy import deepcopy
import json

from cj_agent.draft import PROPOSAL_TTL_SECONDS, proposal_id_for
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.domain import Proposal, packed
from cj_trip.lio_history import plan_action_id, TripHead
from cj_trip.postgres import Repository
from cj_trip.needs_plan import MODEL_VERSION, _build_model
from cj_trip.structured import SourceRejected
from cj_trip.structured_v3 import legacy_validation_view
from cj_feasibility.trip_time_v3 import evaluate

from .calendar_plan import compose, FIRST_PLAN, REPLAN_DELTA, DAY_SYSTEM
from .calendar_source import CalendarContextSource
from .lio_plan import LioPlanPublisher
from .needs_publisher import NeedsDraftPublisher
from .needs_context import ContextPublisher
from .calendar_commit import commit

PLAN_BASIS = 'lio-calendar-plan.1'


def needs_projection(document, capture, subjects, current):
    """Only a constraint-validation copy; no derived calendar enters canonical NEEDS."""
    before, _ = capture.records()
    original = {i['item_id']: i for i in before.fields.get('fixed_items', ())}
    prior = {} if current is None else {i['item_id']: i for i in json.loads(current.proposed).get('fixed_items', ())}
    adopted = {k: v for k, v in prior.items() if k not in original}
    projected = legacy_validation_view(document)
    projected['sources'] = []
    for item in projected['items']:
        item.update(verification='pending', evidence=[], source_refs=[], source_category='unknown')
        for event in item['schedule'].values():
            event['utc_offset'] = dict(state='unknown')  # NEEDS has no offset observation field.
        source = original.get(item['id'])
        if source is not None:
            item['fixed'] = deepcopy(source['locked'])
            if item['text'] == source['description']:
                item['source_category'] = 'user_provided'
            for edge in ('start', 'end'):
                # Fixed absolute-date facts stay original. Relative calendar mapping
                # is separately checked, not silently written into NEEDS fields.
                item['schedule'][edge]['date'] = deepcopy(source[edge]['date'])
        elif item['id'] in adopted:
            item['fixed'] = deepcopy(adopted[item['id']]['locked'])
        else:
            item['fixed'] = dict(state='unknown')
    value = dict(version=MODEL_VERSION, title=document['title'], items=projected['items'], proposed_subjects=subjects)
    _, candidate, report = _build_model(value, capture, adopted)
    return candidate, report


class LioCalendarPublisher(LioPlanPublisher):
    content_version = 'structured.3'
    publication_policy = 'LIO-day-calendar.1'

    def __init__(self, original, confirmation, original_needs, check_lio_original, calendar_reader, date_reader):
        if type(confirmation) is not ConfirmationSigner or date_reader is None:
            raise ValueError('original signer and read-only date-evidence source required')
        repository = Repository(original.repository.connect, original.repository.scope, confirmation,
                                structured=True, calendar=True)
        source = CalendarContextSource(original.source, original_needs, calendar_reader, repository)
        NeedsDraftPublisher.__init__(self, repository, source, original.clock)
        self.check_lio_original = check_lio_original
        self.date_reader = date_reader

    def model_messages(self, binding, text, capture, messages):
        context = self.source.contexts[binding]
        version = FIRST_PLAN if context is None else REPLAN_DELTA
        fields = 'version,title,items,proposed_subjects' if context is None else 'version,items,proposed_subjects'
        self.system = f'Return JSON with exactly {fields}; version "{version}". ' + DAY_SYSTEM
        data = dict(version='TRIP-calendar-source-input.1', day_count=capture.basis.day_count,
                    start_date=capture.basis.start_date, fixed_day_indices=capture.basis.day_indices())
        return ContextPublisher.model_messages(self, binding, text, capture, messages) + [
            dict(role='system', content=json.dumps(data, ensure_ascii=False, separators=(',', ':')))]

    def _commit(self, binding, original, expected, capture, candidate, proposal, action_id, before_publish):
        return commit(self, binding, original, expected, capture, candidate, proposal, action_id, before_publish)

    def build_plan(self, raw, capture):
        context = self.source.contexts[capture.binding]
        retained = None if context is None else json.loads(context.trip.content)
        before, _ = capture.records()
        count, start = capture.basis.day_count, capture.basis.start_date
        provisional = [dict(kind=k, state='unknown', day_indices=list(range(1, count+1)), item_ids=[],
                            reason='date_evidence_pending', evidence_refs=[]) for k in ('weather', 'day_opening')]
        content, subjects = compose(raw, before, capture.basis.day_indices(), count,
                                    start_date=start, retained=retained, date_checks=provisional)
        document = json.loads(content)
        if document['calendar']['state'] == 'dated':
            # Read already-collected, source-bound evidence only. The L adapter
            # dispatches any registered provider calls before publication locks.
            document['date_checks'] = self.date_reader.read(capture.binding, capture, document)
            content = packed(document)
            dates = {d['day_index']: d['date'] for d in document['days']}
            items = {i['id']: i for i in document['items']}
            for fixed in before.fields.get('fixed_items', ()):
                if fixed['locked'] == {'state': 'known', 'value': True}:
                    for edge in ('start', 'end'):
                        observed = fixed[edge]['date']
                        if observed['state'] == 'known' and observed['value'] != dates[items[fixed['item_id']]['schedule'][edge]['day_index']]:
                            raise SourceRejected('fixed_items', 'calendar contradicts original fixed date')
        timing = evaluate(content)
        if any(c.code in ('ITEM_TIME_REVERSED', 'ITEM_RELATIVE_REVERSED') for c in timing.checks):
            raise SourceRejected('schedule', 'planned interval order conflict')
        candidate, report = needs_projection(document, capture, subjects, context)
        return content, candidate, report

    def publish_for_message(self, binding, original, current, reply, capture, *, before_publish=None):
        context = self.source.contexts[binding]
        expected = None if context is None else TripHead.from_trip(context.trip)
        self.require_lio(binding, original, expected)
        content, candidate = self.validated_plan(binding, original, current, reply, capture, before_publish)
        proposal = Proposal(proposal_id_for(binding.run_id),
            'trip-'+binding.run_id if context is None else context.trip.trip_id,
            0 if context is None else context.trip.version, PLAN_BASIS,
            int(self.clock())+PROPOSAL_TTL_SECONDS, content)
        return self._save(binding, original, expected, capture, candidate, proposal,
                          plan_action_id(binding.run_id), before_publish)

    def convert_for_message(self, binding, original, current, raw, capture, *, before_publish):
        from .calendar_dates import convert
        return convert(self, binding, original, current, raw, capture, before_publish)

    def publish_edit_for_message(self, binding, original, current, request_raw, edit_raw, capture, *,
                                 limits, before_publish):
        from .calendar_edit import publish
        return publish(self, binding, original, current, request_raw, edit_raw, capture, before_publish)
