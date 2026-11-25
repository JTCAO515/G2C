"""Fixed-tool VariFlight MCP relay for public flight lookups."""

from datetime import date
import logging
import re
from time import monotonic
from typing import Annotated, Literal

import httpx
from pydantic import Field, field_validator, model_validator

from .plugin_tools import PluginError, register_plugin
from .taxi_tools import WireModel
from .travel_provider import (ShortCache, SupplierPaymentRequired, check_status, checked_key,
                              provider_client, read_reply, supplier_json)


ROUTE = '/v1/tools/flights'
VERSION = 'FLIGHTS.1'
DAILY_LIMIT = 50
ENDPOINT = 'https://c-gw.variflight.com/chat_message/mcp/api'
LOGGER = logging.getLogger(__name__)
READ_ONLY_TOOLS = frozenset({'getFlightList', 'getFlightStatus'})
MAX_FLIGHTS = 100
PROTOCOLS = ('2025-11-25', '2025-06-18', '2025-03-26')
SESSION = re.compile(r'[\x21-\x7e]{1,256}')
NUMBER = r'[A-Z0-9]{2,3}[0-9]{1,4}[A-Z]?'
AIRPORT = r'[A-Z]{3}'
DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')


class FlightInput(WireModel):
    version: Literal['FLIGHTS.1']
    date: str
    flight_number: Annotated[str, Field(pattern='^' + NUMBER + '$')] | None = None
    departure: Annotated[str, Field(pattern='^' + AIRPORT + '$')] | None = None
    arrival: Annotated[str, Field(pattern='^' + AIRPORT + '$')] | None = None

    @field_validator('date')
    @classmethod
    def valid_day(cls, value):
        if not DATE.fullmatch(value):
            raise ValueError('ISO calendar date required')
        return date.fromisoformat(value).isoformat()

    @model_validator(mode='after')
    def one_lookup(self):
        if self.flight_number is not None and self.departure is None and self.arrival is None:
            return self
        if self.flight_number is None and self.departure and self.arrival and self.departure != self.arrival:
            return self
        raise ValueError('choose a flight number or two different airports')

    def tool_call(self):
        if self.flight_number:
            return 'getFlightStatus', dict(fnum=self.flight_number, date=self.date)
        return 'getFlightList', dict(dep=self.departure, arr=self.arrival, date=self.date)


def _events(response, deadline):
    pending, data = b'', []
    for piece in read_reply(response, deadline):
        lines = (pending + piece).split(b'\n')
        pending = lines.pop()
        for line in lines:
            line = line.removesuffix(b'\r')
            if not line:
                if data:
                    yield b'\n'.join(data)
                    data.clear()
                continue
            if line.startswith(b'data:'):
                data.append(line[5:].removeprefix(b' '))


def _rpc_response(response, identifier, deadline, key):
    media = response.headers.get('content-type', '').partition(';')[0].strip().lower()
    if media == 'application/json':
        replies = (b''.join(read_reply(response, deadline)),)
    elif media == 'text/event-stream':
        replies = _events(response, deadline)
    else:
        raise ValueError('unknown MCP response format')
    for raw in replies:
        packet = supplier_json(raw, key)
        if type(packet) is not dict or packet.get('jsonrpc') != '2.0':
            raise ValueError('invalid RPC response')
        if 'id' not in packet and type(packet.get('method')) is str and media == 'text/event-stream':
            continue
        if type(packet.get('id')) is not int or packet['id'] != identifier:
            raise ValueError('unbound RPC response')
        if ('result' in packet) == ('error' in packet):
            raise ValueError('invalid RPC result')
        if 'error' in packet:
            error = packet['error']
            # Content-free: the RPC error code only, never the supplier message.
            code = error.get('code') if type(error) is dict else None
            LOGGER.warning('variflight_rpc_error code=%s', code if type(code) is int else 'unknown')
            if type(error) is dict and error.get('code') == 402:
                raise SupplierPaymentRequired()
            raise PluginError(502, 'supplier_unavailable')
        if type(packet['result']) is not dict:
            raise ValueError('invalid RPC result')
        return packet['result']
    raise ValueError('missing RPC response')


