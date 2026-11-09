import json

import pytest

from cj_api.lio_edit_selection import select_lio_edit
from cj_trip.domain import Trip, packed
from cj_trip.structured_v2 import validate_document


def known(value):
    return dict(state='known', value=value)


def stop(identifier, name, date, starts, ends, fixed):
    def event(clock):
        return dict(date=known(date), time=known(clock), timezone=known('Asia/Shanghai'),
                    utc_offset=dict(state='unknown'))

    return dict(id=identifier, text=name, verification='pending', evidence=[],
                schedule=dict(start=event(starts), end=event(ends)),
                fixed=fixed, source_category='unknown', source_refs=[])


def itinerary(fixed=None, *, overlap=False):
    items = [
        stop('first', '前门', '2026-11-11', '13:00', '14:00', known(False)),
        stop('morning', '故宫', '2026-11-12', '09:00', '10:00', known(True)),
        stop('afternoon', '什刹海', '2026-11-12', '13:00', '14:00', fixed or known(False)),
        stop('evening', '王府井', '2026-11-12', '19:00', '20:00', known(False)),
    ]
    if overlap:
        items.append(stop('crossing', '午餐', '2026-11-12', '11:30', '12:30', known(False)))
    document = dict(content_version='structured.2', title='北京两天', items=items, sources=[])
    validate_document(document)
    return Trip('trip-test', 2, packed(document)), items


@pytest.mark.parametrize('text,locale,replacement', [
    ('把第二天下午换成天坛。', 'zh', '天坛'),
    ('Could you replace the afternoon of day 2 with the Temple of Heaven?', 'en', 'the Temple of Heaven'),
    ('把什刹海改成天坛', 'zh', '天坛'),
])
def test_edit_preserves_everything_outside_the_selected_stop(text, locale, replacement):
    trip, original = itinerary()
    result = select_lio_edit(trip, text, locale, 'original-edit')
    assert result.status == 'preview'
    assert result.candidate.affected_ids == ('afternoon',)
    assert result.candidate.can_publish is False
    after = json.loads(result.candidate.candidate.content)['items']
    assert after == [dict(item, text=replacement) if item['id'] == 'afternoon' else item for item in original]


@pytest.mark.parametrize('fixed', [known(True), dict(state='unknown')])
def test_locked_and_unknown_items_are_protected(fixed):
    trip, _ = itinerary(fixed)
    result = select_lio_edit(trip, '把第二天下午换成天坛', 'zh', 'original-edit')
    assert result.status == 'protected' and result.candidate is None


def test_ambiguous_interval_and_non_edit_leave_no_candidate():
    trip, _ = itinerary(overlap=True)
    assert select_lio_edit(trip, '把第二天下午换成天坛', 'zh', 'original-edit').status == 'clarify'
    assert select_lio_edit(trip, '不要把第二天下午换成天坛', 'zh', 'original-edit') is None
