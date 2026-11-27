"""Read-side check of `rich.trip_receipt` (LIO-answer-rich.1, #1984/#1994).

The receipt is computed by the trip side (`cj_api.lio_trip_receipt.read`, T-1) at every read. This module
is the timeline's own last look before it goes on the wire: the same rules as the contract, with no
database and no clock. It returns the object to send (a copy with only the contract's fields) or None, and
never raises: a receipt that fails any rule is left out, and the row goes on without it.
"""
import re

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')
_UNDO_ID = re.compile(r'undo-[0-9a-f]{40}')
_HASH = re.compile(r'[0-9a-f]{64}')
_UNTIL = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}\+00:00')
_CONTENT = ('structured.1', 'structured.2', 'structured.3', 'structured.4')
_STATUS = ('saved', 'not_saved', 'unknown')
_REASONS = ('conflict', 'protected', 'too_large')
_UNDO_STATES = ('available', 'expired', 'superseded', 'undone', 'unavailable')
_RESTORE_TARGET = ('trip_id', 'expected_version', 'original_hash', 'content_version',
                   'restore_version', 'restore_hash', 'restore_content_version')
_CREATED_TARGET = ('trip_id', 'expected_version', 'original_hash', 'content_version')
MAX_VERSION = 9223372036854775806


def _int(value, low, high):
    return type(value) is int and low <= value <= high


def _id(value):
    return type(value) is str and _ID.fullmatch(value) is not None


def _city(value):
    return (type(value) is dict and set(value) == {'id', 'zh', 'en'} and type(value['id']) is str
            and re.fullmatch(r'[a-z]{3,20}', value['id']) is not None
            and all(type(value[k]) is str and 0 < len(value[k]) <= n and value[k] == value[k].strip() and '\n' not in value[k]
                    for k, n in (('zh', 12), ('en', 24))))


def _summary(value):
    if type(value) is not dict or set(value) != {'days', 'wishlist_added', 'legs_updated'} or type(value['days']) is not list:
        return False
    if len(value['days']) > 14 or not _int(value['wishlist_added'], 0, 99) or not _int(value['legs_updated'], 0, 99):
        return False
    numbers = []
    for day in value['days']:
        if (type(day) is not dict or set(day) != {'day', 'city', 'added', 'updated', 'removed'} or not _int(day['day'], 1, 60)
                or not (day['city'] is None or _city(day['city']))
                or not all(_int(day[k], 0, 99) for k in ('added', 'updated', 'removed'))
                or day['added'] + day['updated'] + day['removed'] == 0):
            return False
        numbers.append(day['day'])
    return numbers == sorted(set(numbers))


def _undo(undo, action_id, version):
    from hashlib import sha256
    if type(undo) is not dict or undo.get('state') not in _UNDO_STATES:
        return None
    state = undo['state']
    allowed = {'state', 'until'} | ({'kind', 'action_id', 'target'} if state == 'available' else set())
    if not set(undo) <= allowed or (state != 'unavailable' and 'until' not in undo):
        return None
    if 'until' in undo and (type(undo['until']) is not str or _UNTIL.fullmatch(undo['until']) is None):
        return None
    if state != 'available':
        return dict(undo)
    kind = undo.get('kind', 'restore')
    expected = 'undo-' + sha256(action_id.encode('utf-8')).hexdigest()[:40]
    target = undo.get('target')
    if (kind not in ('restore', 'withdraw_created') or undo.get('action_id') != expected or type(target) is not dict
            or 'until' not in undo or not _id(target.get('trip_id')) or target.get('expected_version') != version):
        return None
    if type(target.get('original_hash')) is not str or _HASH.fullmatch(target['original_hash']) is None \
            or target.get('content_version') not in _CONTENT:
        return None
    if kind == 'withdraw_created':
        if version != 1 or set(target) != set(_CREATED_TARGET):
            return None
    else:
        if (version < 2 or set(target) != set(_RESTORE_TARGET) or target['restore_version'] != version - 1
                or type(target['restore_hash']) is not str or _HASH.fullmatch(target['restore_hash']) is None
                or target['restore_content_version'] not in _CONTENT):
            return None
    return dict(undo)


def wire(receipt):
    """The receipt object to send (or None). `receipt` is the trip side's `TripReceipt` (`.wire`, `.first`) or the wire dict."""
    try:
        first = bool(getattr(receipt, 'first', False))
        value = getattr(receipt, 'wire', receipt)
        if type(value) is not dict or value.get('status') not in _STATUS or not _id(value.get('action_id')):
            return None
        status = value['status']
        if status == 'unknown':
            return dict(status='unknown', action_id=value['action_id']) if set(value) == {'status', 'action_id'} else None
        if status == 'not_saved':
            if not set(value) <= {'status', 'action_id', 'reason'} or ('reason' in value and value['reason'] not in _REASONS):
                return None
            return dict(value)
        if not set(value) <= {'status', 'action_id', 'trip_id', 'committed_version', 'first_autosave', 'summary', 'undo'}:
            return None
        if not _id(value.get('trip_id')) or not _int(value.get('committed_version'), 1, MAX_VERSION) or 'undo' not in value:
            return None
        if 'summary' in value and not _summary(value['summary']):
            return None
        undo = _undo(value['undo'], value['action_id'], value['committed_version'])
        if undo is None:
            return None
        out = dict(status='saved', action_id=value['action_id'], trip_id=value['trip_id'],
                   committed_version=value['committed_version'], undo=undo)
        if 'summary' in value:
            out['summary'] = value['summary']
        if value.get('first_autosave') is True or (first and 'first_autosave' not in value):
            out['first_autosave'] = True
        elif 'first_autosave' in value:
            return None      # only ever true
        return out
    except Exception:
        return None