def _records(payload):
    if type(payload) is list:
        return payload
    if type(payload) is not dict:
        raise ValueError('invalid flight results')
    # getFlightList answers structuredContent {"kind": "collection", "items": [...]} (HK, #1521).
    for field in ('flights', 'flightList', 'data', 'items'):
        if field in payload:
            rows = payload[field]
            if type(rows) is dict and 'flights' in rows:
                rows = rows['flights']
            if type(rows) is not list:
                raise ValueError('invalid flight collection')
            return rows
    if any(field in payload for field in ('flightNo', 'flightNumber', 'flightnum', 'fnum')):
        return [payload]
    raise ValueError('flight collection missing')


def _public_text(value, limit=120):
    if (type(value) is not str or not value.strip() or len(value) > limit
            or any(ord(c) < 32 for c in value)):
        raise ValueError('invalid flight value')
    value.encode('utf8')
    return value


def _take(row, aliases):
    return next((row[name] for name in aliases if row.get(name) not in (None, '')), None)


def _flight(row):
    identifier = _take(row, ('flightNo', 'flightNumber', 'flightnum', 'fnum'))
    if not re.fullmatch(NUMBER, _public_text(identifier)):
        raise ValueError('invalid flight identifier')
    result = {'flight_number': identifier}
    for field, aliases in (
        ('departure', ('departure', 'dep', 'flightDepcode', 'depAirportCode')),
        ('arrival', ('arrival', 'arr', 'flightArrcode', 'arrAirportCode')),
    ):
        if (value := _take(row, aliases)) is not None:
            if not re.fullmatch(AIRPORT, _public_text(value)):
                raise ValueError('invalid airport code')
            result[field] = value
    if type(row.get('isShare')) is int and row['isShare'] in (0, 1):
        result['codeshare'] = row['isShare'] == 1
    for field, aliases in (
        ('status', ('status', 'flightStatus')),
        ('planned_departure', ('plannedDeparture', 'scheduledDeparture', 'flightDeptimePlan', 'departurePlanTime')),
        ('planned_arrival', ('plannedArrival', 'scheduledArrival', 'flightArrtimePlan', 'arrivalPlanTime')),
        ('actual_departure', ('actualDeparture', 'flightDeptimeAct', 'departureActualTime')),
        ('actual_arrival', ('actualArrival', 'flightArrtimeAct', 'arrivalActualTime')),
        ('departure_terminal', ('departureTerminal', 'flightDepTerminal')),
        ('arrival_terminal', ('arrivalTerminal', 'flightArrTerminal')),
        ('gate', ('gate', 'boardingGate')),
        ('check_in_counter', ('checkInCounter', 'checkinCounter', 'checkinTable')),
        ('baggage_carousel', ('baggageCarousel', 'baggageClaim', 'baggageTurntable')),
        ('airline_name_zh', ('airlineNameZh', 'airlineCnName')),
        ('airline_name_en', ('airlineNameEn', 'airlineName')),
        ('departure_airport_name_zh', ('departureAirportNameZh', 'depAirport')),
        ('departure_airport_name_en', ('departureAirportNameEn',)),
        ('arrival_airport_name_zh', ('arrivalAirportNameZh', 'arrAirport')),
        ('arrival_airport_name_en', ('arrivalAirportNameEn',)),
    ):
        if (value := _take(row, aliases)) is not None:
            result[field] = _public_text(value)
    return result


