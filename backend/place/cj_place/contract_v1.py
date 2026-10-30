"""PLACE@1.0 strict data codec. Data is never AUTH, freshness or dispatch authority.

Reuses the one Gaode model/parser. Legacy versions and projections stay intact.
"""
from datetime import datetime,timezone
import json
import re

from .gaode import _quantity,parse_response
from .models import (CONTRACT_VERSION, Coordinate, Departure, Detail, Endpoint, FieldState,
                     Observed, Outcome, Place, Result, Route, RouteQuery, Search, Source,
                     aware, identifier, text_value)

VERSION = 'PLACE@1.0'
QUERY_VERSION = 'PLACE-query.1'
RESULT_VERSION = 'PLACE-result.1'


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys.split()):
        raise ValueError('unexpected_or_missing_fields')
    return value


def _json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('duplicate_field')
            value[key] = item
        return value
    def constant(value):
        raise ValueError('non_json_number')
    if type(raw) is not bytes or len(raw) > 1048576:
        raise ValueError('bounded_original_bytes_required')
    try:
        return json.loads(raw.decode('utf8'), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError,UnicodeError,RecursionError):
        raise ValueError('invalid_place_json') from None


def _time(value):
    if value is None:
        return None
    return dict(iso8601=value.isoformat(timespec='microseconds'), fold=value.fold)


def _read_time(value):
    _exact(value, 'iso8601 fold')
    if type(value['iso8601']) is not str or type(value['fold']) is not int or value['fold'] not in (0,1):
        raise ValueError('aware_time_required')
    result = aware(datetime.fromisoformat(value['iso8601'])).replace(fold=value['fold'])
    if _time(result) != value:
        raise ValueError('noncanonical_lossless_time')
    return result


def _coordinate(value):
    return dict(raw=value.raw, longitude=str(value.longitude), latitude=str(value.latitude), crs=value.crs)


def _read_coordinate(value):
    _exact(value, 'raw longitude latitude crs')
    result = Coordinate(value['raw'])
    if _coordinate(result) != value:
        raise ValueError('coordinate_association')
    return result


def _endpoint(value):
    return dict(provider_id=value.provider_id, coordinate=_coordinate(value.coordinate), coordinate_role=value.coordinate_role)


def _read_endpoint(value):
    _exact(value, 'provider_id coordinate coordinate_role')
    return Endpoint(value['provider_id'], _read_coordinate(value['coordinate']), value['coordinate_role'])


def query_value(query):
    if type(query) is Search:
        return dict(kind='Search', keyword=query.keyword, city=query.city, page=query.page, page_size=query.page_size)
    if type(query) is Detail:
        return dict(kind='Detail', provider_id=query.provider_id)
    return dict(kind='RouteQuery', origin=_endpoint(query.origin), destination=_endpoint(query.destination),
                mode=query.mode, departure=dict(condition=query.departure.condition, at=_time(query.departure.at)))


def _read_query(value):
    if type(value) is not dict:
        raise ValueError('query_object_required')
    if value.get('kind') == 'Search':
        _exact(value, 'kind keyword city page page_size')
        return Search(value['keyword'], value['city'], value['page'], value['page_size'])
    if value.get('kind') == 'Detail':
        _exact(value, 'kind provider_id')
        return Detail(value['provider_id'])
    _exact(value, 'kind origin destination mode departure')
    if value['kind'] != 'RouteQuery':
        raise ValueError('unsupported_query_kind')
    departure = _exact(value['departure'], 'condition at')
    return RouteQuery(_read_endpoint(value['origin']), _read_endpoint(value['destination']), value['mode'],
                      Departure(departure['condition'], None if departure['at'] is None else _read_time(departure['at'])))


