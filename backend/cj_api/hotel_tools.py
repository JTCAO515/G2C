"""Hotel information entry point. The live affiliate handoff is a separate binding."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .plugin_tools import PluginError, register_plugin


VERSION = 'HOTEL.1'
ROUTE = '/v1/tools/hotel/link'
HANDOFF_PATH = '/v1/tools/hotel/out/'
FILTERS = ('location', 'check_in', 'check_out', 'guests', 'language', 'accepts_foreign_guests')


class Location(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    lat: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    lng: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    radius_m: Annotated[int, Field(gt=0)]


class HotelRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    version: Literal['HOTEL.1']
    city: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    location: Location | None = None
    check_in: str
    check_out: str
    guests: Annotated[int, Field(gt=0)]
    language: Literal['zh', 'en']

    @field_validator('city')
    @classmethod
    def validate_city(cls, value):
        if value is not None:
            if not value.strip() or any(ord(char) < 32 for char in value):
                raise ValueError('invalid city')
            value.encode('utf-8')
        return value

    @field_validator('check_in', 'check_out')
    @classmethod
    def validate_date(cls, value):
        parsed = date.fromisoformat(value)
        if value != parsed.isoformat():
            raise ValueError('expected YYYY-MM-DD')
        return value

    @model_validator(mode='after')
    def validate_stay(self):
        if (self.city is None) == (self.location is None):
            raise ValueError('choose one location type')
        if self.check_out <= self.check_in:
            raise ValueError('check-out must follow check-in')
        return self


class HotelHandoff(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    handle: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{22,128}$')]
    applied_filters: Annotated[list[str], Field(max_length=len(FILTERS))]

    @field_validator('applied_filters')
    @classmethod
    def validate_filters(cls, values):
        if any(value not in FILTERS for value in values) or len(set(values)) != len(values):
            raise ValueError('unknown or duplicate filter')
        return values


class HotelService:
    def __init__(self, create_handoff, public_origin):
        self.create_handoff = create_handoff
        self.public_origin = public_origin

    def link(self, request):
        try:
            handoff = HotelHandoff.model_validate(self.create_handoff(request))
        except TimeoutError:
            raise PluginError(504, 'supplier_timeout') from None
        except (ValidationError, OSError):
            raise PluginError(502, 'supplier_unavailable') from None
        return dict(version=VERSION, url=self.public_origin + HANDOFF_PATH + handoff.handle,
                    applied_filters=handoff.applied_filters,
                    unapplied_filters=[value for value in FILTERS if value not in handoff.applied_filters])


def register_hotel_route(app, *, hotel=None, checker=None, internal=frozenset(), calls=None):
    register_plugin(app, ROUTE, HotelRequest, hotel.link if hotel is not None else None,
                    enabled=hotel is not None, checker=checker, internal=internal, calls=calls, limit=None)
