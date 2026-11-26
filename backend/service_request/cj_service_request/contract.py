"""SERVICE-REQUEST@1 grammar and transitions (contracts/service-request/V1.md).

No storage, no I/O. W9-2 (#1769) builds the repository on these definitions.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

SERVICE_TYPE = 'gz_business_escort_zh_en'
MAX_BODY = 8192

STATES = ('draft', 'user_confirmed', 'submitted', 'accepted', 'quoted', 'arranged', 'in_progress',
          'completed', 'user_cancelled', 'unavailable', 'outcome_unknown')
TERMINAL = frozenset({'completed', 'user_cancelled', 'unavailable', 'outcome_unknown'})
TRANSITIONS = {
    'submitted': {'accepted', 'unavailable', 'user_cancelled'},
    'accepted': {'quoted', 'unavailable', 'user_cancelled'},
    'quoted': {'quoted', 'arranged', 'unavailable', 'user_cancelled'},
    'arranged': {'in_progress', 'unavailable', 'user_cancelled', 'outcome_unknown'},
    'in_progress': {'completed', 'outcome_unknown'},
    'outcome_unknown': {'completed', 'unavailable'},
}
EVIDENCE = {
    'user_confirmed': 'consent', 'submitted': 'receipt', 'accepted': 'staff_accept', 'quoted': 'quote',
    'arranged': 'arrangement', 'in_progress': 'arrival', 'completed': 'completion_summary',
    'user_cancelled': 'cancellation', 'unavailable': 'unavailable_reason', 'outcome_unknown': 'unknown_reason',
}
ACTORS = frozenset({'user', 'staff', 'system'})
SHAREABLE = ('customer_name', 'language', 'service_date', 'time_window', 'venue', 'meeting_purpose',
             'counterpart', 'contact_phone')

_ID = re.compile(r'[A-Za-z0-9_-]{1,128}')
_VERSION = re.compile(r'[A-Za-z0-9._-]{1,32}')
_DATE = re.compile(r'\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])')
_PHONE = re.compile(r'\+[1-9]\d{7,14}')
_KEYS = {'client_request_id', 'service_type', 'service_date', 'time_window', 'venue', 'customer_name',
         'contact_phone', 'meeting_purpose', 'counterpart', 'note', 'consents'}
_CONSENTS = {'location_sensitive', 'share_with_escort', 'cross_border', 'text_version'}


class InvalidInput(ValueError):
    pass


class InvalidTransition(ValueError):
    pass


def _no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise InvalidInput('duplicate key')
        out[k] = v
    return out


def _text(value, limit, *, nonblank=False):
    if not isinstance(value, str) or '\x00' in value or len(value) > limit:
        raise InvalidInput('text')
    if nonblank and not value.strip():
        raise InvalidInput('blank')
    return value


@dataclass(frozen=True)
class Submission:
    original: bytes
    fields: dict

    @property
    def client_request_id(self) -> str:
        return self.fields['client_request_id']

    def shared_with_escort(self) -> list[str]:
        f = self.fields
        out = ['customer_name', 'language', 'service_date', 'time_window', 'venue']
        if f['meeting_purpose']:
            out.append('meeting_purpose')
        if f['counterpart'] is not None:
            out.append('counterpart')
        out.append('contact_phone')
        return out


def parse_submission(original: bytes) -> Submission:
    if not isinstance(original, bytes) or len(original) > MAX_BODY:
        raise InvalidInput('size')
    try:
        value = json.loads(original.decode('utf-8'), object_pairs_hook=_no_dupes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidInput('json') from exc
    if not isinstance(value, dict) or set(value) != _KEYS:
        raise InvalidInput('keys')
    if not isinstance(value['client_request_id'], str) or not _ID.fullmatch(value['client_request_id']):
        raise InvalidInput('client_request_id')
    if value['service_type'] != SERVICE_TYPE:
        raise InvalidInput('service_type')
    if not isinstance(value['service_date'], str) or not _DATE.fullmatch(value['service_date']):
        raise InvalidInput('service_date')
    if value['time_window'] not in ('half_day_am', 'half_day_pm', 'full_day'):
        raise InvalidInput('time_window')
    _text(value['venue'], 200, nonblank=True)
    _text(value['customer_name'], 40, nonblank=True)
    if not isinstance(value['contact_phone'], str) or not _PHONE.fullmatch(value['contact_phone']):
        raise InvalidInput('contact_phone')
    _text(value['meeting_purpose'], 300)
    _text(value['note'], 500)
    cp = value['counterpart']
    if cp is not None:
        if not isinstance(cp, dict) or set(cp) != {'company', 'name'}:
            raise InvalidInput('counterpart')
        _text(cp['company'], 80)
        _text(cp['name'], 40)
        if not cp['company'].strip() and not cp['name'].strip():
            raise InvalidInput('counterpart empty')
    consents = value['consents']
    if not isinstance(consents, dict) or set(consents) != _CONSENTS:
        raise InvalidInput('consents')
    for key in ('location_sensitive', 'share_with_escort', 'cross_border'):
        if consents[key] is not True:
            raise InvalidInput('consent not given')
    if not isinstance(consents['text_version'], str) or not _VERSION.fullmatch(consents['text_version']):
        raise InvalidInput('text_version')
    return Submission(original, value)


def check_transition(current: str, target: str, actor: str, evidence_kind: str | None) -> None:
    if actor not in ACTORS:
        raise InvalidTransition('actor')
    if target not in TRANSITIONS.get(current, ()):
        raise InvalidTransition(f'{current} -> {target}')
    if target == 'user_cancelled' and actor == 'system':
        raise InvalidTransition('system cannot cancel for the user')
    if actor == 'user' and target != 'user_cancelled':
        raise InvalidTransition('user may only cancel')
    if evidence_kind != EVIDENCE[target]:
        raise InvalidInput('evidence_required')
