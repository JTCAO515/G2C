"""Server copy of the place library, for Lio's entity linking and place facts (#1985, F-3).

`places_<city>.v1.json` beside this module is byte-identical to knowledge/places/<city>.v1.json; it is
written by `knowledge/places/validate.py --write` and checked in CI. This module only reads, shape-checks
and selects: no network, no inference. The field rules (official hosts, GCJ-02 box, unique names) are
checked once, on the source, before the byte-identical copy is written; here a copy that does not have
the expected shape fails closed.
"""
import json
from pathlib import Path
import re

from cj_strict_json import reject_duplicates
from .policy import FactFailure

VERSION = 'g2c-places.1'
CITIES = {'beijing': 'bj', 'shanghai': 'sh', 'guangzhou': 'gz', 'shenzhen': 'sz', 'chengdu': 'cd', 'chongqing': 'cq'}
CATEGORIES = frozenset({'attraction', 'food', 'shopping', 'hotel', 'hub'})
MAX_BYTES = 8 * 1024 * 1024


def path_for(city):
    return Path(__file__).with_name(f'places_{city}.v1.json')


def load_city(city, path=None):
    """The city document, or raise FactFailure. A city without a copy is `FactFailure('places_missing')`."""
    if city not in CITIES:
        raise FactFailure('invalid_places_city')
    path = path or path_for(city)
    try:
        raw = path.read_bytes()
    except OSError:
        raise FactFailure('places_missing') from None
    if len(raw) > MAX_BYTES:
        raise FactFailure('places_too_large')
    try:
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicates(FactFailure, 'duplicate_places_key'))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise FactFailure('invalid_places_json') from None
    if type(doc) is not dict or set(doc) != {'version', 'city', 'places'} or doc['version'] != VERSION \
            or doc['city'] != city or type(doc['places']) is not list:
        raise FactFailure('invalid_places_shape')
    pattern = re.compile(rf'pl_{CITIES[city]}_[a-z0-9]+(_[a-z0-9]+)*')
    seen = set()
    for place in doc['places']:
        if type(place) is not dict or type(place.get('id')) is not str or pattern.fullmatch(place['id']) is None \
                or place['id'] in seen or place.get('city') != city or place.get('category') not in CATEGORIES:
            raise FactFailure('invalid_places_entry')
        seen.add(place['id'])
    return doc


def by_id(doc, place_id):
    """One place by id, or None."""
    return next((place for place in doc['places'] if place['id'] == place_id), None)


def by_category(doc, category):
    """Places of a category, best rank first (unranked last, then by id)."""
    found = [place for place in doc['places'] if place['category'] == category]
    return sorted(found, key=lambda p: (p.get('rank') is None, p.get('rank') or 0, p['id']))


def match_name(doc, name):
    """The place whose name or alias equals `name` exactly (casefolded), or None. Names are unique per city."""
    key = name.casefold()
    for place in doc['places']:
        names = [place['name_zh'], place['name_en'], *place['aliases_zh'], *place['aliases_en']]
        if any(n.casefold() == key for n in names):
            return place
    return None
