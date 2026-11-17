"""Card3 visibly qualifies unconfirmed places without rewriting stored content."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest
from cj_api.lio_trip_cards import rich_card
from cj_trip.domain import Trip,packed

ROOT=Path(__file__).resolve().parents[3]
CASES=json.loads((ROOT/'contracts/trip/structured-examples.4.json').read_text())['cases']


class RichCardUnconfirmed(unittest.TestCase):
    def test_unconfirmed_places_are_marked_in_both_locales_and_keep_original_hash_and_items(self):
        value=deepcopy(CASES['unconfirmed']['content']);value['items'][0]['text']='Suggested museum'
        raw=packed(value);trip=Trip('rich-card-test',1,raw)
        for locale,prefix in [('zh','地点未确认：'),('en','Unconfirmed place: ')]:
            card=rich_card(trip,locale=locale)
            first=next(row for day in card['days']for row in day['items']if row['item_id']==value['items'][0]['id'])
            self.assertEqual(first['label'],prefix+'Suggested museum')
            self.assertEqual(card['content_sha256'],sha256(raw).hexdigest())
            self.assertEqual(sum(len(day['items'])for day in card['days']),len(value['items']))
        self.assertEqual(trip.content,raw)

    def test_marker_fits_frozen_label_bound_without_truncating_the_trip_or_item_set(self):
        value=deepcopy(CASES['unconfirmed']['content']);value['items'][0]['text']='x'*500
        trip=Trip('rich-card-test',1,packed(value));card=rich_card(trip,locale='en')
        label=next(row['label']for day in card['days']for row in day['items']if row['item_id']==value['items'][0]['id'])
        self.assertTrue(label.startswith('Unconfirmed place: '));self.assertLessEqual(len(label),500)
        self.assertEqual(json.loads(trip.content)['items'][0]['text'],'x'*500)

    def test_matched_place_label_is_unchanged(self):
        value=deepcopy(CASES['matched']['content']);card=rich_card(Trip('rich-card-test',1,packed(value)),locale='en')
        labels={row['item_id']:row['label']for day in card['days']for row in day['items']}
        for item in value['items']:
            if item['place']['state']=='matched':self.assertEqual(labels[item['id']],item['text'])


if __name__=='__main__':unittest.main()
