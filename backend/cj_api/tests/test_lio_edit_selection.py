from datetime import date
import json
import unittest

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
    ('Replace the second afternoon with Temple of Heaven.', 'en', 'Temple of Heaven'),
    ('Replace the afternoon of day 2 with the Temple of Heaven, and keep the other plans.', 'en', 'the Temple of Heaven'),
    ('把第二天下午换成天坛，保留其他安排。', 'zh', '天坛'),
    ('把第二天下午换成「颐和园（北门）」。', 'zh', '颐和园（北门）'),
    ('Replace the afternoon of day 2 with “Museum of Arts and Design”.', 'en', 'Museum of Arts and Design'),
    ('把什刹海改成天坛', 'zh', '天坛'),
])
def test_edit_preserves_everything_outside_the_selected_stop(text, locale, replacement):
    trip, original = itinerary()
    result = select_lio_edit(trip, text, locale, 'original-edit', starts_on=date(2026,11,11))
    assert result.status == 'preview'
    assert result.candidate.affected_ids == ('afternoon',)
    assert result.candidate.can_publish is False
    after = json.loads(result.candidate.candidate.content)['items']
    assert after == [dict(item, text=replacement) if item['id'] == 'afternoon' else item for item in original]


@pytest.mark.parametrize('fixed', [known(True), dict(state='unknown')])
def test_locked_and_unknown_items_are_protected(fixed):
    trip, _ = itinerary(fixed)
    result = select_lio_edit(trip, '把第二天下午换成天坛', 'zh', 'original-edit', starts_on=date(2026,11,11))
    assert result.status == 'protected' and result.candidate is None


def test_ambiguous_interval_and_non_edit_leave_no_candidate():
    trip, _ = itinerary(overlap=True)
    assert select_lio_edit(trip, '把第二天下午换成天坛', 'zh', 'original-edit', starts_on=date(2026,11,11)).status == 'clarify'
    assert select_lio_edit(trip, '不要把第二天下午换成天坛', 'zh', 'original-edit', starts_on=date(2026,11,11)) is None


@pytest.mark.parametrize('text,locale', [
    ('Replace the afternoon of day 2 with Temple of Heaven, but do not change anything yet.', 'en'),
    ('Replace the afternoon of day 2 with Temple of Heaven only if it is open.', 'en'),
    ('把第二天下午换成颐和园，不过先别改。', 'zh'),
    ('把第二天下午换成颐和园，如果还开放。', 'zh'),
    ('Replace the afternoon of day 2 with Temple of Heaven—do not apply this change yet.', 'en'),
    ('Replace the afternoon of day 2 with Temple of Heaven or Summer Palace.', 'en'),
    ('把第二天下午换成颐和园但先缓一缓。', 'zh'),
    ('把第二天下午换成颐和园或者天坛。', 'zh'),
    ('把第二天下午换成颐和园或天坛。', 'zh'),
    ('把第二天下午换成故宫和天坛。', 'zh'),
    ('把第二天下午换成颐和园先问问我。', 'zh'),
    ('Replace the afternoon of day 2 with Temple of Heaven and Summer Palace.', 'en'),
    ('Replace the afternoon of day 2 with Temple of Heaven subject to my approval.', 'en'),
    ('Replace the afternoon of day 2 with “Temple of Heaven” subject to my approval.', 'en'),
    ('Replace the afternoon of day 2 with Temple of Heaven & Summer Palace.', 'en'),
    ('把第二天下午换成颐和园经我同意再执行。', 'zh'),
    ('把第二天下午换成「颐和园」经我同意再执行。', 'zh'),
    ('把第二天下午换成国家博物馆。', 'zh'),
])
def test_qualified_replacements_need_clarification(text, locale):
    trip, _ = itinerary()
    result = select_lio_edit(trip, text, locale, 'original-edit', starts_on=date(2026,11,11))
    assert result.status == 'clarify' and result.candidate is None

def test_missing_calendar_day_does_not_shift_an_edit_to_another_date():
    trip, _ = itinerary()
    # The stored Needs departure window starts on the 10th. The card starts
    # on the 11th because the 10th has no stops.
    starts_on = date(2026,11,10)
    relative = select_lio_edit(trip, '把第二天下午换成天坛', 'zh', 'original-edit', starts_on=starts_on)
    assert relative.status == 'clarify' and relative.candidate is None
    for text, locale in (('把2026-11-11下午换成天坛', 'zh'),
                         ('Replace the afternoon of 2026-11-11 with Temple of Heaven.', 'en')):
        exact = select_lio_edit(trip, text, locale, 'original-edit', starts_on=starts_on)
        assert exact.candidate.affected_ids == ('first',)


class LioRelativeDayTest(unittest.TestCase):
    def test_named_edit_keeps_to_inside_the_title(self):
        _, items = itinerary()
        title = 'Afternoon visit to Summer Palace'
        items[2]['text'] = title
        text = 'Replace Afternoon visit to Summer Palace with Jingshan Park and keep the other plans.'

        def select(stops, request=text):
            trip = Trip('trip-test', 2, packed(dict(
                content_version='structured.2', title='Beijing', items=stops, sources=[])))
            return select_lio_edit(trip, request, 'en', 'named-edit', starts_on=date(2026, 11, 11))

        result = select(items)
        self.assertEqual(result.status, 'preview')
        self.assertEqual(result.candidate.affected_ids, ('afternoon',))
        self.assertEqual(json.loads(result.candidate.candidate.content)['items'],
                         [dict(item, text='Jingshan Park') if item['id'] == 'afternoon' else item for item in items])
        self.assertEqual(select(items, f'Change {title} to “Walk to Jingshan Park”.').status, 'preview')
        self.assertEqual(select([dict(item, text=title) if item['id'] == 'evening' else item for item in items]).status,
                         'clarify')
        self.assertEqual(select([dict(item, fixed=known(True)) if item['id'] == 'afternoon' else item for item in items]).status,
                         'protected')

    def test_last_evening_uses_the_actual_last_calendar_day(self):
        trip, _ = itinerary()
        dates = dict(starts_on=date(2026, 11, 11), ends_on=date(2026, 11, 12))
        for text, locale in (
            ('把最后一天晚上换成天坛。', 'zh'),
            ('Replace the last evening with Temple of Heaven.', 'en'),
            ('Replace the evening of the final day with Temple of Heaven.', 'en'),
        ):
            with self.subTest(text=text):
                selected = select_lio_edit(trip, text, locale, 'last', **dates)
                self.assertEqual(selected.candidate.affected_ids, ('evening',))
                missing = select_lio_edit(trip, text, locale, 'missing', **dict(dates, ends_on=date(2026, 11, 13)))
                self.assertEqual(missing.status, 'clarify')
                self.assertIsNone(missing.candidate)
