"""Reader for the unreviewed development place pack (#1985 follow-up). NEVER for production.

`knowledge/places/dev/places-dev-pack.v1.json` holds candidates nobody has reviewed. It is not part of
the `cj_fact` package or the server image; a developer or a test points at it explicitly. Two opt-ins are
required, so a stray variable cannot switch it on:

    CJ_PLACES_DEV_ENABLED=1
    CJ_PLACES_DEV_PACK=/path/to/places-dev-pack.v1.json

Without both, every function here raises FactFailure('places_dev_disabled'). The deployment environments
(HK) must never set either variable; `backend/tests/test_places_pipeline.py` fails if a deploy file does.
"""
import json
from pathlib import Path
import os

from cj_strict_json import reject_duplicates
from .policy import FactFailure

VERSION = 'g2c-places-dev.1'
MAX_BYTES = 8 * 1024 * 1024
ENABLE, PATH = 'CJ_PLACES_DEV_ENABLED', 'CJ_PLACES_DEV_PACK'


def load(environ=None):
    """The development pack document, or raise FactFailure (disabled, missing, malformed)."""
    environ = os.environ if environ is None else environ
    if environ.get(ENABLE) != '1' or not environ.get(PATH):
        raise FactFailure('places_dev_disabled')
    try:
        raw = Path(environ[PATH]).read_bytes()
    except OSError:
        raise FactFailure('places_dev_missing') from None
    if len(raw) > MAX_BYTES:
        raise FactFailure('places_dev_too_large')
    try:
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicates(FactFailure, 'duplicate_places_dev_key'))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise FactFailure('invalid_places_dev_json') from None
    if type(doc) is not dict or doc.get('version') != VERSION or type(doc.get('places')) is not list \
            or not all(type(p) is dict and type(p.get('id')) is str for p in doc['places']):
        raise FactFailure('invalid_places_dev_shape')
    if any(p.get('review', {}).get('status') != 'unreviewed' for p in doc['places']):
        raise FactFailure('invalid_places_dev_shape')   # a reviewed entry belongs in the real library, not here
    return doc


def by_id(doc, place_id):
    return next((p for p in doc['places'] if p['id'] == place_id), None)


def by_city(doc, city, category=None):
    return [p for p in doc['places'] if p['city'] == city and (category is None or p['category'] == category)]


def match_name(doc, name, city=None):
    """The entry whose name or alias equals `name` (casefolded), or None; unique per city, so `city` narrows ties."""
    key = name.casefold()
    for place in doc['places']:
        if city is not None and place['city'] != city:
            continue
        names = [place['name_zh'], place['name_en'], *(place.get('aliases_zh') or []), *(place.get('aliases_en') or [])]
        if any(n.casefold() == key for n in names):
            return place
    return None
