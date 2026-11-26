"""Validate the business-pack knowledge catalogue (#1759): strict shape, approved hosts, dated review.

Each entry carries its official sources, the day they were read (`checked_on`, Beijing calendar) and
its review deadline (`expires_on`). The scene pack (`backend/cj_api/scene_packs/business.json`)
refers to these ids; nothing here reads a clock, so CI never turns red on a calendar day
(expiry alerts are `scripts/fact_expiry.py`'s job, #1757).

Usage (from the repository root):  python3 -B knowledge/business/validate.py
"""
from datetime import date
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
CATALOGUES = (ROOT / 'knowledge/business/guangzhou.v1.json',)
VERSION = 'g2c-business-knowledge.1'
CITIES = frozenset({'guangzhou'})
TOPICS = frozenset({'trade_fair_registration', 'venue_transport', 'visa_channel', 'business_payment'})
# S1 hosts only, each approved for the Guangzhou business entries; see knowledge/business/README.md.
HOSTS = frozenset({'www.cantonfair.org.cn', 'hk.cantonfair.org.cn', 'gaj.gz.gov.cn', 'www.gz.gov.cn', 'www.nia.gov.cn'})
KEYS = frozenset({'id', 'topic', 'title', 'text_zh', 'text_en', 'source_urls', 'checked_on', 'expires_on'})
MAX_REVIEW_DAYS = 90


class Invalid(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise Invalid(message)


def _text(value, where):
    _require(type(value) is str and value.strip() == value and value and '\n' not in value, f'{where}: one trimmed line')
    return value


def _day(value, where):
    _require(type(value) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is not None, f'{where}: YYYY-MM-DD')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise Invalid(f'{where}: not a calendar day') from None


def _pairs(object_pairs):
    keys = [key for key, _ in object_pairs]
    if len(keys) != len(set(keys)):
        raise Invalid('duplicate JSON key')
    return dict(object_pairs)


def load(path):
    """Return the validated catalogue; raise Invalid on the first problem."""
    doc = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_pairs)
    _require(type(doc) is dict and doc.keys() == {'version', 'city', 'entries'}, 'document keys')
    _require(doc['version'] == VERSION, 'version')
    _require(doc['city'] in CITIES, 'city')
    _require(type(doc['entries']) is list and doc['entries'], 'entries: non-empty list')
    seen = set()
    for index, entry in enumerate(doc['entries']):
        _require(type(entry) is dict and entry.keys() == KEYS, f'entries[{index}]: keys')
        where = _text(entry['id'], f'entries[{index}].id')
        _require(re.fullmatch(rf"business\.{doc['city']}\.[a-z0-9-]+", where) is not None, f'{where}: id prefix')
        _require(where not in seen, f'{where}: duplicate id')
        seen.add(where)
        _require(type(entry['topic']) is str and entry['topic'] in TOPICS, f'{where}: topic')
        title = entry['title']
        _require(type(title) is dict and title.keys() == {'zh', 'en'}, f'{where}: title zh/en')
        for key in ('zh', 'en'):
            _text(title[key], f'{where}.title.{key}')
        _text(entry['text_zh'], f'{where}.text_zh')
        _text(entry['text_en'], f'{where}.text_en')
        urls = entry['source_urls']
        _require(type(urls) is list and urls and len(set(urls)) == len(urls), f'{where}: unique non-empty sources')
        for url in urls:
            parts = urlsplit(_text(url, f'{where}.source_urls'))
            _require(parts.scheme == 'https' and parts.hostname in HOSTS and parts.port is None and parts.path not in ('', '/')
                     and not parts.username and not parts.password and not parts.fragment,
                     f'{where}: source {url} is not a page on an approved https host')
        checked = _day(entry['checked_on'], f'{where}.checked_on')
        expires = _day(entry['expires_on'], f'{where}.expires_on')
        _require(checked < expires and (expires - checked).days <= MAX_REVIEW_DAYS, f'{where}: review period 1..90 days')
    return doc


def main():
    for path in CATALOGUES:
        doc = load(path)
        print(f'PASS: {len(doc["entries"])} entries in {path.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Invalid as error:
        print(f'FAIL: {error}', file=sys.stderr)
        sys.exit(1)
