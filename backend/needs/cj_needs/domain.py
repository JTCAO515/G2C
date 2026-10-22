"""NEEDS internal candidate: explicit manual input, never model extraction or Trip."""
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VERSION = 'CJ-NEEDS-INTERNAL@0.1.0-candidate.1'


class InvalidInput(ValueError): pass
class Conflict(Exception): pass
class Denied(Exception): pass
class CommitUnknown(Exception): pass


def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}', value):
        raise InvalidInput('invalid identifier')
    return value


def text(value):
    if type(value) is not str or not value.strip() or len(value) > 4096:
        raise InvalidInput('nonempty bounded text required')
    try: value.encode('utf-8')
    except UnicodeError: raise InvalidInput('valid Unicode scalar text required') from None


def exact(obj, keys):
    if type(obj) is not dict or set(obj) != set(keys):
        raise InvalidInput('unexpected or missing fields')


def choice(*values):
    def check(value):
        if type(value) is not str or value not in values: raise InvalidInput('invalid choice')
    return check


def positive(value):
    if type(value) is not int or not 1 <= value <= 100000: raise InvalidInput('invalid party size')


def boolean(value):
    if type(value) is not bool: raise InvalidInput('boolean required')


def money(value):
    # Decimal text is retained exactly; zero is accepted only when explicitly supplied.
    if type(value) is not str or not re.fullmatch(r'(0|[1-9][0-9]{0,14})(\.[0-9]{1,6})?', value):
        raise InvalidInput('nonnegative decimal text required')
    if not Decimal(value).is_finite(): raise InvalidInput('finite amount required')


def currency(value):
    if type(value) is not str or not re.fullmatch('[A-Z]{3}', value):
        raise InvalidInput('explicit three-letter currency code required')


def local_date(value):
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise InvalidInput('local date required')
    try: date.fromisoformat(value)
    except ValueError: raise InvalidInput('invalid local date') from None


def local_time(value):
    if type(value) is not str or not re.fullmatch(r'\d{2}:\d{2}(:\d{2})?', value):
        raise InvalidInput('local wall time without offset required')
    parts = [int(part) for part in value.split(':')]
    if parts[0] > 23 or parts[1] > 59 or (len(parts) == 3 and parts[2] > 59):
        raise InvalidInput('invalid local wall time')
    try: time.fromisoformat(value)
    except ValueError: raise InvalidInput('invalid local time') from None


def zone(value):
    if type(value) is not str or value.startswith(('/', '.')): raise InvalidInput('IANA zone required')
    try: ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError): raise InvalidInput('unknown IANA zone') from None


def observation(value, validator):
    if type(value) is not dict: raise InvalidInput('observation required')
    state = value.get('state')
    if state in ('missing', 'unknown'):
        exact(value, ('state',))
    elif state == 'uncertain':
        exact(value, ('state', 'note'))
        text(value['note'])
    elif state == 'known':
        exact(value, ('state', 'value'))
        validator(value['value'])
    else: raise InvalidInput('invalid observation state')


def event(value):
    exact(value, ('date', 'time', 'timezone', 'place'))
    for name, check in (('date', local_date), ('time', local_time), ('timezone', zone), ('place', text)):
        observation(value[name], check)


def strings(value):
    if type(value) is not list or len(value) > 32 or not value: raise InvalidInput('nonempty bounded list required')
    for v in value: text(v)
    if len(set(value)) != len(value): raise InvalidInput('duplicate value')


def subjects(value):
    strings(value)
    for v in value:
        if v not in ('self', 'party'):
            if not v.startswith('companion:'): raise InvalidInput('local companion reference required')
            identifier(v[len('companion:'):])


def companions(value):
    if type(value) is not dict or len(value) > 100: raise InvalidInput('bounded companion map required')
    for key, label in value.items(): identifier(key); text(label)


