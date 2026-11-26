"""Server copy of the App's arrival (entry) rules, generated from knowledge/arrival (#1730).

`arrival_rules.v1.json` beside this module is byte-identical to the file the App bundles; both are
written by knowledge/arrival/sync_copies.py and checked in CI. This module only reads and shape-checks
it: no network, no date inference. Callers decide what to say once `review_due` has passed, the way
the App withholds conclusions and points to the official channel.
"""
from datetime import date, timedelta
import json
from pathlib import Path

from cj_strict_json import reject_duplicates
from .policy import FactFailure

RULES_PATH = Path(__file__).with_name('arrival_rules.v1.json')
DATA_VERSION = 1
KEYS = frozenset({'data_version', 'checked_at', 'review_every_days', 'official_fallback',
                  'policies', 'countries', 'arrival_card'})
MAX_BYTES = 262144


def _constant(_):
    raise FactFailure('nonfinite_arrival_json')


def _day(value):
    if type(value) is not str or len(value) != 10:
        raise FactFailure('invalid_arrival_date')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise FactFailure('invalid_arrival_date') from None


def load_rules(path=RULES_PATH):
    """Return the parsed rules; raise FactFailure if the file is missing, malformed or reshaped."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise FactFailure('arrival_rules_unavailable') from None
    if not 0 < len(raw) <= MAX_BYTES:
        raise FactFailure('arrival_rules_unavailable')
    try:
        value = json.loads(raw.decode('utf8'), parse_constant=_constant,
                           object_pairs_hook=reject_duplicates(FactFailure, 'duplicate_arrival_key'))
    except (ValueError, UnicodeError, RecursionError):
        raise FactFailure('invalid_arrival_json') from None
    if type(value) is not dict or value.keys() != KEYS or value['data_version'] != DATA_VERSION:
        raise FactFailure('invalid_arrival_rules')
    if type(value['review_every_days']) is not int or not 1 <= value['review_every_days'] <= 90:
        raise FactFailure('invalid_arrival_rules')
    if not all(type(value[key]) is list and value[key] for key in ('official_fallback', 'policies', 'countries')):
        raise FactFailure('invalid_arrival_rules')
    _day(value['checked_at'])
    return value


def review_due(rules):
    """First day (Beijing calendar) on which the whole file counts as possibly out of date."""
    return _day(rules['checked_at']) + timedelta(days=rules['review_every_days'])