def _project(result, day, key):
    if result.get('isError') is True:
        LOGGER.warning('variflight_tool_error')
        raise PluginError(502, 'supplier_unavailable')
    if 'structuredContent' in result:
        payload = result['structuredContent']
    else:
        block, = result['content']
        if block.get('type') != 'text':
            raise ValueError('unsupported flight content')
        payload = supplier_json(block['text'], key)
    rows = _records(payload)
    # A busy route (e.g. Shanghai -> Beijing, both airports) lists about 75 flights; keep them all within a bound.
    # One malformed row is skipped, not the whole answer; a reply with rows but none usable is still a failure.
    items, skipped = [], 0
    for row in rows[:MAX_FLIGHTS]:
        try:
            items.append(_flight(row))
        except (AttributeError, KeyError, TypeError, ValueError):
            skipped += 1
    if skipped:
        LOGGER.warning('variflight_rows_skipped count=%d', skipped)
        if not items:
            raise ValueError('no usable flight rows')
    return dict(version=VERSION, source='VariFlight', date=day, items=items, more=len(rows) > MAX_FLIGHTS)


class VariFlight:
    def __init__(self, key, *, client=provider_client):
        checked_key(key)
        self.key, self.client = key, client
        self.cache = ShortCache(60)
        self.session = None

    def query(self, request, reserve):
        tool, arguments = request.tool_call()
        # VariFlight also offers ordering, payment and follow tools; only these read-only lookups may be called.
        if tool not in READ_ONLY_TOOLS:
            LOGGER.error('variflight_tool_refused')
            raise PluginError(503, 'unavailable')
        return self.cache.load((tool, tuple(arguments.items())), lambda: self._fetch(tool, arguments, reserve))

    def _post(self, client, headers, payload, reserve, deadline):
        if monotonic() >= deadline:
            raise PluginError(504, 'supplier_timeout')
        reserve('variflight:dispatch', None)
        with client.stream('POST', ENDPOINT, json=payload, headers=headers) as response:
            if 'id' not in payload and response.status_code == 202:
                return None, None
            if response.status_code == 404:
                self.session = None
            if response.status_code != 200:
                LOGGER.warning('variflight_http_status status=%d', response.status_code)
            check_status(response.status_code)
            return (_rpc_response(response, payload['id'], deadline, self.key),
                    response.headers.get('Mcp-Session-Id'))

    def _fetch(self, tool, arguments, reserve):
        headers = {'Authorization': 'Bearer ' + self.key, 'Accept': 'application/json, text/event-stream'}
        deadline = monotonic() + 23
        try:
            with self.client() as client:
                if self.session is None:
                    hello, session = self._post(client, headers, dict(jsonrpc='2.0', id=1, method='initialize',
                        params=dict(protocolVersion=PROTOCOLS[0], capabilities={},
                                    clientInfo=dict(name='Go2China', version='1'))), reserve, deadline)
                    version = hello['protocolVersion']
                    if version not in PROTOCOLS or session is not None and (
                            not SESSION.fullmatch(session) or self.key in session):
                        raise ValueError('invalid negotiated MCP session')
                    headers['MCP-Protocol-Version'] = version
                    if session:
                        headers['Mcp-Session-Id'] = session
                    self._post(client, headers, dict(jsonrpc='2.0', method='notifications/initialized'),
                               reserve, deadline)
                    self.session = (version, session)
                else:
                    version, session = self.session
                    headers['MCP-Protocol-Version'] = version
                    if session:
                        headers['Mcp-Session-Id'] = session
                packet, _ = self._post(client, headers, dict(jsonrpc='2.0', id=2, method='tools/call',
                    params=dict(name=tool, arguments=arguments)), reserve, deadline)
            return _project(packet, arguments['date'], self.key)
        except httpx.TimeoutException:
            raise PluginError(504, 'supplier_timeout') from None
        except (httpx.HTTPError, AttributeError, KeyError, TypeError, UnicodeError, ValueError, RecursionError) as error:
            LOGGER.warning('variflight_reply_unusable error=%s', type(error).__name__)
            raise PluginError(502, 'supplier_unavailable') from None


def register_flights(app, *, service=None, checker=None, internal=frozenset(), calls=None):
    register_plugin(app, ROUTE, FlightInput, service.query if service else None, enabled=service is not None,
                    checker=checker, internal=internal, calls=calls, limit=DAILY_LIMIT, count_provider_calls=True)
