from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import unittest

from validate_v3 import validate_entry_v3

ROOT = Path(__file__).resolve().parent
TODAY = date(2026, 11, 16)


class VenueSourceScopeTests(unittest.TestCase):
    def setUp(self):
        self.venue = json.loads((ROOT / 'entries-v3/venues-beijing-chengdu-xian.json').read_text())[0]

    def test_approved_institution_does_not_authorize_other_city_topic_or_city_wide_rule(self):
        validate_entry_v3(self.venue, as_of=TODAY)
        for change in ({'cities': ['chengdu']}, {'topic': 'transport'}, {'subject': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_entry_v3({**self.venue, **change}, as_of=TODAY)

    def test_candidate_identity_and_external_reservation_subdomains_are_not_accepted(self):
        for host in ('www.szmuseum.com', 'ticket.dpm.org.cn', 'reservation.shanghaimuseum.net',
                     'file.panda.org.cn', 'search.zj.gov.cn'):
            record = deepcopy(self.venue)
            record['source_urls'] = ['https://' + host + '/example']
            with self.subTest(host=host), self.assertRaises(ValueError):
                validate_entry_v3(record, as_of=TODAY)


if __name__ == '__main__':
    unittest.main()
