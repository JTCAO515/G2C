"""Server copy of the App's attraction booking rules, for Lio's fact tool (#1826).

`attraction_booking_rules.v1.json` beside this module is byte-identical to
knowledge/attractions/booking-rules.v1.json and to what the App's table is generated from; all
copies are written by knowledge/attractions/generate_ios.py and checked in CI. This module only
reads, shape-checks and matches: no network, no inference. Matching follows the App
(`LioAttractionBookingRule.match`): an exact name or alias, so a café next to a museum never
inherits its rules. A rule past its review period is not returned, the way the App withholds it.
"""
from datetime import date, timedelta
import json
from pathlib import Path

from cj_strict_json import reject_duplicates
from .policy import FactFailure

RULES_PATH = Path(__file__).with_name('attraction_booking_rules.v1.json')
VERSION = 'attraction-booking-rules.1'
RULE_KEYS = frozenset({'id', 'name', 'city', 'aliases', 'requirement', 'window_days', 'release_time', 'passport',
                       'closed_weekdays', 'open_on_public_holidays', 'limits', 'notes', 'official_channel',
                       'partner_links', 'sources', 'checked_on'})
MAX_BYTES = 262144


def _constant(_):
    raise FactFailure('nonfinite_attraction_json')


def _day(value):
    if type(value) is not str or len(value) != 10:
        raise FactFailure('invalid_attraction_date')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise FactFailure('invalid_attraction_date') from None


def load_rules(path=RULES_PATH):
    """Return the parsed document; raise FactFailure if missing, malformed or reshaped."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise FactFailure('attraction_rules_unavailable') from None
    if not 0 < len(raw) <= MAX_BYTES:
        raise FactFailure('attraction_rules_unavailable')
    try:
        doc = json.loads(raw.decode('utf8'), parse_constant=_constant,
                         object_pairs_hook=reject_duplicates(FactFailure, 'duplicate_attraction_key'))
    except (ValueError, UnicodeError, RecursionError):
        raise FactFailure('invalid_attraction_json') from None
    if type(doc) is not dict or doc.keys() != {'version', 'review_days', 'rules'} or doc['version'] != VERSION:
        raise FactFailure('invalid_attraction_rules')
    if type(doc['review_days']) is not int or not 1 <= doc['review_days'] <= 90:
        raise FactFailure('invalid_attraction_rules')
    if type(doc['rules']) is not list or not doc['rules']:
        raise FactFailure('invalid_attraction_rules')
    for rule in doc['rules']:
        if type(rule) is not dict or rule.keys() != RULE_KEYS or not rule['sources']:
            raise FactFailure('invalid_attraction_rules')
        _day(rule['checked_on'])
    return doc


def normalized(text):
    """The App's normalisation: trimmed, lowercased, a leading "the " dropped, curly apostrophe made straight."""
    value = text.strip().lower()
    if value.startswith('the '):
        value = value[4:]
    return value.replace('’', "'")


def review_due(doc, rule):
    """First Beijing-calendar day on which the rule counts as possibly changed."""
    return _day(rule['checked_on']) + timedelta(days=doc['review_days'])


def match(doc, *names, today):
    """The rule whose name or alias equals one of `names`, tried in order; None if absent or past review.

    `today` is the trusted server's current Beijing calendar day.
    """
    if type(today) is not date:
        raise FactFailure('invalid_attraction_date')
    for key in (normalized(name) for name in names if type(name) is str):
        if not key:
            continue
        for rule in doc['rules']:
            if key in {normalized(n) for n in (rule['name']['zh'], rule['name']['en'], *rule['aliases'])}:
                return rule if today < review_due(doc, rule) else None
    return None
