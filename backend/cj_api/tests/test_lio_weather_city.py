from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import json
from cj_api.lio_weather import CITY_EFFECT, encode_query, decode_query
from cj_api.lio_city import CityReference
from cj_api.lio_dialogue_routes import _message
from cj_message.lio_context import LioCitation
from cj_message.lio_timeline import TimelineMessage
from cj_fact.live_source import weather_for_adcode
from cj_fact.policy import FactFailure
import unittest

class NationalLioWeatherCity(unittest.TestCase):

    def test_public_reference_uses_actual_city_not_beijing(self):
        for (adcode, name, weather_code) in [('310000', '上海市', '101020100'), ('510100', '成都市', '101270101'), ('610100', '西安市', '101110101'), ('450300', '桂林市', '101300501'), ('440100', '广州市', '101280101'), ('330100', '杭州市', '101210101')]:
            with self.subTest(adcode=adcode, name=name, weather_code=weather_code):
                effects = (LioCitation('tool0', 'Amap Weather', None, '2026-11-11T08:00:00Z').effect(), CITY_EFFECT + json.dumps(dict(adcode=adcode, name=name)))
                state = SimpleNamespace(status='completed', text='Forecast source received.', draft_outcome=None, effects=effects)
                result = _message(TimelineMessage('m', 'r', 1, 'Weather?', 'en'), state)
                assert result['sources'][1]['url'] == 'https://www.weather.com.cn/weather/' + weather_code + '.shtml'
                assert 'Beijing' not in result['sources'][1]['title']

    def test_unknown_public_reference_keeps_only_original_source_name(self):
        effects = (LioCitation('t', '高德天气', None, '2026-11-11T08:00:00Z').effect(), CITY_EFFECT + json.dumps(dict(adcode='330782', name='义乌市')))
        state = SimpleNamespace(status='completed', text='预报来源已收到。', draft_outcome=None, effects=effects)
        result = _message(TimelineMessage('m', 'r', 1, '天气', 'zh'), state)
        assert len(result['sources']) == 1 and result['sources'][0]['title'] == '高德天气'

    def test_forecast_validates_provider_adcode_and_preserves_actual_reporttime(self):
        city = CityReference('310000', '上海市', '上海市', None, 'province', 'Asia/Shanghai')
        query = decode_query(encode_query(city, '2026-11-12', '2026-11-12'))
        body = dict(status='1', infocode='10000', count='1', forecasts=[dict(adcode='310000', reporttime='2026-11-11 15:00:00', casts=[dict(date='2026-11-12', dayweather='晴')])])
        with patch('cj_fact.live_source._weather_exchange', new=AsyncMock(return_value=json.dumps(body).encode())) as send:
            result = weather_for_adcode(query, 'not-a-real-key', guard=lambda : True)
        assert send.call_args.kwargs['adcode'] == '310000'
        assert result['region_adcode'] == '310000' and result['provider_reporttime'] == '2026-11-11 15:00:00'
        body['forecasts'][0]['adcode'] = '110000'
        with patch('cj_fact.live_source._weather_exchange', new=AsyncMock(return_value=json.dumps(body).encode())), self.assertRaises(FactFailure):
            weather_for_adcode(query, 'not-a-real-key', guard=lambda : True)
