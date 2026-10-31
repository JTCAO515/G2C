"""Deterministic display data for a new explicit selection; never a candidate."""
from dataclasses import dataclass, field
import json

from cj_trip.domain import packed
from cj_trip.manual import ManualEdit, prepare as prepare_one
from cj_trip.manual_needs import EditV2, prepare as prepare_two


@dataclass(frozen=True, repr=False)
class ScopeExplanation:
    raw: bytes
    status: str
    can_publish: bool = field(default=False, init=False)


def _dates(items):
    observations = [item['schedule'][edge]['date'] for item in items for edge in ('start', 'end')]
    return dict(known=sorted({v['value'] for v in observations if v['state'] == 'known'}),
                incomplete=any(v['state'] != 'known' for v in observations))


def explain(scope, raw_edit=None):
    """Return bounded clarification/expansion data, or None for an in-scope edit.

    The original resolver and manual grammar/CAS/protection validators are reused.
    No model prose is interpreted as a date, selection, reason or permission.
    """
    before = json.loads(scope.original.content)
    items = before['items']
    original_selection = json.loads(scope.request.raw)['selection']
    base = dict(version='TRIP-scoped-explanation.1', trip_id=scope.original.trip_id,
                expected_version=scope.original.version, original_selection=original_selection,
                resolved_item_ids=list(scope.selected_ids))
    if scope.status != 'READY':
        unknown = [v['id'] for v in items if _dates([v])['incomplete']]
        cross_day = [v['id'] for v in items if len(_dates([v])['known']) > 1]
        observed = _dates(items)
        unmatched = sorted(set(scope.request.selected) - set(observed['known'])) if scope.request.kind == 'dates' else []
        base.update(status='CLARIFICATION_REQUIRED', reason_codes=['EXPLICIT_SELECTION_UNRESOLVED'],
                    reason=dict(zh=scope.reason_zh, en=scope.reason_en),
                    facts=dict(unknown_date_item_ids=unknown, cross_day_item_ids=cross_day,
                               unmatched_dates=unmatched, observed_dates=observed),
                    outside_item_ids=[], outside_dates=[], changes=[], required_selection=None)
    else:
        version = before['content_version']
        edit = (ManualEdit if version == 'structured.1' else EditV2).parse(raw_edit)
        if edit.request_id != scope.request.request_id:
            raise ValueError('retain the original scoped request ID')
        if any(name == 'fixed' for _, name, _ in edit.changes):
            raise ValueError('assistant cannot change fixed intent; use the explicit manual editor')
        # Discard the validator's candidate: this module exposes only display data.
        checked = (prepare_one if version == 'structured.1' else prepare_two)(scope.original, edit)
        after = json.loads(checked.content)
        originals = {v['id']: v for v in items}
        changes = []
        affected = set()
        for item_id, name, value in edit.changes:
            value = json.loads(value)
            if originals[item_id][name] != value:
                affected.add(item_id)
                changes.append(dict(item_id=item_id, field=name, before=originals[item_id][name], after=value))
        old_order = [v['id'] for v in items]
        if edit.order is not None and list(edit.order) != old_order:
            affected.update(v for index, v in enumerate(edit.order) if old_order[index] != v)
            changes.append(dict(item_id=None, field='order', before=old_order, after=list(edit.order)))
        whole_title = edit.title is not None
        title_changed = whole_title and edit.title != before['title']
        if whole_title:
            affected.update(old_order)
        if title_changed:
            changes.append(dict(item_id=None, field='title', before=before['title'], after=edit.title))
        outside = [v for v in old_order if v in affected and v not in scope.selected_ids]
        required_ids = [v for v in old_order if v in affected or v in scope.selected_ids]
        required_items = [v for v in items + after['items'] if v['id'] in required_ids]
        dates = _dates(required_items)
        outside_dates = sorted(set(dates['known']) - set(scope.request.selected)) if scope.request.kind == 'dates' else []
        if not outside and not outside_dates and not whole_title:
            return None
        codes = []
        if outside: codes.append('ITEMS_OUTSIDE_SELECTION')
        if outside_dates: codes.append('DATES_OUTSIDE_SELECTION')
        if whole_title: codes.append('WHOLE_TRIP_TITLE')
        zh = '这些具体变化超出原选区；请核对所需范围并重新明确选择。'
        en = 'These changes exceed the original selection; review the required scope and select again.'
        if whole_title:
            zh += '标题属于整份行程，当前局部选择不授权改标题。'
            en += ' A title belongs to the whole Trip; a local selection does not authorize a title change.'
        base.update(status='EXPANSION_REQUIRED', reason_codes=codes,
                    reason=dict(zh=zh, en=en),
                    outside_item_ids=outside, outside_dates=outside_dates, changes=changes,
                    required_selection=dict(item_ids=required_ids, dates=dates,
                                            whole_trip=whole_title,
                                            local_selection_sufficient=not whole_title))
    raw = packed(base)
    if len(raw) > 1_000_000:
        raise ValueError('bounded scope explanation required')
    return ScopeExplanation(raw, base['status'])
