"""Opt-in grouped draft profiles; original publication/validation stays authoritative."""
import json

from cj_needs.domain import subjects as validate_subjects
from cj_strict_json import reject_duplicates
from cj_trip.domain import identifier, packed
from cj_trip.needs_plan import MODEL_VERSION
from cj_trip.structured import FieldRejected, MAX_ITEMS, SourceRejected, _date, _fields

from .calendar_plan import FIRST_PLAN, REPLAN_DELTA
from .lio_calendar import LioCalendarPublisher
from .lio_plan import LioSourceWindowPublisher, _expand_compact

DATED_FIRST = 'TRIP-lio-first-plan.2'
DATED_DELTA = 'TRIP-lio-replan-delta.4'
ORDINAL_FIRST = 'TRIP-lio-day-plan.2'
ORDINAL_DELTA = 'TRIP-lio-day-delta.2'


def system_for(*, retained, ordinal, guidance=''):
    version = (ORDINAL_DELTA if retained else ORDINAL_FIRST) if ordinal else (DATED_DELTA if retained else DATED_FIRST)
    fields = 'version,days' if retained else 'version,title,days'
    day = 'positive day_index' if ordinal else 'YYYY-MM-DD date'
    window = ('Use only the captured requested day indices, without inventing calendar dates. '
              if ordinal else 'Use only captured arrival.date through departure.date, inclusive, '
              'and respect known arrival/departure clock bounds. ')
    return (
        'Return only compact JSON, with no prose, Markdown, indentation or per-stop explanations. '
        'Use complete place names in the question language, without visit verbs or descriptions. '
        'The server retains every saved item, title, source and fixed commitment. Never repeat their IDs. '
        'Cover each requested date/day and requested time period; a fixed commitment covers only its own period. '
        'Do not shorten the trip, omit requested periods, or change existing/fixed arrangements to fit output. '
        'For each new stop explicitly supply its participants; do not infer party size or booking/evidence. '
        'Participant references are only self, party, or an actual companion:<id> from the source. '
        + window + guidance +
        f' Exact output has only {fields}; version="{version}". '
        'Use a short title for a first plan; omit title for a replan. '
        f'days is a list of [{day},rows] pairs, each day once. '
        'Each row is exactly [id,place_name,start_time,end_time,subjects], with short unique new IDs, '
        'HH:MM local times and an explicit subjects list such as ["self"]. '
        'The server supplies the confirmed NEEDS destination timezone and expands each day onto its rows. '
        'Do not repeat timezone/date/field names per stop. Do not return observation objects, sources, '
        'verification, evidence, fixed flags or a separate proposed_subjects map. '
        'Use days:[] if there are no new suggestions; close the complete JSON object.'
    )


def expand(raw, capture, *, retained, ordinal):
    """Decode the new external model shape; output is validation-only normalized data."""
    if type(raw) is not bytes or not 0 < len(raw) <= 1_000_000:
        raise FieldRejected('plan', 'bounded grouped model bytes required')
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate grouped field'))
    except (ValueError, RecursionError):
        raise FieldRejected('plan', 'strict complete grouped JSON required') from None
    _fields(value, {'version', 'days'} if retained else {'version', 'title', 'days'},
            'plan', 'exact grouped model fields required')
    expected = (ORDINAL_DELTA if retained else ORDINAL_FIRST) if ordinal else (DATED_DELTA if retained else DATED_FIRST)
    if value['version'] != expected:
        raise FieldRejected('version', 'explicit grouped first/delta profile required')
    if type(value['days']) is not list:
        raise FieldRejected('days', 'grouped day list required')
    snapshot, _ = capture.records()
    zone = snapshot.fields.get('destination_timezone')
    if zone is None or zone['state'] != 'known':
        raise SourceRejected('destination_timezone', 'confirmed source timezone required')
    if not ordinal:
        first, last, _ = LioSourceWindowPublisher._source_window(snapshot.fields)
    items, subjects, days = [], {}, set()
    for group in value['days']:
        if type(group) is not list or len(group) != 2:
            raise FieldRejected('days', 'exact day/rows pair required')
        day, rows = group
        if (ordinal and (type(day) is not int or day < 1)) or (not ordinal and type(day) is not str):
            raise FieldRejected('days', 'explicit date or positive integer day required')
        if ordinal:
            if day > capture.basis.day_count:
                raise FieldRejected('days', 'ordinal outside captured requested days')
        else:
            _date(day)
            if not first.isoformat() <= day <= last.isoformat():
                raise SourceRejected('days', 'day outside confirmed source window')
        if day in days:
            raise FieldRejected('days', 'one group per day required')
        days.add(day)
        if type(rows) is not list or len(items) + len(rows) > MAX_ITEMS:
            raise FieldRejected('items', 'bounded grouped stop list required')
        for row in rows:
            if type(row) is not list or len(row) != 5:
                raise FieldRejected('items', 'exact id/name/start/end/subjects row required')
            item_id, name, start, end, party = row
            identifier(item_id)
            if item_id in subjects:
                raise FieldRejected('items.id', 'duplicate new stop ID')
            validate_subjects(party)
            subjects[item_id] = party
            items.append(dict(id=item_id, text=name, start_time=start, end_time=end,
                              timezone=zone['value'], **{('day_index' if ordinal else 'date'): day}))
    return value, items, subjects


class LioGroupedPlanPublisher(LioSourceWindowPublisher):
    """Explicit dated opt-in. Retains the original source-window/signer/sole act."""
    def model_messages(self, binding, text, capture, messages):
        result = super().model_messages(binding, text, capture, messages)
        self.system = system_for(retained=self.source.contexts[binding] is not None,
                                 ordinal=False, guidance=self.draft_guidance)
        return result

    def _model_plan(self, raw, context, capture):
        value, items, subjects = expand(raw, capture, retained=context is not None, ordinal=False)
        saved = None if context is None else json.loads(context.trip.content)
        if saved is not None and saved['sources']:
            raise SourceRejected('sources', 'Lio replan cannot omit retained Trip sources')
        previous = [] if saved is None else saved['items']
        # This is the same server-side expansion used by the original compact
        # profile. Actual model wire/version remains in the original RUN evidence.
        return dict(version=MODEL_VERSION, title=value['title'] if saved is None else saved['title'],
                    items=previous + _expand_compact(items, capture, previous), proposed_subjects=subjects)


class LioGroupedCalendarPublisher(LioCalendarPublisher):
    """Explicit ordinal opt-in; calendar source leases and commit guards are unchanged."""
    def model_messages(self, binding, text, capture, messages):
        result = super().model_messages(binding, text, capture, messages)
        self.system = system_for(retained=self.source.contexts[binding] is not None, ordinal=True)
        return result

    def build_plan(self, raw, capture):
        retained = self.source.contexts[capture.binding] is not None
        value, items, subjects = expand(raw, capture, retained=retained, ordinal=True)
        normalized = dict(version=REPLAN_DELTA if retained else FIRST_PLAN, items=items, proposed_subjects=subjects)
        if not retained:
            normalized['title'] = value['title']
        return super().build_plan(packed(normalized), capture)
