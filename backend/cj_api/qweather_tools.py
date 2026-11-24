"""Project-scoped QWeather observations, forecasts, and official alerts."""

from datetime import datetime
from math import isfinite
import re
from time import monotonic
from typing import Annotated, Literal

import httpx
from pydantic import Field, model_validator

from .plugin_tools import PluginError, register_plugin
from .taxi_tools import WireModel
from .travel_provider import ShortCache, check_status, checked_key, provider_client, read_reply, supplier_json


ROUTE = '/v1/tools/weather'
VERSION = 'WEATHER.1'
DAILY_LIMIT = 200
HOST = re.compile(r'[a-z0-9-]{4,50}(?:\.yun)?\.qweatherapi\.com')
CITY_POINTS = {'beijing': (39.90, 116.41), 'chengdu': (30.57, 104.07), 'shanghai': (31.23, 121.47)}
PATHS = {'current': '/weather/v1/current', 'hourly': '/weather/v1/hourly',
         'daily': '/weather/v1/daily', 'alerts': '/weatheralert/v1/current'}
ATTRIBUTION = 'https://www.qweather.com/'


class WeatherInput(WireModel):
    version: Literal['WEATHER.1']
    kind: Literal['current', 'hourly', 'daily', 'alerts']
    language: Literal['zh', 'en']
    city: Literal['beijing', 'chengdu', 'shanghai'] | None = None
    lat: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)] | None = None
    lng: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None = None

    @model_validator(mode='after')
    def one_location(self):
        if self.city is None and None not in (self.lat, self.lng):
            return self
        if self.city is not None and self.lat is None and self.lng is None:
            return self
        raise ValueError('one location required')

    def coordinates(self):
        lat, lng = CITY_POINTS[self.city] if self.city else (self.lat, self.lng)
        return f'{lat:.2f}', f'{lng:.2f}'


def _text(value, limit=160):
    if (type(value) is not str or not value.strip() or len(value) > limit
            or any(ord(c) < 32 and c not in '\r\n\t' for c in value)):
        raise ValueError('invalid weather text')
    value.encode('utf8')
    return value


def _when(value):
    raw = _text(value, 40)
    if datetime.fromisoformat(raw).utcoffset() is None:
        raise ValueError('timezone required')
    return raw


def _number(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not isfinite(value):
        raise ValueError('invalid weather measurement')
    return value


def _measurement(row, field, unit, low, high):
    value = row[field]
    if value['unit'] != unit:
        raise ValueError('unexpected measurement unit')
    return _number(value['value'], low, high)


def _conditions(row, time_field):
    out = dict(at=_when(row[time_field]), condition=_text(row['condition']['text']),
               temperature_c=_measurement(row, 'temperature', '°C', -100, 80))
    if row.get('feelsLike') is not None:
        out['feels_like_c'] = _measurement(row, 'feelsLike', '°C', -150, 100)
    if row.get('humidity') is not None:
        out['humidity_percent'] = round(100 * _number(row['humidity'], 0, 1))
    if row.get('wind') is not None:
        out['wind_mps'] = _measurement(row['wind'], 'speed', 'm/s', 0, 200)
    if row.get('precipitation') and row['precipitation'].get('probability') is not None:
        out['precipitation_percent'] = round(100 * _number(row['precipitation']['probability'], 0, 1))
    if row.get('uvIndex') is not None:
        out['uv_index'] = _number(row['uvIndex'], 0, 30)
    return out


def _daily(row):
    return dict(at=_when(row['forecastStartTime']),
                min_c=_measurement(row, 'temperatureMin', '°C', -100, 80),
                max_c=_measurement(row, 'temperatureMax', '°C', -100, 80),
                condition=_text(row['daytime']['condition']['text']))


def _alert(row):
    out = dict(id=_text(row['id']), headline=_text(row['headline'], 500),
               issued_at=_when(row['issuedTime']), description=_text(row['description'], 12000))
    for upstream, field in (('senderName', 'sender'), ('severity', 'severity'), ('instruction', 'instruction')):
        if row.get(upstream):
            out[field] = _text(row[upstream], 12000 if field == 'instruction' else 160)
    if row.get('expireTime'):
        out['expires_at'] = _when(row['expireTime'])
    if row.get('messageType'):
        out['message_type'] = _text(row['messageType']['code'])
    return out


def _project(kind, value):
    attributions = value['metadata']['attributions']
    if type(attributions) is not list or not 1 <= len(attributions) <= 16:
        raise ValueError('weather attribution required')
    result = dict(version=VERSION, kind=kind, source='QWeather', source_url=ATTRIBUTION,
                  attributions=[_text(text, 1500) for text in attributions])
    if kind == 'current':
        return dict(result, items=[_conditions(value, 'validTime')])
    key, limit, project = {
        'hourly': ('hours', 24, lambda row: _conditions(row, 'forecastTime')),
        'daily': ('days', 7, _daily),
        'alerts': ('alerts', 50, _alert),
    }[kind]
    rows = value.get(key, [] if kind == 'alerts' and value['metadata'].get('zeroResult') is True else None)
    if type(rows) is not list or len(rows) > limit or not rows and kind != 'alerts':
        raise ValueError('invalid weather collection')
    return dict(result, items=[project(row) for row in rows])


class QWeather:
    def __init__(self, host, key, *, client=provider_client):
        if not HOST.fullmatch(host):
            raise ValueError('invalid project API host')
        checked_key(key)
        self.host, self.key, self.client = host, key, client
        self.cache = ShortCache(120)
        self.alerts = ShortCache(45)

    def query(self, request, reserve):
        point = request.coordinates()
        cache = self.alerts if request.kind == 'alerts' else self.cache
        return cache.load((request.kind, request.language, point), lambda: self._fetch(request, point, reserve))

    def _fetch(self, request, point, reserve):
        params = dict(lang=request.language, localTime='true')
        if request.kind == 'hourly':
            params['hours'] = '24'
        if request.kind == 'daily':
            params['days'] = '7'
        url = f'https://{self.host}{PATHS[request.kind]}/{point[0]}/{point[1]}'
        try:
            with self.client() as client:
                reserve('qweather:dispatch', None)
                deadline = monotonic() + 10
                with client.stream('GET', url, params=params, headers={'X-QW-Api-Key': self.key}) as response:
                    check_status(response.status_code)
                    value = supplier_json(b''.join(read_reply(response, deadline)), self.key)
            return _project(request.kind, value)
        except httpx.TimeoutException:
            raise PluginError(504, 'supplier_timeout') from None
        except (httpx.HTTPError, AttributeError, KeyError, TypeError, ValueError, RecursionError):
            raise PluginError(502, 'supplier_unavailable') from None


def register_weather(app, *, service=None, checker=None, internal=frozenset(), calls=None):
    register_plugin(app, ROUTE, WeatherInput, service.query if service else None, enabled=service is not None,
                    checker=checker, internal=internal, calls=calls, limit=DAILY_LIMIT, count_provider_calls=True)
