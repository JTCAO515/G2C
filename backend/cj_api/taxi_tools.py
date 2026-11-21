"""Information-only taxi contracts. HK stays disabled until provider verification."""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .plugin_tools import PluginError, register_plugin


VERSION = 'TAXI.1'
ESTIMATE = '/v1/tools/taxi/estimate'
LINK = '/v1/tools/taxi/link'
DAILY_LIMIT = 50


class DiDiTool(str, Enum):
    TEXT_SEARCH = 'maps_textsearch'
    REGEOCODE = 'maps_regeocode'
    ESTIMATE = 'taxi_estimate'
    LINK = 'taxi_generate_ride_app_link'


class DiDiInformation:
    """Transport receives only fixed-tool calls. This adapter owns error mapping."""

    def __init__(self, transport):
        self._transport = transport

    def call(self, tool, params):
        selected = DiDiTool(tool)
        try:
            result = self._transport(selected.value, params)
        except TimeoutError:
            raise PluginError(504, 'supplier_timeout') from None
        except OSError:
            raise PluginError(502, 'supplier_unavailable') from None
        if type(result) is not dict:
            raise PluginError(502, 'supplier_unavailable')
        if 'error' in result:
            error = result['error']
            if type(error) is dict and error.get('code') == -32001:
                raise PluginError(429, 'rate_limited')
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


def _public_link(raw, allowed):
    # Until #1309 verifies the real URL grammar, only fixed, reviewed fixture
    # URLs are approved. Provider-controlled path, query and fragment never pass.
    if type(raw) is not str or raw not in allowed:
        raise PluginError(502, 'supplier_unavailable')
    return dict(url=raw, link_type='https' if urlsplit(raw).scheme == 'https' else 'app_scheme')


class TaxiService:
    def __init__(self, provider, resolve_point, allowed_links, *, clock=lambda: datetime.now(timezone.utc)):
        self.provider = provider
        self.resolve_point = resolve_point
        self.allowed_links = allowed_links
        self.clock = clock

    def _points(self, request, *, with_names):
        first = self.resolve_point(request.origin, with_names)
        last = self.resolve_point(request.destination, with_names)
        params = dict(from_lat=first.lat, from_lng=first.lng, to_lat=last.lat, to_lng=last.lng)
        if with_names:
            params.update(from_name=first.name, to_name=last.name)
        return params

    def estimate(self, request):
        result = self.provider.call(DiDiTool.ESTIMATE, self._points(request, with_names=True))
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
        params = self._points(request, with_names=False)
        result = self.provider.call(DiDiTool.LINK, params)
        data = result.get('structuredContent')
        raw = data.get('url') if type(data) is dict else None
        return dict(version=VERSION, **_public_link(raw, self.allowed_links))


def register_taxi_routes(app, *, taxi=None, checker=None, internal=frozenset(), calls=None):
    enabled = taxi is not None
    register_plugin(app, ESTIMATE, EstimateRequest, taxi.estimate if enabled else None,
                    enabled=enabled, checker=checker, internal=internal, calls=calls, limit=DAILY_LIMIT)
    register_plugin(app, LINK, LinkRequest, taxi.link if enabled else None,
                    enabled=enabled, checker=checker, internal=internal, calls=calls, limit=DAILY_LIMIT)
