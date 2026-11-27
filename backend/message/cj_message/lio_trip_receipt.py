"""The `lio_trip_receipt:` effect of LIO-answer-rich.1 (#1984 "Stored", #1994 T-1): bytes and parsing only.

Written outside the trip lock on the Lio trip path, only while the write's repository has autosave on:
`{"action_id":…,"status":"unknown"}` before the commit, then `saved` or `not_saved` (with an optional
reason) once the result is known; the last valid one counts. Nothing here is trusted by a reader:
`saved` holds only when cj_trip_receipt has the row (see cj_api.lio_trip_receipt).
"""
import json
import re

EFFECT = 'lio_trip_receipt:'
MAX_EFFECT_BYTES = 8192
STATUSES = ('unknown', 'saved', 'not_saved')
REASONS = ('conflict', 'protected', 'too_large')
ACTION_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')


def effect(action_id, status, reason=None):
    if type(action_id) is not str or ACTION_ID.fullmatch(action_id) is None or status not in STATUSES:
        raise ValueError('exact receipt action and status required')
    if reason is not None and (status != 'not_saved' or reason not in REASONS):
        raise ValueError('a reason belongs to a known not_saved receipt')
    value = dict(action_id=action_id, status=status, **({'reason': reason} if reason is not None else {}))
    raw = EFFECT + json.dumps(value, separators=(',', ':'), sort_keys=True)
    if len(raw.encode('utf-8')) > MAX_EFFECT_BYTES:
        raise ValueError('receipt effect exceeds its byte bound')
    return raw


def parse(raw):
    """The effect's value, or None when it is not an exact receipt effect."""
    if type(raw) is not str or not raw.startswith(EFFECT) or len(raw.encode('utf-8')) > MAX_EFFECT_BYTES:
        return None
    try:
        value = json.loads(raw.removeprefix(EFFECT))
    except (ValueError, RecursionError):
        return None
    if type(value) is not dict or not {'action_id', 'status'} <= value.keys() <= {'action_id', 'status', 'reason'}:
        return None
    try:
        if effect(value['action_id'], value['status'], value.get('reason')) != raw:
            return None
    except ValueError:
        return None
    return value


def last(effects):
    """The last valid receipt effect of one RUN (a prefix that occurs more than once: the last counts)."""
    found = None
    for raw in effects:
        value = parse(raw)
        if value is not None:
            found = value
    return found
