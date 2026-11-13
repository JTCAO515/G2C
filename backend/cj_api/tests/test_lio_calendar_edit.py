"""Calendar selections feed C's actual replacement validator without shifting rest days."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from cj_api.lio_calendar_edit import select_calendar_edit
from cj_draft.calendar_edit import VERSION, replacement
from cj_trip.domain import Trip, packed
from cj_trip.manual import ManualEdit


BASE = json.loads((Path(__file__).resolve().parents[3] /
                   'contracts/trip/structured-examples.3.json').read_bytes())['base']


def trip(*, fixed=False, duplicate=False):
    content = deepcopy(BASE)
    item = content['items'][0]
    item.update(id='museum', text='City Museum', fixed=dict(state='known', value=fixed),
                source_category='unknown')
    for edge, clock in (('start', '13:00'), ('end', '14:00')):
        item['schedule'][edge].update(day_index=3, time=dict(state='known', value=clock))
    if duplicate:
        content['items'].append(dict(deepcopy(item), id='museum-other'))
    return Trip('calendar-edit-test', 2, packed(content))


class CalendarEdit(unittest.TestCase):
    def test_bilingual_day_selection_passes_original_c_edit_validator(self):
        original = trip()
        before = json.loads(original.content)
        for text, locale in (('把第三天下午换成「人民公园」', 'zh'),
                             ('Replace the afternoon of day 3 with "People Park".', 'en')):
            with self.subTest(text=text):
                selected = select_calendar_edit(original, text, locale, 'original-calendar-edit')
                self.assertEqual(selected.status, 'preview')
                self.assertEqual(selected.selected_ids, ('museum',))
                after = replacement(original, selected.request, ManualEdit._parse(selected.edit, VERSION))
                self.assertEqual(after['calendar'], before['calendar'])
                self.assertEqual(after['days'], before['days'])
                self.assertEqual(after['items'][0]['schedule'], before['items'][0]['schedule'])
                self.assertEqual(after['items'][0]['text'], '人民公园' if locale == 'zh' else 'People Park')

    def test_rest_day_does_not_shift_to_next_occupied_day(self):
        for text in ('把第二天下午换成人民公园', 'Replace the afternoon of day 2 with People Park.'):
            self.assertEqual(select_calendar_edit(trip(), text, 'en', 'edit').status, 'clarify')

    def test_duplicate_names_and_periods_do_not_expand_selection(self):
        for text in ('Replace City Museum with People Park.',
                     'Replace the afternoon of day 3 with People Park.'):
            self.assertEqual(select_calendar_edit(trip(duplicate=True), text, 'en', 'edit').status, 'clarify')

    def test_locks_unknown_protection_and_conditional_requests_stay_protected(self):
        self.assertEqual(select_calendar_edit(trip(fixed=True),
            'Replace City Museum with People Park.', 'en', 'edit').status, 'protected')
        for suffix in (' only if it is open.', ' but do not apply.', ' or Garden Park.'):
            selected = select_calendar_edit(trip(), 'Replace City Museum with People Park'+suffix, 'en', 'edit')
            self.assertEqual(selected.status, 'clarify')


if __name__ == '__main__':
    unittest.main()
