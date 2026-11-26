"""Server copy of the Guangzhou business knowledge entries, for Lio's fact tool (#1859).

`business_guangzhou.v1.json` beside this module is byte-identical to
knowledge/business/guangzhou.v1.json; it is written by `knowledge/business/validate.py --write`
and checked in CI. This module only reads, shape-checks and selects: no network, no inference.
An entry is returned only before its `expires_on` day (Beijing calendar), the way the visitor
entries are withheld once their review deadline arrives.
"""
from datetime import date
import json
from pathlib import Path

from cj_strict_json import reject_duplicates
from .policy import FactFailure

CATALOGUE_PATH = Path(__file__).with_name('business_guangzhou.v1.json')
VERSION = 'g2c-business-knowledge.1'
CITY = 'guangzhou'
TOPICS = frozenset({'trade_fair_registration', 'venue_transport', 'visa_channel', 'business_payment'})
ENTRY_KEYS = frozenset({'id', 'topic', 'title', 'text_zh', 'text_en', 'source_urls', 'checked_on', 'expires_on'})
MAX_BYTES = 65536


def _constant(_):
    raise FactFailure('nonfinite_business_json')


def _day(value):
    if type(value) is not str or len(value) != 10:
        raise FactFailure('invalid_business_date')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise FactFailure('invalid_business_date') from None


def _text(value):
    return type(value) is str and value != '' and value.strip() == value


def load_catalogue(path=CATALOGUE_PATH):
    """Return the parsed document; raise FactFailure if missing, malformed or reshaped."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise FactFailure('business_knowledge_unavailable') from None
    if not 0 < len(raw) <= MAX_BYTES:
        raise FactFailure('business_knowledge_unavailable')
    try:
        doc = json.loads(raw.decode('utf8'), parse_constant=_constant,
                         object_pairs_hook=reject_duplicates(FactFailure, 'duplicate_business_key'))
    except (ValueError, UnicodeError, RecursionError):
        raise FactFailure('invalid_business_json') from None
    if type(doc) is not dict or doc.keys() != {'version', 'city', 'entries'} or doc['version'] != VERSION or doc['city'] != CITY:
        raise FactFailure('invalid_business_knowledge')
    if type(doc['entries']) is not list or not doc['entries']:
        raise FactFailure('invalid_business_knowledge')
    seen = set()
    for entry in doc['entries']:
        if (type(entry) is not dict or entry.keys() != ENTRY_KEYS or not _text(entry['id']) or entry['id'] in seen
                or not entry['id'].startswith(f'business.{CITY}.') or type(entry['topic']) is not str or entry['topic'] not in TOPICS
                or type(entry['title']) is not dict or entry['title'].keys() != {'zh', 'en'}
                or not all(_text(entry['title'][key]) for key in ('zh', 'en'))
                or not _text(entry['text_zh']) or not _text(entry['text_en'])
                or type(entry['source_urls']) is not list or not entry['source_urls']
                or not all(type(url) is str and url.startswith('https://') for url in entry['source_urls'])):
            raise FactFailure('invalid_business_knowledge')
        seen.add(entry['id'])
        if not _day(entry['checked_on']) < _day(entry['expires_on']):
            raise FactFailure('invalid_business_knowledge')
    return doc


def _current(entry, today):
    if type(today) is not date:
        raise FactFailure('invalid_business_date')
    return today < _day(entry['expires_on'])


def by_topic(doc, topic, *, today):
    """Entries of `topic`, in file order, that are still before their review deadline.

    `today` is the trusted server's current Beijing calendar day. An unknown topic is an error,
    not an empty answer, so a misspelt tool argument cannot look like "nothing official".
    """
    if type(topic) is not str or topic not in TOPICS:
        raise FactFailure('invalid_business_topic')
    return [entry for entry in doc['entries'] if entry['topic'] == topic and _current(entry, today)]


def by_id(doc, entry_id, *, today):
    """The entry with this id (as a scene pack's `knowledge` refers to it); None if absent or past review."""
    for entry in doc['entries']:
        if entry['id'] == entry_id:
            return entry if _current(entry, today) else None
    if type(today) is not date:
        raise FactFailure('invalid_business_date')
    return None
