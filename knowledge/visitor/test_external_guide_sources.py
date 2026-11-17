"""Exact guide permissions do not grant a travel operator's entire website."""
from datetime import date
import json
from pathlib import Path
import unittest

from validate_v3 import validate_entry_v3


class ExternalGuideSourceScopeTests(unittest.TestCase):
    def test_lianhua_guide_keeps_exact_url_and_shenzhen_venue_boundary(self):
        root = Path(__file__).resolve().parent
        record = json.loads((root / 'entries-v3/venues-beijing-chengdu-xian.json').read_text())[0]
        page = 'https://sz.bendibao.com/xiuxian/20261012/1014588.shtm'
        record = {**record, 'cities': ['shenzhen'], 'source_urls': [page],
                  'subject': {'key': 'shenzhen.example-venue', 'name_zh': '合成场馆',
                              'name_en': 'Synthetic venue', 'wikidata_qid': None}}
        validate_entry_v3(record, as_of=date(2026, 11, 16))
        for url in (page + '?extra=1', page.replace('1014588', '1014589'),
                    'https://sz.bendibao.com/',
                    page.replace('sz.bendibao.com', 'm.bendibao.com')):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_entry_v3({**record, 'source_urls': [url]}, as_of=date(2026, 11, 16))
        for change in ({'cities': ['chengdu']}, {'cities': ['shenzhen', 'beijing']},
                       {'subject': None}, {'topic': 'payment'}, {'topic': 'visa_entry'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_entry_v3({**record, **change}, as_of=date(2026, 11, 16))

    def test_each_xian_guide_keeps_exact_url_and_local_venue_boundary(self):
        root = Path(__file__).resolve().parent
        # Synthetic scope fixture; its conditions do not certify the guide's facts.
        base = json.loads((root / 'entries-v3/venues-beijing-chengdu-xian.json').read_text())[0]
        guides = (
            ('https://www.chinahighlights.com/xian/attraction/big-wild-goose-pagoda.htm',
             'https://www.chinahighlights.com/xian/attraction/small-wild-goose-pagoda.htm'),
            ('https://www.chinahighlights.com/xian/terracotta-army/how-to-visit.htm',
             'https://www.chinahighlights.com/xian/terracotta-army/other.htm'),
        )
        for page, other_page in guides:
            record = {**base, 'cities': ['xian'], 'source_urls': [page],
                      'subject': {'key': 'xian.example-venue', 'name_zh': '合成场馆',
                                  'name_en': 'Synthetic venue', 'wikidata_qid': None}}
            with self.subTest(allowed=page):
                validate_entry_v3(record, as_of=date(2026, 11, 16))
            for url in (page + '?extra=1', other_page, 'https://www.chinahighlights.com/',
                        page.replace('www.chinahighlights.com', 'other.chinahighlights.com')):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    validate_entry_v3({**record, 'source_urls': [url]}, as_of=date(2026, 11, 16))
            for change in ({'cities': ['chengdu']}, {'cities': ['xian', 'beijing']},
                           {'subject': None}, {'topic': 'payment'}, {'topic': 'visa_entry'}):
                with self.subTest(page=page, change=change), self.assertRaises(ValueError):
                    validate_entry_v3({**record, **change}, as_of=date(2026, 11, 16))


if __name__ == '__main__':
    unittest.main()
