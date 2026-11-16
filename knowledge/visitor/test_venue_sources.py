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
        for host in ('www.szmuseum.com', 'www.xixishidi.cn', 'www.szwwco.com', 'ticket.dpm.org.cn', 'reservation.shanghaimuseum.net',
                     'file.panda.org.cn', 'search.zj.gov.cn'):
            record = deepcopy(self.venue)
            record['source_urls'] = ['https://' + host + '/example']
            with self.subTest(host=host), self.assertRaises(ValueError):
                validate_entry_v3(record, as_of=TODAY)

    def test_provincial_source_still_requires_one_explicit_venue_city(self):
        record = deepcopy(self.venue)
        record['source_urls'] = ['https://ct.zj.gov.cn/example-venue.html']
        for city in ('hangzhou', 'taizhou-zhejiang'):
            validate_entry_v3({**record, 'cities': [city]}, as_of=TODAY)
        for cities in (['beijing'], ['hangzhou', 'taizhou-zhejiang']):
            with self.subTest(cities=cities), self.assertRaises(ValueError):
                validate_entry_v3({**record, 'cities': cities}, as_of=TODAY)

    def test_one_approved_static_page_does_not_authorize_its_cdn(self):
        record = deepcopy(self.venue)
        record['cities'] = ['shenzhen']
        page = 'https://cdn3.shenzhenmuseum.com/museum/html/aboutus/visit-service.html'
        validate_entry_v3({**record, 'source_urls': [page]}, as_of=TODAY)
        for url in (page + '?extra=1', 'https://cdn3.shenzhenmuseum.com/other.html'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_entry_v3({**record, 'source_urls': [url]}, as_of=TODAY)

    def test_one_static_guide_approval_does_not_expand_cdn_or_city(self):
        guide = 'https://cdn3.shenzhenmuseum.com/museum/html/aboutus/visit-service.html'
        record = {**self.venue, 'cities': ['shenzhen'], 'source_urls': [guide]}
        validate_entry_v3(record, as_of=TODAY)
        for url in (guide + '?copy=1', guide.replace('visit-service', 'other'),
                    'https://cdn3.shenzhenmuseum.com/example.pdf'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_entry_v3({**record, 'source_urls': [url]}, as_of=TODAY)
        with self.assertRaises(ValueError):
            validate_entry_v3({**record, 'cities': ['suzhou-anhui']}, as_of=TODAY)

    def test_hangzhou_delegated_sources_do_not_authorize_city_wide_or_other_city_claims(self):
        for host in ('www.ehangzhou.gov.cn', 'wgly.hangzhou.gov.cn'):
            record = deepcopy(self.venue)
            record['cities'] = ['hangzhou']
            record['subject'] = {'key': 'hangzhou.west-lake', 'name_zh': '西湖',
                                 'name_en': 'West Lake', 'wikidata_qid': None}
            record['source_urls'] = ['https://' + host + '/example.html']
            with self.subTest(host=host):
                validate_entry_v3(record, as_of=TODAY)
                for change in ({'cities': ['chengdu']}, {'cities': ['hangzhou', 'taizhou-zhejiang']},
                               {'topic': 'payment'}, {'subject': None}):
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        validate_entry_v3({**record, **change}, as_of=TODAY)


if __name__ == '__main__':
    unittest.main()
