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
