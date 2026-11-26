from copy import deepcopy
from datetime import date
import unittest

from validate_v3 import validate_entry_v3

TODAY = date(2026, 11, 20)
# Synthetic Beijing venue fact with fixed dates, shaped like the former first catalogue record
# (palace-museum, retired 2026-11-26), so the source-scope probes do not depend on live entries.
SYNTHETIC_VENUE = {
    'format_version': 'visitor-entry.3', 'entry_kind': 'fact', 'topic': 'passport_booking',
    'id': 'visitor.example.v3-venue', 'cities': ['beijing'],
    'subject': {'key': 'beijing.example-venue', 'name_zh': '合成场馆',
                'name_en': 'Synthetic venue', 'wikidata_qid': None},
    'conditions': {'reservation_required': True, 'closed_weekdays': [1],
                   'closed_weekdays_public_holiday_exception': True,
                   'advance_booking_days': None, 'advance_booking_rule': None},
    'text_zh': '合成格式样例，不是已核对的游客须知。', 'text_en': 'Synthetic format sample, not reviewed visitor guidance.',
    'source_urls': ['https://www.dpm.org.cn/example-visit.html'],
    'checked_on': '2026-11-20', 'expires_on': '2026-12-04',
}


class VenueSourceScopeTests(unittest.TestCase):
    def setUp(self):
        self.venue = deepcopy(SYNTHETIC_VENUE)

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

    def test_later_official_sources_stay_within_approved_city_venue_scope(self):
        for host, city in (
            ('cgj.sz.gov.cn', 'shenzhen'), ('fao.sz.gov.cn', 'shenzhen'),
            ('english.shanghai.gov.cn', 'shanghai'), ('en.xa.gov.cn', 'xian'),
            ('bmy.com.cn', 'xian'), ('www.meet-in-shanghai.net', 'shanghai'),
        ):
            record = {**self.venue, 'cities': [city],
                      'source_urls': ['https://' + host + '/visitor-guide.html']}
            with self.subTest(host=host):
                validate_entry_v3(record, as_of=TODAY)
                for change in (
                    {'cities': ['beijing']}, {'cities': [city, 'beijing']},
                    {'topic': 'payment'}, {'topic': 'visa_entry'}, {'subject': None},
                    {'source_urls': ['https://ticket.' + host + '/visitor-guide.html']},
                ):
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        validate_entry_v3({**record, **change}, as_of=TODAY)

    def test_search_helper_and_unread_approved_attachment_do_not_become_fact_sources(self):
        for url in (
            'https://search.gd.gov.cn/search/all/755001',
            'https://arabic.shanghai.gov.cn/cmsres/fb/fb4c67ebf9604322a8b3f6f74d7e1760/eec310a1555eb5a02a121cee2922800d.pdf',
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_entry_v3({**self.venue, 'cities': ['shanghai'],
                                   'source_urls': [url]}, as_of=TODAY)

    def test_museum_linked_page_does_not_expand_to_other_urls_or_scopes(self):
        page = 'https://museum-guanwang.leleu.cn/'
        record = {**self.venue, 'cities': ['chengdu'], 'source_urls': [page]}
        validate_entry_v3(record, as_of=TODAY)
        for url in (page + 'orders', page + '?other=1', 'https://other.leleu.cn/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_entry_v3({**record, 'source_urls': [url]}, as_of=TODAY)
        for change in ({'cities': ['beijing']}, {'subject': None}, {'topic': 'payment'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_entry_v3({**record, **change}, as_of=TODAY)

    def test_one_institutional_media_report_does_not_authorize_its_host(self):
        for page in ('https://tidenews.com.cn/news.html?id=3612168',
                     'https://tidenews.com.cn/news.html?id=2858557'):
            record = {**self.venue, 'cities': ['taizhou-zhejiang'], 'source_urls': [page],
                      'subject': {'key': 'taizhou-zhejiang.museum', 'name_zh': '台州市博物馆',
                                  'name_en': 'Taizhou Museum (Zhejiang)', 'wikidata_qid': None}}
            with self.subTest(page=page):
                validate_entry_v3(record, as_of=TODAY)
                for url in (page + '&extra=1', 'https://tidenews.com.cn/news.html?id=1',
                            'https://tidenews.com.cn/', page.replace('tidenews.com.cn', 'other.tidenews.com.cn')):
                    with self.subTest(url=url), self.assertRaises(ValueError):
                        validate_entry_v3({**record, 'source_urls': [url]}, as_of=TODAY)
                for change in ({'cities': ['suzhou-anhui']}, {'cities': ['taizhou-zhejiang', 'shanghai']},
                               {'subject': None}, {'topic': 'payment'}, {'topic': 'visa_entry'}):
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        validate_entry_v3({**record, **change}, as_of=TODAY)

    def test_one_authorised_booking_channel_page_does_not_expand_its_platform(self):
        page = 'https://m.ctrip.com/webapp/you/sight/chengdu104/4229.html?ext-shelfPage=ctrip_shelf_seo'
        record = {**self.venue, 'cities': ['chengdu'], 'source_urls': [page],
                  'subject': {'key': 'chengdu.panda-base', 'name_zh': '成都大熊猫繁育研究基地',
                              'name_en': 'Chengdu Research Base of Giant Panda Breeding',
                              'wikidata_qid': None}}
        validate_entry_v3(record, as_of=TODAY)
        for url in (page + '&other=1', page.replace('4229', '1'),
                    'https://m.ctrip.com/', 'https://other.ctrip.com/webapp/you/sight/chengdu104/4229.html'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_entry_v3({**record, 'source_urls': [url]}, as_of=TODAY)
        for change in ({'cities': ['beijing']}, {'cities': ['chengdu', 'xian']},
                       {'subject': None}, {'topic': 'payment'}, {'topic': 'visa_entry'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_entry_v3({**record, **change}, as_of=TODAY)


    def test_one_platform_lakeside_page_does_not_authorize_the_whole_platform(self):
        page = 'https://www.trip.com/travel-guide/attraction/hangzhou/west-lake-82922'
        record = {**self.venue, 'cities': ['hangzhou'], 'source_urls': [page],
                  'subject': {'key': 'hangzhou.west-lake', 'name_zh': '西湖',
                              'name_en': 'West Lake', 'wikidata_qid': None}}
        validate_entry_v3(record, as_of=TODAY)
        for url in (page + '?extra=1', page.replace('82922', '1'),
                    'https://www.trip.com/', page.replace('www.trip.com', 'sg.trip.com')):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_entry_v3({**record, 'source_urls': [url]}, as_of=TODAY)
        for change in ({'cities': ['shenzhen']}, {'cities': ['hangzhou', 'chengdu']},
                       {'subject': None}, {'topic': 'payment'}, {'topic': 'visa_entry'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_entry_v3({**record, **change}, as_of=TODAY)


if __name__ == '__main__':
    unittest.main()
