"""Bounded Gaode v3 preparation and parsing. Contains no HTTP client or credentials."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, DecimalException
from hashlib import sha256
import json
import math
import re
from urllib.parse import urlencode

from .models import (
    CONTRACT_VERSION, ORIGIN, Coordinate, Detail, FieldState, Observed, Outcome,
    Place, Quantity, Query, Result, Route, RouteQuery, Search, Source, aware,
    identifier, text_value,
)


class PreparationError(ValueError):
    """Only fixed, non-sensitive local reason codes are exposed."""


@dataclass(frozen=True)
class Config:
    origin: str
    max_request_bytes: int
    max_response_bytes: int
    timeout_seconds: float
    max_age_seconds: float

    def __post_init__(self):
        if self.origin != ORIGIN:
            raise ValueError("provider_origin")
        for value in (self.max_request_bytes, self.max_response_bytes):
            if type(value) is not int or value <= 0:
                raise ValueError("byte_limit")
        for value in (self.timeout_seconds, self.max_age_seconds):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("time_limit")


@dataclass(frozen=True, repr=False)
class PreparedRequest:
    query: Query
    origin: str
    path: str
    params: tuple[tuple[str, str], ...]
    request_ref: str
    started_at: datetime
    binding_digest: str

    def __repr__(self):
        return "PreparedRequest(<private query>)"


@dataclass(frozen=True, repr=False)
class Response:
    """Association metadata is supplied by a trusted transport, not provider JSON."""
    binding_digest: str
    origin: str
    path: str
    http_status: int
    body: bytes = field(repr=False)
    received_at: datetime

    def __repr__(self):
        return "Response(<private body>)"


def _binding_json(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError("binding_type")


def prepare(config: Config, query: Query, request_ref: str, started_at: datetime) -> PreparedRequest:
    if type(config) is not Config:
        raise PreparationError("configuration_required")
    aware(started_at)
    identifier(request_ref)
    if type(query) not in (Search, Detail, RouteQuery):
        raise PreparationError("unsupported_query")
    # Revalidate objects on this public boundary; no unvalidated dict coercion.
    query.__post_init__()
    params = {"output": "JSON"}
    if type(query) is Search:
        path = "/v3/place/text"
        params.update(keywords=query.keyword, city=query.city, citylimit="true",
                      children="0", extensions="all", langCode="zh",
                      page=str(query.page), offset=str(query.page_size))
    elif type(query) is Detail:
        path = "/v3/place/detail"
        params.update(id=query.provider_id, langCode="zh")
    else:
        if query.departure.condition != "at_query_time":
            raise PreparationError("departure_not_supported")
        path = "/v3/direction/" + query.mode
        params.update(origin=query.origin.coordinate.raw, destination=query.destination.coordinate.raw)
        if query.mode == "walking":
            params.update(origin_id=query.origin.provider_id, destination_id=query.destination.provider_id)
        else:
            params.update(originid=query.origin.provider_id, destinationid=query.destination.provider_id,
                          strategy="10", extensions="base")
    pairs = tuple(sorted(params.items()))
    # Credential-free request size only. A future host must bound the final signed URL too.
    if len((config.origin + path + "?" + urlencode(pairs)).encode("ascii")) > config.max_request_bytes:
        raise PreparationError("request_too_large")
    canonical = json.dumps({"version": CONTRACT_VERSION, "query_type": type(query).__name__,
                            "query": asdict(query), "origin": config.origin, "path": path,
                            "params": pairs, "request_ref": request_ref,
                            "started_at": started_at, "limits": asdict(config)},
                           ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                           default=_binding_json).encode("utf-8")
    return PreparedRequest(query, config.origin, path, pairs, request_ref, started_at,
                           sha256(canonical).hexdigest())


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("non_json_number")


def _validate_unicode(value, depth=0):
    if depth > 32:
        raise ValueError("json_depth")
    if isinstance(value, str):
        # Reject unpaired surrogates even in unknown fields, without normalizing text.
        value.encode("utf-8", errors="strict")
    elif isinstance(value, dict):
        for key, child in value.items():
            _validate_unicode(key, depth + 1)
            _validate_unicode(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _validate_unicode(child, depth + 1)


def _decode(body):
    value = json.loads(body.decode("utf-8", errors="strict"), object_pairs_hook=_pairs,
                       parse_constant=_reject_constant, parse_float=Decimal)
    _validate_unicode(value)
    if type(value) is not dict:
        raise ValueError("json_object")
    return value


def _observed(item, key, parser):
    if key not in item:
        return Observed(FieldState.MISSING)
    value = item[key]
    if value is None:
        return Observed(FieldState.NULL)
    if type(value) is list and not value:
        return Observed(FieldState.EMPTY_ARRAY)
    if value == "":
        return Observed(FieldState.EMPTY_STRING)
    try:
        return Observed(FieldState.PRESENT, parser(value))
    except (ValueError, TypeError, UnicodeError):
        return Observed(FieldState.INVALID)


def _place(item):
    if type(item) is not dict:
        raise ValueError("poi_object")
    return Place(
        identifier(item.get("id")), text_value(item.get("name")),
        _observed(item, "address", text_value), _observed(item, "location", Coordinate),
        _observed(item, "entr_location", Coordinate), _observed(item, "exit_location", Coordinate),
        _observed(item, "parent", identifier), _observed(item, "navi_poiid", identifier),
        _observed(item, "typecode", text_value),
    )


def _count(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,10}", value):
        raise ValueError("count")
    return int(value)


def _quantity(value, unit):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,6})?", value):
        raise ValueError("quantity")
    return Quantity(value, Decimal(value), unit)


# Fixed documented codes, not matching arbitrary provider error prose.
_RATE_CODES = frozenset({"10003", "10004", "10010", "10014", "10015", "10019", "10020", "10021",
                         "10029", "10044", "10045"})


def parse_response(config: Config, request: PreparedRequest, response: Response,
                   *, now: datetime, evidence="unverified_bytes") -> Result:
    """Pure parsing. Binding checks are correlation checks, NOT authentication.

    The host associates exact original request with response; Gaode does not echo
    query identity or departure. No assertion of receipt/usage settlement is made.
    """
    if type(request) is not PreparedRequest:
        raise ValueError("prepared_request_required")
    expected = prepare(config, request.query, request.request_ref, request.started_at)
    if expected != request:
        return Result(Outcome.BINDING_MISMATCH, request.query, "request_changed")
    if evidence not in ("synthetic", "unverified_bytes"):
        raise ValueError("evidence_kind")
    if type(response) is not Response:
        return Result(Outcome.INVALID_RESPONSE, request.query, "response_envelope")
    if (response.binding_digest, response.origin, response.path) != (
        request.binding_digest, request.origin, request.path
    ):
        return Result(Outcome.BINDING_MISMATCH, request.query, "response_binding")
    try:
        aware(now)
        aware(response.received_at)
        # Same-tzinfo datetime arithmetic uses wall time across DST/fold.
        # Compare actual instants while retaining originals in binding/Source.
        started_instant = request.started_at.astimezone(timezone.utc)
        received_instant = response.received_at.astimezone(timezone.utc)
        now_instant = now.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return Result(Outcome.INVALID_RESPONSE, request.query, "response_time")
    source = Source(request.origin + request.path, request.started_at, response.received_at,
                    request.request_ref, request.binding_digest, evidence)

    def result(outcome, reason, **kwargs):
        return Result(outcome, request.query, reason, source, **kwargs)

    elapsed = (received_instant - started_instant).total_seconds()
    age = (now_instant - started_instant).total_seconds()
    if elapsed < 0 or now_instant < received_instant:
        return result(Outcome.INVALID_RESPONSE, "response_time")
    if elapsed > config.timeout_seconds:
        return result(Outcome.UNKNOWN, "response_deadline_exceeded")
    if age > config.max_age_seconds:
        return result(Outcome.STALE, "query_expired")
    if type(response.http_status) is not int or not 100 <= response.http_status <= 599:
        return result(Outcome.INVALID_RESPONSE, "http_status")
    if type(response.body) is not bytes or len(response.body) > config.max_response_bytes:
        return result(Outcome.INVALID_RESPONSE, "response_bytes_limit")
    if response.http_status == 429:
        return result(Outcome.RATE_LIMITED, "http_rate_limited")
    if response.http_status != 200:
        return result(Outcome.PROVIDER_ERROR, "http_failure")
    try:
        data = _decode(response.body)
        status, code = data.get("status"), data.get("infocode")
        if status not in ("0", "1") or not isinstance(code, str) or not re.fullmatch(r"[0-9]{5}", code):
            raise ValueError("provider_status")
        if status == "0":
            if code == "10000":
                raise ValueError("contradictory_status")
            return result(Outcome.RATE_LIMITED if code in _RATE_CODES else Outcome.PROVIDER_ERROR,
                          "provider_rejected", provider_code=code)
        if code != "10000" or data.get("info") != "OK":
            raise ValueError("contradictory_status")
        count = _count(data.get("count"))
        if type(request.query) in (Search, Detail):
            items = data.get("pois")
            if type(items) is not list:
                raise ValueError("pois_required")
            if len(items) > (request.query.page_size if type(request.query) is Search else 1):
                raise ValueError("poi_count_limit")
            if count < len(items) or (count == 0 and items):
                raise ValueError("count_inconsistent")
            if type(request.query) is Detail and count != len(items):
                raise ValueError("detail_count")
            places = tuple(_place(item) for item in items)
            if len({p.provider_id for p in places}) != len(places):
                raise ValueError("duplicate_poi_identity")
            if type(request.query) is Detail and any(p.provider_id != request.query.provider_id for p in places):
                return result(Outcome.BINDING_MISMATCH, "detail_identity")
            return result(Outcome.OK if places else Outcome.NO_RESULTS,
                          "page_results" if places else "empty_page", places=places,
                          provider_code=code, provider_count=count)
        route = data.get("route")
        if type(route) is not dict or type(route.get("paths")) is not list:
            raise ValueError("route_required")
        if not Coordinate(route.get("origin")).same_position(request.query.origin.coordinate) or not Coordinate(
            route.get("destination")
        ).same_position(request.query.destination.coordinate):
            return result(Outcome.BINDING_MISMATCH, "route_coordinates")
        paths = route["paths"]
        if count != len(paths):
            raise ValueError("route_count")
        routes = []
        for path in paths:
            if type(path) is not dict:
                raise ValueError("route_path")
            routes.append(Route(request.query, _observed(path, "distance", lambda v: _quantity(v, "m")),
                                _observed(path, "duration", lambda v: _quantity(v, "s"))))
        return result(Outcome.OK if routes else Outcome.NO_RESULTS,
                      "route_estimates" if routes else "no_routes", routes=tuple(routes),
                      provider_code=code, provider_count=count)
    except (ValueError, TypeError, UnicodeError, RecursionError, DecimalException):
        return result(Outcome.INVALID_RESPONSE, "invalid_provider_payload")


def execute(query: Query, *, config: Config | None = None) -> Result:
    """Production entry intentionally closed. No fake allow flag or network client."""
    return Result(Outcome.UNAVAILABLE, query, "configuration_required" if config is None
                  else "canonical_dispatch_not_connected")
