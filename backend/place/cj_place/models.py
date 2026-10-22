"""PLACE internal values. These are evidence types, never authorization tokens."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Generic, Literal, TypeVar
import re

CONTRACT_VERSION = "CJ-PLACE-GAODE@0.1.0-rc.1"
ORIGIN = "https://restapi.amap.com"
T = TypeVar("T")


class FieldState(str, Enum):
    PRESENT = "present"
    MISSING = "missing"
    EMPTY_ARRAY = "empty_array"
    EMPTY_STRING = "empty_string"
    NULL = "null"
    INVALID = "invalid"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Observed(Generic[T]):
    state: FieldState
    value: T | None = None

    def __post_init__(self):
        if not isinstance(self.state, FieldState):
            raise ValueError("field_state")
        if (self.state is FieldState.PRESENT) != (self.value is not None):
            raise ValueError("field_value")


def text_value(value: object, limit: int = 1024) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > limit:
        raise ValueError("text")
    if any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError("text")
    return value


def identifier(value: object) -> str:
    value = text_value(value, 200)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("provider_id")
    return value


def aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("aware_time_required")
    return value


@dataclass(frozen=True)
class Coordinate:
    """Exact provider text and Decimal values. No conversion, rounding or zero fill."""
    raw: str
    longitude: Decimal = field(init=False)
    latitude: Decimal = field(init=False)
    crs: Literal["GCJ-02"] = field(default="GCJ-02", init=False)

    def __post_init__(self):
        if not isinstance(self.raw, str) or not re.fullmatch(
            r"-?[0-9]{1,3}(?:\.[0-9]{1,12})?,-?[0-9]{1,2}(?:\.[0-9]{1,12})?", self.raw
        ):
            raise ValueError("coordinate")
        lon, lat = map(Decimal, self.raw.split(","))
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("coordinate_range")
        object.__setattr__(self, "longitude", lon)
        object.__setattr__(self, "latitude", lat)

    def same_position(self, other: Coordinate) -> bool:
        return (self.longitude, self.latitude, self.crs) == (
            other.longitude, other.latitude, other.crs
        )


@dataclass(frozen=True)
class Place:
    provider_id: str
    name_zh: str
    address_zh: Observed[str]
    coordinate: Observed[Coordinate]
    entrance_coordinate: Observed[Coordinate]
    exit_coordinate: Observed[Coordinate]
    parent_id: Observed[str]
    navigation_id: Observed[str]
    typecode: Observed[str]
    official_name_en: Observed[str] = field(default_factory=lambda: Observed(FieldState.UNKNOWN))
    official_address_en: Observed[str] = field(default_factory=lambda: Observed(FieldState.UNKNOWN))
    provider: Literal["gaode"] = field(default="gaode", init=False)


@dataclass(frozen=True)
class Search:
    keyword: str
    city: str
    page: int
    page_size: int

    def __post_init__(self):
        text_value(self.keyword, 256)
        text_value(self.city, 128)
        if "|" in self.keyword:
            raise ValueError("one_keyword_required")
        if type(self.page) is not int or type(self.page_size) is not int:
            raise ValueError("pagination")
        if not 1 <= self.page_size <= 25 or self.page < 1 or self.page * self.page_size > 200:
            raise ValueError("pagination")


@dataclass(frozen=True)
class Detail:
    provider_id: str

    def __post_init__(self):
        identifier(self.provider_id)


@dataclass(frozen=True)
class Endpoint:
    provider_id: str
    coordinate: Coordinate
    coordinate_role: Literal["poi_center", "entrance", "exit"]

    def __post_init__(self):
        identifier(self.provider_id)
        if type(self.coordinate) is not Coordinate:
            raise ValueError("coordinate")
        if self.coordinate_role not in ("poi_center", "entrance", "exit"):
            raise ValueError("coordinate_role")
        if any(len(part.partition(".")[2]) > 6 for part in self.coordinate.raw.split(",")):
            raise ValueError("route_coordinate_precision")


def endpoint_from_place(place: Place, role: Literal["poi_center", "entrance", "exit"]) -> Endpoint:
    """Select exactly one observed point, never fall back to another building/role.

    The caller must retain Result.source and check evidence/freshness separately.
    This is a projection of parsed evidence, not provider authentication.
    """
    if type(place) is not Place or role not in ("poi_center", "entrance", "exit"):
        raise ValueError("place_endpoint")
    observed = {"poi_center": place.coordinate, "entrance": place.entrance_coordinate,
                "exit": place.exit_coordinate}[role]
    if observed.state is not FieldState.PRESENT:
        raise ValueError("coordinate_unavailable")
    return Endpoint(place.provider_id, observed.value, role)


@dataclass(frozen=True)
class Departure:
    condition: Literal["at_query_time", "specified_time"]
    at: datetime | None

    def __post_init__(self):
        if self.condition == "at_query_time" and self.at is None:
            return
        if self.condition == "specified_time" and self.at is not None:
            aware(self.at)
            return
        raise ValueError("departure")


@dataclass(frozen=True)
class RouteQuery:
    origin: Endpoint
    destination: Endpoint
    mode: Literal["walking", "driving"]
    departure: Departure

    def __post_init__(self):
        if type(self.origin) is not Endpoint or type(self.destination) is not Endpoint:
            raise ValueError("endpoint")
        if self.mode not in ("walking", "driving") or type(self.departure) is not Departure:
            raise ValueError("route_query")


Query = Search | Detail | RouteQuery


@dataclass(frozen=True)
class Quantity:
    raw: str
    value: Decimal
    unit: Literal["m", "s"]


@dataclass(frozen=True)
class Route:
    query: RouteQuery
    distance: Observed[Quantity]
    duration: Observed[Quantity]
    time_semantics: Literal["provider_estimate_at_query_time"] = "provider_estimate_at_query_time"
    future_guaranteed: Literal[False] = False


class Outcome(str, Enum):
    OK = "ok"
    NO_RESULTS = "no_results"
    RATE_LIMITED = "rate_limited"
    PROVIDER_ERROR = "provider_error"
    UNKNOWN = "unknown"
    INVALID_RESPONSE = "invalid_response"
    BINDING_MISMATCH = "binding_mismatch"
    STALE = "stale"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Source:
    endpoint: str
    query_started_at: datetime
    received_at: datetime
    request_ref: str
    binding_digest: str
    evidence: Literal["synthetic", "unverified_bytes"]
    provider: Literal["gaode"] = "gaode"
    api_version: Literal["v3"] = "v3"
    provider_updated_at: None = None  # not supplied by these endpoints


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    query: Query
    reason: str  # fixed local code; never provider info/body/exception text
    source: Source | None = None
    places: tuple[Place, ...] = ()
    routes: tuple[Route, ...] = ()
    provider_code: str | None = None
    provider_count: int | None = None
    contract_version: str = CONTRACT_VERSION
