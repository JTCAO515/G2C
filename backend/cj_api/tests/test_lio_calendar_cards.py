"""New card projection preserves the authoritative calendar and legacy isolation."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest

from cj_api.lio_trip_cards import _card, calendar_card
from cj_trip.domain import Denied, Trip, packed


ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = json.loads((ROOT / 'contracts/trip/structured-examples.3.json').read_bytes())


def revision(content):
    raw = packed(content)
    return Trip('calendar-card-test', 4, raw)


class CalendarCards(unittest.TestCase):
    def test_original_unversioned_card_keeps_its_legacy_projection(self):
        original=revision(dict(title='Original legacy Trip',items=[]))
        self.assertEqual(_card(original),dict(trip_id=original.trip_id,title='Original legacy Trip',days=[]))

    def test_undated_rest_days_remain_distinct_without_dates(self):
        original = revision(EXAMPLES['base'])
        card = calendar_card(original)
        self.assertEqual([day['day_index'] for day in card['days']], [1, 2, 3])
        self.assertTrue(all('date' not in day for day in card['days']))
        self.assertEqual([len(day['items']) for day in card['days']], [1, 0, 0])
        self.assertEqual(card['calendar'], {'state': 'undated'})
        self.assertEqual(card['date_checks'], EXAMPLES['base']['date_checks'])
        self.assertEqual((card['trip_version'], card['content_sha256']),
                         (original.version, sha256(original.content).hexdigest()))
        self.assertEqual(original.content, packed(EXAMPLES['base']))

    def test_dated_mapping_and_original_labels_are_preserved(self):
        card = calendar_card(revision(EXAMPLES['dated']))
        self.assertEqual([(day['day_index'], day['date']) for day in card['days']],
                         [(1, '2026-12-01'), (2, '2026-12-02'), (3, '2026-12-03')])
        self.assertEqual(card['days'][0]['items'][0]['label'],
                         EXAMPLES['dated']['items'][0]['text'])

    def test_old_card_rejects_calendar_content(self):
        for key in ('base', 'dated'):
            with self.subTest(key=key), self.assertRaises(Denied):
                _card(revision(EXAMPLES[key]))

    def test_legacy_card_does_not_claim_undated_calendar(self):
        content = deepcopy(EXAMPLES['dated'])
        content['content_version'] = 'structured.2'
        content.pop('calendar')
        content.pop('days')
        content.pop('date_checks')
        for item in content['items']:
            for edge in ('start', 'end'):
                item['schedule'][edge].pop('day_index')
                item['schedule'][edge]['date'] = dict(state='known', value='2026-12-01')
        original = revision(content)
        card = calendar_card(original)
        self.assertIsNone(card['calendar'])
        self.assertIsNone(card['date_checks'])
        self.assertEqual(card['days'], _card(original)['days'])


if __name__ == '__main__':
    unittest.main()
