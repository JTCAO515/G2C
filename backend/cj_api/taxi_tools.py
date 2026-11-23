"""Information-only taxi contracts. HK stays disabled until provider verification."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import logging
from time import sleep
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from cj_strict_json import reject_duplicates

from .didi_mcp import DiDiTool
from .plugin_tools import PluginError, register_plugin
from .taxi_geography import gcj_to_wgs, in_mainland, wgs_to_gcj


VERSION = 'TAXI.1'
ESTIMATE = '/v1/tools/taxi/estimate'
LINK = '/v1/tools/taxi/link'
DAILY_LIMIT = 50
APP_LINK_HOST = 'v.didi.cn'
APP_LINK_PATH = '/XvYQEWe'
LINK_COORDINATES = {
    'slng': 'from_lng', 'slat': 'from_lat', 'dlng': 'to_lng', 'dlat': 'to_lat',
}
_LOGGER = logging.getLogger(__name__)


class DiDiEstimateExpired(PluginError):
    def __init__(self):
        super().__init__(502, 'supplier_unavailable')


class DiDiInformation:
    """Transport receives only fixed-tool calls. This adapter owns error mapping."""

    def __init__(self, transport, *, wait=sleep):
        self._transport = transport
        self._wait = wait

    def _send(self, selected, params):
        try:
            result = self._transport(selected, params)
        except TimeoutError:
            raise PluginError(504, 'supplier_timeout') from None
        except OSError:
            raise PluginError(502, 'supplier_unavailable') from None
        if type(result) is not dict:
            raise PluginError(502, 'supplier_unavailable')
        error = result.get('error')
        return result, error.get('code') if type(error) is dict else None

    def call(self, tool, params, *, retry=True):
        selected = DiDiTool(tool)
        result, code = self._send(selected, params)
        if retry and (code == -32001 or (code == -32021 and selected is DiDiTool.ESTIMATE)):
            if code == -32001:
                self._wait(0.25)
            result, code = self._send(selected, params)
        if code == -32001:
            raise PluginError(429, 'rate_limited')
        if code == -32002:
            _LOGGER.warning('ALERT didi_key_rejected')
        if code == -32010:
            raise PluginError(400, 'invalid_request')
        if code == -32021:
            raise DiDiEstimateExpired()
        if 'error' in result or result.get('isError') is True:
            raise PluginError(502, 'supplier_unavailable')
        return result


class WireModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Point(WireModel):
    lat: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    lng: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    coordinate_system: Literal['WGS-84', 'GCJ-02']
    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, name):
        if name is not None:
            if not name.strip() or any(ord(char) < 32 for char in name):
                raise ValueError('invalid name')
            name.encode('utf-8')
        return name


class EstimateRequest(WireModel):
    version: Literal['TAXI.1']
    origin: Point
    destination: Point


class LinkRequest(EstimateRequest):
    vehicle_category: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,48}$')] | None = None


class Vehicle(WireModel):
    category: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,48}$')]
    name: Annotated[str, Field(min_length=1, max_length=80)]
    price_display: Annotated[str, Field(min_length=1, max_length=120)]
    currency: Literal['CNY'] = 'CNY'
    price_min_minor: Annotated[int, Field(ge=0)] | None = None
    price_max_minor: Annotated[int, Field(ge=0)] | None = None


class EstimateOutput(WireModel):
    vehicles: Annotated[list[Vehicle], Field(min_length=1, max_length=32)]
    distance_m: Annotated[int, Field(ge=0)] | None = None
    trace_id: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')] | None = None


def _public_link(raw, params):
    try:
        if type(raw) is not str or len(raw) > 512 or any(ord(char) <= 32 for char in raw):
            raise ValueError('invalid link')
        target = urlsplit(raw)
        if ((target.scheme, target.netloc, target.path) != ('https', APP_LINK_HOST, APP_LINK_PATH)
                or target.fragment):
            raise ValueError('invalid link target')
        pairs = parse_qsl(target.query, strict_parsing=True)
        query = dict(pairs)
        if (len(pairs) != len(LINK_COORDINATES) or query.keys() != LINK_COORDINATES.keys()
                or any(Decimal(query[key]) != Decimal(params[field]) for key, field in LINK_COORDINATES.items())):
            raise ValueError('invalid link coordinates')
    except (InvalidOperation, ValueError):
        raise PluginError(502, 'supplier_unavailable') from None
    return dict(url=raw, link_type='https')


def _gcj_strings(point):
    source = (point.lng, point.lat)
    if not 72 < point.lng < 136 or not 17 < point.lat < 55:
        raise PluginError(422, 'out_of_service_area')
    original_wgs = source if point.coordinate_system == 'WGS-84' else gcj_to_wgs(*source)
    if not in_mainland(*original_wgs):
        raise PluginError(422, 'out_of_service_area')
    lng, lat = wgs_to_gcj(*source) if point.coordinate_system == 'WGS-84' else source
    return f'{lng:.6f}', f'{lat:.6f}'


class TaxiService:
    def __init__(self, provider, *, clock=lambda: datetime.now(timezone.utc)):
        self.provider = provider
        self.clock = clock

    def _points(self, request):
        # Validate both before any DiDi call, including reverse geocoding.
        first_lng, first_lat = _gcj_strings(request.origin)
        last_lng, last_lat = _gcj_strings(request.destination)
        return dict(from_lat=first_lat, from_lng=first_lng, to_lat=last_lat, to_lng=last_lng)

    def _resolve_name(self, point, lng, lat):
        if point.name is not None:
            return point.name
        result = self.provider.call(DiDiTool.REGEOCODE, {'location': f'{lng},{lat}'})
        try:
            text = result['content'][0]['text']
            address = json.loads(text, object_pairs_hook=reject_duplicates(ValueError, 'duplicate address field'))
        except (IndexError, KeyError, RecursionError, TypeError, ValueError):
            raise PluginError(422, 'coordinate_unverified') from None
        for key in ('display_name', 'formatted_address'):
            name = address.get(key) if type(address) is dict else None
            if (type(name) is str and 0 < len(name) <= 120 and not any(ord(char) < 32 for char in name)
                    and any('\u4e00' <= char <= '\u9fff' for char in name)):
                return name
        raise PluginError(422, 'coordinate_unverified')

    def _named_estimate(self, request, params, *, retry=True):
        origin = self._resolve_name(request.origin, params['from_lng'], params['from_lat'])
        destination = self._resolve_name(request.destination, params['to_lng'], params['to_lat'])
        return self.provider.call(DiDiTool.ESTIMATE, dict(params, from_name=origin, to_name=destination), retry=retry)

    def estimate(self, request):
        result = self._named_estimate(request, self._points(request))
        try:
            data = result['structuredContent']
            output = EstimateOutput.model_validate(dict(
                vehicles=[dict(category=item['productCategory'], name=item['productName'],
                               price_display=item['priceText']) for item in data['items']],
                trace_id=data.get('traceId'),
            ))
        except (AttributeError, KeyError, TypeError, ValidationError):
            raise PluginError(502, 'supplier_unavailable') from None
        return dict(version=VERSION, **output.model_dump(exclude_none=True),
                    observed_at=self.clock().isoformat())

    def link(self, request):
        points = self._points(request)
        try:
            result = self.provider.call(DiDiTool.LINK, points)
        except DiDiEstimateExpired:
            self._named_estimate(request, points, retry=False)
            result = self.provider.call(DiDiTool.LINK, points, retry=False)
        data = result.get('structuredContent')
        raw = data.get('appLink') if type(data) is dict else None
        return dict(version=VERSION, **_public_link(raw, points))


def register_taxi_routes(app, *, taxi=None, checker=None, internal=frozenset(), calls=None):
    enabled = taxi is not None
    register_plugin(app, ESTIMATE, EstimateRequest, taxi.estimate if enabled else None,
                    enabled=enabled, checker=checker, internal=internal, calls=calls, limit=DAILY_LIMIT)
    register_plugin(app, LINK, LinkRequest, taxi.link if enabled else None,
                    enabled=enabled, checker=checker, internal=internal, calls=calls, limit=DAILY_LIMIT)
