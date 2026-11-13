"""Explicit WP1 first-plan richness; no inferred saved-item classifications."""
from datetime import timedelta
import json
import re

from cj_strict_json import reject_duplicates
from cj_trip.domain import packed
from cj_trip.structured import FieldRejected, SourceRejected, _fields

from .grouped_plan import (DATED_FIRST, ORDINAL_FIRST, LioGroupedPlanPublisher,
                          LioGroupedCalendarPublisher, expand, system_for)
from .lio_plan import LioSourceWindowPublisher
from .rich_schema import Pace, PROFILES, SIGHT_COUNTS


def rich_system_for(*, ordinal, pace, guidance=''):
    """The same actual generation text is available to source-manifest assembly."""
    legacy = system_for(retained=False, ordinal=ordinal, guidance=guidance)
    shape = legacy.index(' Exact output has only ')
    return legacy[:shape] + (
        f' Exact output has only version,title,days; version="{PROFILES[ordinal, pace]}". '
        f'Each day is [date_or_day_index,sights,meals], with exactly {SIGHT_COUNTS[pace]} '
        'sights and exactly two meals (lunch and dinner). Each row is exactly '
        '[id,place_name,start_time,end_time,subjects], HH:MM local times, explicit subjects. '
        'Cover every captured requested day; use complete place names in the question language. '
        'Use distinct stops in the sights and meals groups; supply neither extra fields nor explanations. '
        'The server sorts the rows by start time; close the complete JSON object.'
    )


def normalize(raw, capture, *, ordinal, pace):
    """Validate the model boundary, then reuse original grouped/source guards."""
    if type(raw) is not bytes or not 0 < len(raw) <= 1_000_000:
        raise FieldRejected('plan', 'bounded rich model bytes required')
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate rich field'))
    except (ValueError, RecursionError):
        raise FieldRejected('plan', 'strict complete rich JSON required') from None
    _fields(value, {'version', 'title', 'days'}, 'plan', 'exact rich first-plan fields required')
    if value['version'] != PROFILES[ordinal, pace]:
        raise FieldRejected('version', 'selected rich first-plan profile required')
    if type(value['days']) is not list:
        raise FieldRejected('days', 'rich day list required')
    groups = []
    for group in value['days']:
        if type(group) is not list or len(group) != 3:
            raise FieldRejected('days', 'exact day/sights/meals group required')
        day, sights, meals = group
        if (type(sights) is not list or len(sights) != SIGHT_COUNTS[pace]
                or type(meals) is not list or len(meals) != 2):
            raise FieldRejected('days', 'selected sight count and two meals required')
        # The original decoder validates row shapes, identifiers, subjects,
        # dates and timezone. No names imply kind.
        groups.append([day, sights + meals])
    normalized = dict(version=ORDINAL_FIRST if ordinal else DATED_FIRST,
                      title=value['title'], days=groups)
    expand(packed(normalized), capture, retained=False, ordinal=ordinal)
    if ordinal:
        expected = set(range(1, capture.basis.day_count + 1))
    else:
        before, _ = capture.records()
        first, last, _ = LioSourceWindowPublisher._source_window(before.fields)
        expected = {(first + timedelta(days=n)).isoformat() for n in range((last-first).days + 1)}
    if {group[0] for group in groups} != expected:
        raise SourceRejected('days', 'every captured requested day required')
    # expand checks lengths and subjects; the original final publisher checks
    # actual time validity/order, source bounds, retained data and signing.
    for _, rows in groups:
        for row in rows:
            if any(type(clock) is not str or re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', clock) is None
                   for clock in row[2:4]):
                raise FieldRejected('items.time', 'explicit HH:MM clocks required')
        rows.sort(key=lambda row: row[2])
    return packed(normalized)


class _RichFirst:
    ordinal = False

    def __init__(self, *args, pace, **kwargs):
        if type(pace) is not Pace:
            raise ValueError('trusted code must supply a typed Pace')
        self.pace = pace
        self.generation_used = None
        super().__init__(*args, **kwargs)

    def _rich_first(self, capture):
        before, _ = capture.records()
        return self.source.contexts[capture.binding] is None and before.fields.get('fixed_items') == []

    def generation_profile(self, capture):
        return (PROFILES[self.ordinal, self.pace] if self._rich_first(capture)
                else super().generation_profile(capture))

    def model_messages(self, binding, text, capture, messages):
        result = super().model_messages(binding, text, capture, messages)
        if self._rich_first(capture):
            # Preserve all original source/subjects instructions, replacing only
            # the generation shape. The factory supplies a grounded/default pace.
            self.system = rich_system_for(ordinal=self.ordinal, pace=self.pace,
                                          guidance='' if self.ordinal else self.draft_guidance)
        self.generation_used = self.generation_profile(capture)
        return result


class LioRichFirstPlanPublisher(_RichFirst, LioGroupedPlanPublisher):
    def _model_plan(self, raw, context, capture):
        if self._rich_first(capture):
            raw = normalize(raw, capture, ordinal=False, pace=self.pace)
        return super()._model_plan(raw, context, capture)


class LioRichFirstCalendarPublisher(_RichFirst, LioGroupedCalendarPublisher):
    ordinal = True

    def build_plan(self, raw, capture):
        if self._rich_first(capture):
            raw = normalize(raw, capture, ordinal=True, pace=self.pace)
        return super().build_plan(raw, capture)
