"""Fixes from the run -42 intercity smoke (#1521): AMap seat names, one flight lookup per search, read-only tools."""
from contextlib import contextmanager
import json

import httpx
import pytest

from cj_api.lio_transport import rail_items, validate_rail_items
from cj_api.plugin_tools import PluginError
from cj_api.variflight_tools import VariFlight


# Exactly as AMap returned them on HK (run -42, Shanghai -> Beijing, 2026-12-02; #1521 comment 7164503770).
T110 = [dict(code='火车硬座', cost='177.5'), dict(code='火车硬卧下铺', cost='325.5'), dict(code='火车软卧下铺', cost='497.5'),
        dict(code='火车硬卧中铺', cost='315.5'), dict(code='火车无座', cost='177.5'), dict(code='火车硬卧上铺', cost='304.5')]
G28 = [dict(code='火车无座', cost='637.0'), dict(code='火车商务座', cost='2192.0'), dict(code='火车二等座', cost='636.0'),
       dict(code='火车二等座', cost='637.0'), dict(code='火车软座', cost='1444.0'), dict(code='火车无座', cost='636.0'),
       dict(code='火车商务座', cost='2190.0'), dict(code='不分仓位级别', cost='1442.0'), dict(code='火车一等座', cost='1049.0'),
       dict(code='火车一等座', cost='1051.0')]


def reply(*rails):
    return dict(status='1', infocode='10000', route=dict(transits=[dict(segments=[dict(walking={}, railway=dict(
        trip=trip, departure_stop=dict(name='上海虹桥', time=depart), arrival_stop=dict(name='北京南', time=arrive),
        spaces=spaces))]) for trip, depart, arrive, spaces in rails]))


def test_amap_chinese_seat_names_become_classes_from_the_lowest_price():
    items = rail_items(reply(('T110', '0705', '1857', T110), ('G28', '0800', '1228', G28)))
    t110, g28 = items
    assert [(seat['class_zh'], seat['class_en'], seat['price_cny_minor']) for seat in t110['seats']] == [
        ('硬座', 'Hard seat', 17750), ('无座', 'Standing (no seat)', 17750),
        ('硬卧', 'Hard sleeper', 30450), ('软卧', 'Soft sleeper', 49750)]
    assert [(seat['class_zh'], seat['price_cny_minor']) for seat in g28['seats']] == [
        ('二等座', 63600), ('无座', 63600), ('一等座', 104900), ('软座', 144400), ('商务座', 219000)]
    assert validate_rail_items(items)


def test_unclassified_or_unknown_seat_names_are_dropped_not_guessed():
    items = rail_items(reply(('G28', '0800', '1228', [dict(code='不分仓位级别', cost='1442.0'),
                                                       dict(code='火车包厢', cost='3000.0')])))
    assert items[0]['seats'] == [] and items[0]['availability'] is None


KEY = 'offline-provider-key'


def fixture_transport(handler):
    @contextmanager
    def client():
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as connection:
            yield connection
    return client


class Lookup:
    def __init__(self, tool):
        self.tool = tool

    def tool_call(self):
        return self.tool, dict(date='2026-12-02')


@pytest.mark.parametrize('tool', ['createOrder', 'payOrder', 'followFlight', 'tools/list', ''])
def test_only_read_only_tools_can_ever_be_called(tool):
    seen = []
    provider = VariFlight(KEY, client=fixture_transport(lambda http: seen.append(http) or httpx.Response(500)))
    with pytest.raises(PluginError) as refused:
        provider.query(Lookup(tool), lambda *_: None)
    assert (refused.value.status, refused.value.code) == (503, 'unavailable') and seen == []


# VariFlight getFlightList as observed on HK (run -42, #1521 comment 7164717828): a short non-JSON text block plus
# structuredContent {"kind": "collection", "items": [...]}, items keyed fnum / dep / arr / departurePlanTime / ...
def flight(fnum, dep, arr, depart, arrive, *, share=0, operating='', cn='东方航空', en='China Eastern Airlines'):
    return dict(fnum=fnum, dep=dep, arr=arr, depAirport='上海虹桥', arrAirport='北京首都', departurePlanTime=depart,
                arrivalPlanTime=arrive, departureEstimateTime='', departureActualTime='', airlineCnName=cn,
                airlineName=en, airlinesCode=fnum[:2], isShare=share, shareFlight=operating, shareFlightList=[],
                flightStatus='计划', date='2026-12-02', distance=1178, uuid='x')