def encode_query(query):
    return json.dumps(dict(version=QUERY_VERSION, query=query_value(query)), ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf8')


def decode_query(raw):
    value = _exact(_json(raw), 'version query')
    if value['version'] != QUERY_VERSION:
        raise ValueError('unsupported_query_version')
    return _read_query(value['query'])


def _observed(value, encode=lambda item:item):
    return dict(state=value.state.value, value=encode(value.value) if value.state is FieldState.PRESENT else None)


def _read_observed(value, decode):
    _exact(value, 'state value')
    state = FieldState(value['state'])
    if state is FieldState.PRESENT:
        return Observed(state, decode(value['value']))
    if value['value'] is not None:
        raise ValueError('nonpresent_value')
    return Observed(state)


def _place(value):
    return dict(provider=value.provider, provider_id=value.provider_id, name_zh=value.name_zh,
        address_zh=_observed(value.address_zh), coordinate=_observed(value.coordinate, _coordinate),
        entrance_coordinate=_observed(value.entrance_coordinate, _coordinate),
        exit_coordinate=_observed(value.exit_coordinate, _coordinate), parent_id=_observed(value.parent_id),
        navigation_id=_observed(value.navigation_id), typecode=_observed(value.typecode),
        official_name_en=_observed(value.official_name_en), official_address_en=_observed(value.official_address_en))


def _read_place(value):
    _exact(value, 'provider provider_id name_zh address_zh coordinate entrance_coordinate exit_coordinate parent_id navigation_id typecode official_name_en official_address_en')
    if value['provider'] != 'gaode':
        raise ValueError('unsupported_provider')
    return Place(identifier(value['provider_id']), text_value(value['name_zh']),
        _read_observed(value['address_zh'], text_value), _read_observed(value['coordinate'], _read_coordinate),
        _read_observed(value['entrance_coordinate'], _read_coordinate), _read_observed(value['exit_coordinate'], _read_coordinate),
        _read_observed(value['parent_id'], identifier), _read_observed(value['navigation_id'], identifier),
        _read_observed(value['typecode'], text_value), _read_observed(value['official_name_en'], text_value),
        _read_observed(value['official_address_en'], text_value))


def _quantity_value(value):
    return dict(raw=value.raw, value=str(value.value), unit=value.unit)


def _read_quantity(value, unit):
    _exact(value, 'raw value unit')
    result = _quantity(value['raw'], unit)
    if _quantity_value(result) != value:
        raise ValueError('quantity_association')
    return result


def _route(value):
    return dict(query=query_value(value.query), distance=_observed(value.distance,_quantity_value),
                duration=_observed(value.duration,_quantity_value), time_semantics=value.time_semantics,
                future_guaranteed=value.future_guaranteed)


def _read_route(value, query):
    _exact(value, 'query distance duration time_semantics future_guaranteed')
    if (type(query) is not RouteQuery or value['query'] != query_value(query)
            or value['time_semantics'] != 'provider_estimate_at_query_time' or value['future_guaranteed'] is not False):
        raise ValueError('route_query_association')
    return Route(query, _read_observed(value['distance'], lambda v:_read_quantity(v,'m')),
                 _read_observed(value['duration'], lambda v:_read_quantity(v,'s')))


def encode_result(result, *, evidence_kind, recording_ref=None):
    """Trusted host projection only. Caller labels/data never create provider authority."""
    if evidence_kind not in ('synthetic','recorded_replay','live_provider','unverified_bytes'):
        raise ValueError('evidence_kind')
    if (recording_ref is not None) != (evidence_kind == 'recorded_replay'):
        raise ValueError('recording_reference')
    source = result.source
    if source is not None and source.evidence=='synthetic' and evidence_kind!='synthetic':
        raise ValueError('synthetic_evidence_cannot_be_promoted')
    data = None if source is None else dict(endpoint=source.endpoint, provider=source.provider,
        api_version=source.api_version, adapter_profile=result.contract_version,
        request_ref=source.request_ref, binding_digest=source.binding_digest,
        query_started_at=_time(source.query_started_at), received_at=_time(source.received_at),
        provider_updated_at=None, evidence_kind=evidence_kind, recording_ref=recording_ref)
    value = dict(version=RESULT_VERSION, query=query_value(result.query), outcome=result.outcome.value,
        reason=result.reason, source=data, places=[_place(p) for p in result.places],
        routes=[_route(r) for r in result.routes], provider_code=result.provider_code, provider_count=result.provider_count)
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')


def decode_result(raw):
    """Strict consumer data check, with no adoption/freshness/AUTH grant."""
    value = _exact(_json(raw), 'version query outcome reason source places routes provider_code provider_count')
    if value['version'] != RESULT_VERSION:
        raise ValueError('unsupported_result_version')
    query, outcome = _read_query(value['query']), Outcome(value['outcome'])
    if type(value['reason']) is not str or re.fullmatch('[a-z0-9_]{1,96}', value['reason']) is None:
        raise ValueError('reason_code')
    if value['provider_code'] is not None and (type(value['provider_code']) is not str
            or re.fullmatch('[0-9]{1,16}', value['provider_code']) is None):
        raise ValueError('provider_code')
    if value['provider_count'] is not None and (type(value['provider_count']) is not int or value['provider_count'] < 0):
        raise ValueError('provider_count')
    if value['provider_count'] is not None and value['provider_count']>9999999999:
        raise ValueError('provider_count')
    if type(value['places']) is not list or type(value['routes']) is not list:
        raise ValueError('result_arrays')
    places=tuple(_read_place(p) for p in value['places'])
    routes=tuple(_read_route(r,query) for r in value['routes'])
    if (places and type(query) is RouteQuery) or (routes and type(query) is not RouteQuery):
        raise ValueError('result_query_kind')
    if outcome is not Outcome.OK and (places or routes):
        raise ValueError('failure_has_no_usable_results')
    if outcome is Outcome.OK and not places and not routes:
        raise ValueError('empty_success')
    if len({p.provider_id for p in places})!=len(places):
        raise ValueError('duplicate_place_identity')
    if type(query) is Detail and (len(places)>1 or any(p.provider_id!=query.provider_id for p in places)):
        raise ValueError('detail_identity')
    if type(query) is Search and len(places)>query.page_size:
        raise ValueError('page_size')
    if value['provider_count'] is not None:
        if value['provider_count']<len(places) or (routes and value['provider_count']!=len(routes)):
            raise ValueError('result_count_association')
    source=value['source']
    if source is not None:
        _exact(source, 'endpoint provider api_version adapter_profile request_ref binding_digest query_started_at received_at provider_updated_at evidence_kind recording_ref')
        paths = {'Search':'/v3/place/text','Detail':'/v3/place/detail'}
        path = '/v3/direction/'+query.mode if type(query) is RouteQuery else paths[type(query).__name__]
        if (source['endpoint'] != 'https://restapi.amap.com'+path or source['provider'] != 'gaode'
                or source['api_version'] != 'v3' or source['adapter_profile'] != CONTRACT_VERSION
                or source['provider_updated_at'] is not None):
            raise ValueError('source_profile')
        identifier(source['request_ref'])
        if type(source['binding_digest']) is not str or re.fullmatch('[0-9a-f]{64}',source['binding_digest']) is None:
            raise ValueError('source_binding')
        started=_read_time(source['query_started_at']);received=_read_time(source['received_at'])
        if outcome is Outcome.OK and received.astimezone(timezone.utc)<started.astimezone(timezone.utc):
            raise ValueError('source_chronology')
        if outcome is Outcome.OK and type(query) is RouteQuery and query.departure.condition!='at_query_time':
            raise ValueError('unsupported_departure_has_no_success')
        if source['evidence_kind'] not in ('synthetic','recorded_replay','live_provider','unverified_bytes'):
            raise ValueError('evidence_kind')
        if source['evidence_kind']=='recorded_replay':
            text_value(source['recording_ref'],1024)
        elif source['recording_ref'] is not None:
            raise ValueError('recording_reference')
    elif places or routes or outcome is Outcome.NO_RESULTS:
        raise ValueError('usable_result_requires_source')
    return value


def publish_response(config,request,response,*,now,evidence_kind,recording_ref=None):
    """One existing parser followed by the fixed versioned data projection.

    No dispatch, credentials, retries or execution permission is provided here.
    Actual registered business invocation is owned by #265.
    """
    result=parse_response(config,request,response,now=now,
        evidence='synthetic' if evidence_kind=='synthetic' else 'unverified_bytes')
    return encode_result(result,evidence_kind=evidence_kind,recording_ref=recording_ref)
