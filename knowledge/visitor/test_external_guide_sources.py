"""Exact public-source permissions do not grant an entire website."""
from datetime import date
import json
from pathlib import Path
import unittest

from validate_v3 import validate_entry_v3


class ExternalGuideSourceScopeTests(unittest.TestCase):
    def test_fucheng_maintenance_notice_keeps_exact_local_venue_boundary(self):
        page = 'https://sight.qunar.com/11714'
        self._check_venue_source_scope(
            page=page, city='taizhou-zhejiang', wrong_city='suzhou-anhui',
            invalid_urls=(page + '?extra=1', page.replace('11714', '11715'),
                          'https://sight.qunar.com/',
                          page.replace('sight.qunar.com', 'piao.qunar.com')))

    def test_ctrip_lianhua_page_keeps_exact_url_and_shenzhen_venue_boundary(self):
        page = 'https://you.ctrip.com/sight/shenzhen26/50541.html'
        self._check_venue_source_scope(
            page=page, city='shenzhen', wrong_city='chengdu',
            invalid_urls=(page + '?extra=1', page.replace('50541', '50542'),
                          'https://you.ctrip.com/',
                          page.replace('you.ctrip.com', 'm.ctrip.com')))

    def test_ruqin_guide_keeps_exact_url_and_xian_venue_boundary(self):
        page = 'https://ruqintravel.com/china-destination-guides/big-wild-goose-pagoda/'
        self._check_venue_source_scope(
            page=page, city='xian', wrong_city='chengdu',
            invalid_urls=(page + '?extra=1', page.replace('big-wild', 'small-wild'),
                          'https://ruqintravel.com/', 'https://ruqintravel.com/about-ruqin/',
                          page.replace('ruqintravel.com', 'www.ruqintravel.com')))

    def test_dufu_report_keeps_exact_url_and_chengdu_venue_boundary(self):
        page = 'https://sichuan.scol.com.cn/ggxw/202502/82903345.html'
        self._check_venue_source_scope(
            page=page, city='chengdu', wrong_city='xian',
            invalid_urls=(page + '?extra=1', page.replace('82903345', '82903346'),
                          'https://sichuan.scol.com.cn/',
                          page.replace('sichuan.scol.com.cn', 'other.scol.com.cn')))

    def test_world_window_guide_keeps_exact_url_and_shenzhen_venue_boundary(self):
        page = 'https://www.shenzhen-tickets.com/window-of-the-world/timings-opening-hours/'
        self._check_venue_source_scope(
            page=page, city='shenzhen', wrong_city='hangzhou',
            invalid_urls=(page + '?extra=1', page.replace('timings-opening-hours/', 'other/'),
                          'https://www.shenzhen-tickets.com/',
                          page.replace('www.shenzhen-tickets.com', 'book.shenzhen-tickets.com')))

    def test_park_platform_pages_keep_exact_local_venue_boundaries(self):
        cases = (
            ('https://www.traveloka.com/en-sg/activities/china/product/xixi-wetland-park-admission-ticket-peaceful-oasis-near-west-lake-7621127360134',
             'hangzhou', 'chengdu', '7621127360134', '7621127360135'),
            ('https://gs.ctrip.com/html5/you/sight/suzhou672/5577341.html',
             'suzhou-anhui', 'taizhou-zhejiang', '5577341', '5577342'),
        )
        for page, city, wrong_city, old_id, other_id in cases:
            self._check_venue_source_scope(
                page=page, city=city, wrong_city=wrong_city,
                invalid_urls=(page + '?extra=1', page.replace(old_id, other_id),
                              page.split('/')[0] + '//' + page.split('/')[2] + '/',
                              page.replace('https://', 'https://other.')))

    def test_panda_official_attachment_keeps_exact_url_and_chengdu_venue_boundary(self):
        page = 'https://m.panda.org.cn/cn/education/trends/2025-01-17/8632.html'
        self._check_venue_source_scope(
            page=page, city='chengdu', wrong_city='xian',
            invalid_urls=(page + '?extra=1', page.replace('8632', '8633'),
                          'https://m.panda.org.cn/',
                          page.replace('m.panda.org.cn', 'other.panda.org.cn')))

    def _check_venue_source_scope(self, *, page, city, wrong_city, invalid_urls):
        root = Path(__file__).resolve().parent
        # Explicit source fixtures, independent of the implementation's allowlist.
        record = json.loads((root / 'entries-v3/venues-beijing-chengdu-xian.json').read_text())[0]
        record = {**record, 'cities': [city], 'source_urls': [page],
                  'subject': {'key': f'{city}.example-venue', 'name_zh': '合成场馆',
                              'name_en': 'Synthetic venue', 'wikidata_qid': None}}
        with self.subTest(allowed=page):
            validate_entry_v3(record, as_of=date(2026, 11, 20))
        for url in invalid_urls:
            with self.subTest(page=page, url=url), self.assertRaises(ValueError):
                validate_entry_v3({**record, 'source_urls': [url]}, as_of=date(2026, 11, 20))
        for change in ({'cities': [wrong_city]}, {'cities': [city, 'beijing']},
                       {'subject': None}, {'topic': 'payment'}, {'topic': 'visa_entry'}):
            with self.subTest(page=page, change=change), self.assertRaises(ValueError):
                validate_entry_v3({**record, **change}, as_of=date(2026, 11, 20))

    def test_fucheng_listing_keeps_exact_url_and_taizhou_venue_boundary(self):
        page = ('https://map.baidu.com/mobile/webapp/search/search/'
                'qt%3Ds%26wd%3D%E5%8F%B0%E5%B7%9E%E5%BA%9C%E5%9F%8E%E5%A2%99/')
        self._check_venue_source_scope(
            page=page, city='taizhou-zhejiang', wrong_city='suzhou-anhui',
            invalid_urls=(page + '?extra=1',
                          page.replace('%E5%A2%99/', '%E5%A2%99%E5%8D%9A%E7%89%A9%E9%A6%86/'),
                          'https://map.baidu.com/', page.replace('map.baidu.com', 'other.baidu.com')))

    def test_yuewang_report_keeps_exact_url_and_hangzhou_venue_boundary(self):
        page = 'https://www.hzzx.gov.cn/cshz/content/2023-08/07/content_8595938.htm'
        self._check_venue_source_scope(
            page=page, city='hangzhou', wrong_city='chengdu',
            invalid_urls=(page + '?extra=1', page.replace('8595938', '8595939'),
                          'https://www.hzzx.gov.cn/',
                          page.replace('www.hzzx.gov.cn', 'other.hzzx.gov.cn')))

    def test_lianhua_guide_keeps_exact_url_and_shenzhen_venue_boundary(self):
        page = 'https://sz.bendibao.com/xiuxian/20261012/1014588.shtm'
        self._check_venue_source_scope(
            page=page, city='shenzhen', wrong_city='chengdu',
            invalid_urls=(page + '?extra=1', page.replace('1014588', '1014589'),
                          'https://sz.bendibao.com/',
                          page.replace('sz.bendibao.com', 'm.bendibao.com')))

    def test_each_xian_guide_keeps_exact_url_and_local_venue_boundary(self):
        guides = (
            ('https://www.chinahighlights.com/xian/attraction/big-wild-goose-pagoda.htm',
             'https://www.chinahighlights.com/xian/attraction/small-wild-goose-pagoda.htm'),
            ('https://www.chinahighlights.com/xian/terracotta-army/how-to-visit.htm',
             'https://www.chinahighlights.com/xian/terracotta-army/other.htm'),
        )
        for page, other_page in guides:
            self._check_venue_source_scope(
                page=page, city='xian', wrong_city='chengdu',
                invalid_urls=(page + '?extra=1', other_page, 'https://www.chinahighlights.com/',
                              page.replace('www.chinahighlights.com', 'other.chinahighlights.com')))


if __name__ == '__main__':
    unittest.main()
