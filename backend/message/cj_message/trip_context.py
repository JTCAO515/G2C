"""Explicit formal Trip selection. No latest-Trip lookup or Trip write authority."""
from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo
import json
from cj_agent.draft import trip_scope_for
from cj_trip.domain import identifier, packed
from cj_trip.structured import validate_document as validate_v1
from cj_trip.structured_v2 import validate_document as validate_v2
from .domain import InvalidInput, Unavailable
from .travel_reference import ContextConflict

ABI = 'MESSAGE-TRIP-CONSUMER@1'
PROFILE = 'message-trip.1'


@dataclass(frozen=True)
class TripSelection:
    id: str
    expected_version: int
    day: tuple[str, str] | None
    item_id: str | None

    @classmethod
    def parse(cls, value):
        try:
            if type(value) is not dict or set(value) != {'id', 'expected_version', 'day', 'item_id'}:
                raise ValueError('explicit Trip selection fields required')
            identifier(value['id'])
            version = value['expected_version']
            if type(version) is not int or not 1 <= version <= 9223372036854775807:
                raise ValueError('explicit Trip version required')
            day = value['day']
            if day is not None:
                if type(day) is not dict or set(day) != {'date', 'timezone'}:
                    raise ValueError('explicit local date and timezone required')
                if type(day['date']) is not str or date.fromisoformat(day['date']).isoformat() != day['date']:
                    raise ValueError('ISO date required')
                zone=day['timezone']
                if type(zone) is not str or not zone.strip() or len(zone)>128 or zone in ('localtime','Factory'):
                    raise ValueError('explicit IANA timezone required')
                ZoneInfo(zone)
                day = (day['date'], day['timezone'])
            item = value['item_id']
            if item is not None:
                identifier(item)
            return cls(value['id'], version, day, item)
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise InvalidInput('invalid explicit Trip selection') from exc

    def public_value(self):
        return dict(id=self.id, expected_version=self.expected_version,
                    day=None if self.day is None else dict(date=self.day[0], timezone=self.day[1]),
                    item_id=self.item_id)


def on_day(item, day):
    """Declared local endpoints only; never infer unknown dates/zones from prose."""
    target, zone = day
    start, end = item['schedule']['start'], item['schedule']['end']
    def known(event, key):
        observation = event[key]
        return observation['value'] if observation['state'] == 'known' else None
    sd, ed = known(start, 'date'), known(end, 'date')
    sz, ez = known(start, 'timezone'), known(end, 'timezone')
    if sd is not None and ed is not None and sz == ez == zone and sd <= ed:
        # Midnight end is exclusive; an unknown end time cannot prove exclusion.
        last = (date.fromisoformat(ed) - timedelta(days=1)).isoformat() if known(end, 'time') in ('00:00','00:00:00') and sd < ed else ed
        return sd <= target <= last
    return ((sd == target and sz == zone)
            or (ed == target and ez == zone and known(end, 'time') not in ('00:00','00:00:00')))


def decode_source(raw, selection):
    """Persisted C-owned structured.1 boundary; bytes are canonical and immutable."""
    try:
        document = json.loads(raw.decode('utf-8'))
        version=document['content_version']
        if version=='structured.1':validate_v1(document)
        elif version=='structured.2':validate_v2(document)
        else:raise ValueError('supported structured Trip version required')
        if packed(document) != raw or len(raw) > 1048576:
            raise ValueError('canonical bounded structured.1 required')
        items = document['items']
        if selection.item_id is not None:
            items = [item for item in items if item['id'] == selection.item_id]
            if not items:
                raise ValueError('item does not belong to Trip')
        if selection.day is not None and not any(on_day(item, selection.day) for item in items):
            raise ValueError('date/item does not belong to explicit Trip day')
        return document
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise Unavailable('formal Trip content/selection unavailable') from exc


def current_source(cursor, scope, selection):
    """M scope precedes Trip scope. C writers hold the same Trip row exclusively."""
    trip_scope = trip_scope_for(scope)
    cursor.execute('SELECT scope FROM cj_trip_scope WHERE scope=%s FOR SHARE', (trip_scope,))
    if cursor.fetchone() is None:
        raise Unavailable('formal Trip owner unavailable')
    cursor.execute('SELECT version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s',
                   (trip_scope, selection.id))
    row = cursor.fetchone()
    if row is None:
        raise Unavailable('formal Trip unavailable')
    if row[0] != selection.expected_version:
        raise ContextConflict('formal Trip version changed')
    raw = bytes(row[1])
    decode_source(raw, selection)
    return raw