def items(value):
    if type(value) is not list or len(value) > 100: raise InvalidInput('bounded fixed item list required')
    seen = set()
    for item in value:
        exact(item, ('item_id', 'kind', 'description', 'applies_to', 'locked', 'start', 'end', 'booking_status'))
        identifier(item['item_id'])
        if item['item_id'] in seen: raise InvalidInput('duplicate item')
        seen.add(item['item_id'])
        choice('hotel', 'transport', 'appointment', 'intent')(item['kind'])
        text(item['description']); subjects(item['applies_to'])
        observation(item['locked'], boolean)
        event(item['start']); event(item['end'])
        observation(item['booking_status'], choice('booked', 'intended', 'cancelled'))


def conditions(value):
    if type(value) is not list or len(value) > 100: raise InvalidInput('bounded current conditions required')
    seen = set()
    for item in value:
        exact(item, ('condition_id', 'applies_to', 'description'))
        identifier(item['condition_id']); subjects(item['applies_to']); text(item['description'])
        if item['condition_id'] in seen: raise InvalidInput('duplicate condition')
        seen.add(item['condition_id'])


OBSERVATIONS = {
    'party_size': positive, 'destination_timezone': zone, 'overseas_timezone': zone,
    'budget_currency': currency, 'budget_total': money, 'budget_per_person': money,
    'budget_paid': money, 'budget_basis': choice('total', 'per_person'),
    'budget_includes': strings, 'pace': text,
}
EVENTS = {'overseas_departure', 'arrival', 'departure'}
COLLECTIONS = {'companions': companions, 'fixed_items': items, 'temporary_conditions': conditions}


def validate_fields(fields, *, complete=False):
    if type(fields) is not dict or (not fields and not complete): raise InvalidInput('changes required')
    if not set(fields) <= set(OBSERVATIONS) | EVENTS | set(COLLECTIONS):
        raise InvalidInput('unsupported field or source')
    for key, value in fields.items():
        if key in OBSERVATIONS: observation(value, OBSERVATIONS[key])
        elif key in EVENTS: event(value)
        else: COLLECTIONS[key](value)
    if complete:
        known = fields.get('companions', {})
        for item in fields.get('fixed_items', []) + fields.get('temporary_conditions', []):
            for subject in item['applies_to']:
                if subject.startswith('companion:') and subject[10:] not in known:
                    raise InvalidInput('companion unavailable in this needs record')


def decode(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 131072: raise InvalidInput('bounded original UTF8 bytes required')
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out: raise InvalidInput('duplicate field')
            out[key] = value
        return out
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(InvalidInput('nonfinite number')))
    except (ValueError, UnicodeError, RecursionError): raise InvalidInput('invalid JSON') from None


@dataclass(frozen=True, repr=False)
class Command:
    raw: bytes

    def __post_init__(self):
        obj = decode(self.raw)
        exact(obj, ('action_id', 'needs_id', 'expected_version', 'source', 'changes'))
        identifier(obj['action_id']); identifier(obj['needs_id'])
        if type(obj['expected_version']) is not int or not 0 <= obj['expected_version'] < 2**63 - 1:
            raise InvalidInput('expected version required')
        exact(obj['source'], ('kind', 'text'))
        choice('manual')(obj['source']['kind']); text(obj['source']['text'])
        validate_fields(obj['changes'])

    @property
    def data(self): return decode(self.raw)
    @property
    def action_id(self): return self.data['action_id']


@dataclass(frozen=True)
class Receipt:
    action_id: str
    needs_id: str
    version: int
    operation: str = 'manual_patch'


@dataclass(frozen=True, repr=False)
class Snapshot:
    needs_id: str
    version: int
    content: bytes
    source_kind: str = 'user_provided'

    @property
    def fields(self): return decode(self.content)


@dataclass(frozen=True, repr=False)
class Revision:
    needs_id: str
    version: int
    action_id: str
    original_input: bytes
    content: bytes
    source_kind: str = 'user_provided'
