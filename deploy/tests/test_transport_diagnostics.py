"""Content-free diagnostics for the HK intercity smoke (#1521): why flights failed, why seats were empty.

Logs carry only categories, status or RPC codes and supplier seat-class codes; never the key, a supplier
message, a station name or anything a traveller sent.
"""
from contextlib import contextmanager
import json
import logging

import httpx
import pytest

from cj_api.lio_transport import rail_items
from cj_api.plugin_tools import PluginError
from cj_api.variflight_tools import FlightInput, VariFlight


KEY = 'offline-provider-key'
REQUEST = FlightInput(version='FLIGHTS.1', date='2026-12-02', departure='SHA', arrival='PEK')


def fixture_transport(handler):
    @contextmanager
    def client():
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as connection:
            yield connection
    return client


def mcp(tool_reply):
    def reply(http):
        call = json.loads(http.content)
        if call['method'] == 'initialize':
            return httpx.Response(200, json=dict(jsonrpc='2.0', id=1, result={'protocolVersion': '2025-06-18'}))
        if call['method'] == 'notifications/initialized':
            return httpx.Response(202)
        return tool_reply(call)
    return reply


def query(tool_reply):
    VariFlight(KEY, client=fixture_transport(mcp(tool_reply))).query(REQUEST, lambda *_: None)


@pytest.mark.parametrize(('tool_reply', 'expected'), [
    (lambda call: httpx.Response(200, json=dict(jsonrpc='2.0', id=2, error=dict(
        code=-32602, message='Unknown tool getFlightList for ' + KEY))), 'variflight_rpc_error code=-32602'),
    (lambda call: httpx.Response(200, json=dict(jsonrpc='2.0', id=2, result=dict(
        isError=True, content=[dict(type='text', text='tool failed near Shanghai')]))), 'variflight_tool_error'),
    (lambda call: httpx.Response(500, text='upstream exploded'), 'variflight_http_status status=500'),
    (lambda call: httpx.Response(200, json=dict(jsonrpc='2.0', id=2, result=dict(
        structuredContent={'unexpected': 'shape'}))), 'variflight_reply_unusable error=ValueError'),
    (lambda call: httpx.Response(200, json=dict(jsonrpc='2.0', id=2, result=dict(
        content=[dict(type='text', text='航班列表：MU5101 07:30')]))), 'variflight_reply_unusable error=JSONDecodeError'),
])
def test_each_flight_failure_logs_only_its_category(caplog, tool_reply, expected):
    caplog.set_level(logging.INFO)
    with pytest.raises(PluginError) as failure:
        query(tool_reply)
    assert (failure.value.status, failure.value.code) == (502, 'supplier_unavailable')
    assert expected in caplog.text
    for secret_or_content in (KEY, 'Unknown tool', 'Shanghai', 'exploded', 'unexpected', 'MU5101', '航班'):
        assert secret_or_content not in caplog.text


def railway(spaces, trip='G28', depart='0800'):
    return dict(trip=trip, departure_stop=dict(name='上海虹桥', time=depart),
                arrival_stop=dict(name='北京南', time='1228'), **({} if spaces is None else dict(spaces=spaces)))


def reply(*rails):
    return dict(status='1', infocode='10000', route=dict(
        transits=[dict(segments=[dict(walking={}, railway=rail)]) for rail in rails]))


def test_seat_diagnostics_tell_missing_spaces_from_unknown_codes(caplog):
    caplog.set_level(logging.INFO)
    items = rail_items(reply(railway(None, 'T110', '0700'), railway([dict(code='YZ', cost='553.0'), dict(code='ZE<script>', cost='1'),
                                                     dict(code='O', cost='626.0')])))
    assert [item['number'] for item in items] == ['T110', 'G28']
    assert items[0]['seats'] == [] and [seat['class_zh'] for seat in items[1]['seats']] == ['二等座']
    assert 'transport_rail_segments_without_seats count=1' in caplog.text
    assert 'transport_rail_seat_codes_dropped codes=YZ,?' in caplog.text
    assert '<script>' not in caplog.text and '553' not in caplog.text and '上海' not in caplog.text


def test_no_seat_diagnostics_when_every_seat_is_known(caplog):
    caplog.set_level(logging.INFO)
    rail_items(reply(railway([dict(code='O', cost='626.0')])))
    assert 'transport_rail_seat_codes_dropped' not in caplog.text
    assert 'transport_rail_segments_without_seats' not in caplog.text