def collection(items):
    def handler(http):
        call = json.loads(http.content)
        if call['method'] == 'initialize':
            return httpx.Response(200, json=dict(jsonrpc='2.0', id=1, result={'protocolVersion': '2025-11-25'}))
        if call['method'] == 'notifications/initialized':
            return httpx.Response(202)
        assert call['params'] == dict(name='getFlightList', arguments=dict(dep='SHA,PVG', arr='PEK,PKX', date='2026-12-02'))
        return httpx.Response(200, json=dict(jsonrpc='2.0', id=2, result=dict(
            isError=False, content=[dict(type='text', text='共找到 75 条航班信息，详见结构化数据')],
            structuredContent=dict(kind='collection', items=items))))
    return handler


def transport_flights(items):
    from cj_api.lio_transport import CITIES, TransportService
    service = TransportService(flights=VariFlight(KEY, client=fixture_transport(collection(items))))
    return service._flight(CITIES['shanghai'], CITIES['beijing'], '2026-12-02', lambda *_: None)


def test_variflight_collection_items_become_flights_keeping_the_operating_carrier():
    result = transport_flights([
        flight('FM9101', 'SHA', 'PEK', '2026-12-02 07:30:00', '2026-12-02 09:40:00', share=1, operating='MU5101',
               cn='上海航空', en='Shanghai Airlines'),
        flight('MU5101', 'SHA', 'PEK', '2026-12-02 07:30:00', '2026-12-02 09:40:00'),
        flight('CA1858', 'PVG', 'PKX', '2026-12-02 13:05', '2026-12-02 15:25', cn='中国国际航空', en='Air China'),
        flight('HO1251', 'SHA', 'PEK', '1796171400', '1796179200', cn='吉祥航空', en='Juneyao Air'),
        flight('MU5199', 'SHA', 'PEK', '2026-12-03 07:30:00', '2026-12-03 09:40:00'),
        flight('BAD1', 'SHA', 'PEK', 'soon', '2026-12-02 12:00:00'),
    ])
    assert result['status'] == 'ok'
    assert [(item['number'], item['depart_time'], item['arrive_time'], item['duration_min']) for item in result['items']] == [
        ('MU5101', '07:30', '09:40', 130), ('HO1251', '08:30', '10:40', 130), ('CA1858', '13:05', '15:25', 140)]
    mu = result['items'][0]
    assert mu['carrier'] == dict(name_zh='东方航空', name_en='China Eastern Airlines')
    assert mu['depart_airport']['iata'] == 'SHA' and mu['arrive_airport']['name_en'] == 'Beijing Capital International Airport'


def test_all_flights_of_a_busy_route_reach_the_transport_list():
    items = [flight(f'MU{5100 + n}', 'SHA', 'PEK', f'2026-12-02 {6 + n // 4:02d}:{(n % 4) * 15:02d}:00',
                    f'2026-12-02 {8 + n // 4:02d}:{(n % 4) * 15:02d}:00') for n in range(64)]
    provider = VariFlight(KEY, client=fixture_transport(collection(items)))
    from cj_api.lio_transport import RouteLookup
    projected = provider.query(RouteLookup('2026-12-02', 'SHA,PVG', 'PEK,PKX'), lambda *_: None)
    assert len(projected['items']) == 64 and projected['more'] is False
    result = transport_flights(items)
    assert len(result['items']) == 20 and result['items'][0]['number'] == 'MU5100'


def test_non_ascii_airline_name_is_not_shown_as_english():
    result = transport_flights([flight('MU5101', 'SHA', 'PEK', '2026-12-02 07:30:00', '2026-12-02 09:40:00', en='东方航空')])
    assert result['items'][0]['carrier'] == dict(name_zh='东方航空')
