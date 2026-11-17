"""Exact guide permissions do not grant a travel operator's entire website."""
from datetime import date
import json
from pathlib import Path
import unittest

from validate_v3 import validate_entry_v3


class ExternalGuideSourceScopeTests(unittest.TestCase):
    def test_one_xian_guide_keeps_exact_url_and_local_venue_boundary(self):
        root = Path(__file__).resolve().parent
        page = 'https://www.chinahighlights.com/xian/attraction/big-wild-goose-pagoda.htm'
        # Synthetic scope fixture; its conditions do not certify the guide's facts.
        record = json.loads((root / 'entries-v3/venues-beijing-chengdu-xian.json').read_text())[0]
        record = {**record, 'cities': ['xian'], 'source_urls': [page],
                  'subject': {'key': 'xian.big-wild-goose-pagoda', 'name_zh': '大雁塔',
                              'name_en': 'Giant Wild Goose Pagoda', 'wikidata_qid': None}}
        validate_entry_v3(record, as_of=date(2026, 11, 16))
        for url in (page + '?extra=1', page.replace('big-wild-goose', 'small-wild-goose'),
                    'https://www.chinahighlights.com/',
                    page.replace('www.chinahighlights.com', 'other.chinahighlights.com')):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_entry_v3({**record, 'source_urls': [url]}, as_of=date(2026, 11, 16))
        for change in ({'cities': ['chengdu']}, {'cities': ['xian', 'beijing']},
                       {'subject': None}, {'topic': 'payment'}, {'topic': 'visa_entry'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_entry_v3({**record, **change}, as_of=date(2026, 11, 16))


if __name__ == '__main__':
    unittest.main()
