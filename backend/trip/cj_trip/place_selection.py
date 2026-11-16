"""Deterministic selection from a complete registered provider capture.

This data codec is not capture, collection or publication authority. The live
draft component obtains originals under their actual holder; historical v2
readers only validate retained bytes. No provider outcome is relabelled.
"""
from hashlib import sha256

from cj_place.models import identifier as provider_id
from .domain import identifier, packed
from .rich_source import digest, source_ref
from .structured import SourceRejected, _fields, _text

VERSION = 'LIO-place-selection.1'
SOURCE = 'TRIP-RICH-PLACE-SELECTION-SOURCE.1'
PLAN_SOURCE = 'TRIP-RICH-PLAN-SOURCE.2'
POI_REGISTRATION = 'tool.lio_poi2.1'
ROUTE_REGISTRATION = 'tool.lio_route.1'


def selections(outcomes, records):
    """One result per original target, from same-operation eligible places.

    Zero exact usable observations permits an explicit selection fallback.
    Multiple exact identities remain ambiguous, never a first-result choice or
    an unavailable claim. Inputs must be the complete registered capture, not a
    caller/model-selected subset. Equality here grants no source permission.
    """
    if type(outcomes) is not list or type(records) is not list or max(len(outcomes), len(records)) > 256:
        raise SourceRejected('selection', 'complete bounded provider capture required')
    operations = {}
    targets = set()
    for outcome in outcomes:
        _fields(outcome, {'version', 'attempt_id', 'operation_id', 'registration', 'input_sha256',
                         'reply_sha256', 'request_ref', 'status', 'item_count', 'targets', 'query_type', 'query'},
                'selection.outcome', 'complete registered provider outcome required')
        if (outcome['version'] != 'LIO-provider-outcome.1'
                or outcome['registration'] not in (POI_REGISTRATION, ROUTE_REGISTRATION)):
            raise SourceRejected('selection.outcome', 'known original provider registration required')
        for key in ('operation_id', 'attempt_id', 'request_ref'):
            identifier(outcome[key])
        for key in ('input_sha256', 'reply_sha256'):
            digest(outcome[key])
        if outcome['operation_id'] in operations:
            raise SourceRejected('selection.operation', 'distinct original operation required')
        operations[outcome['operation_id']] = (outcome, [])
        if (outcome['status'] not in ('ok', 'unavailable') or type(outcome['item_count']) is not int
                or not 0 <= outcome['item_count'] <= 25
                or outcome['status'] == 'unavailable' and outcome['item_count'] != 0):
            raise SourceRejected('selection.outcome', 'actual terminal provider status/count required')
        if outcome['registration'] == ROUTE_REGISTRATION:
            continue  # A route outcome never authorizes an unconfirmed place.
        query = outcome['query']
        query_fields = {'keyword', 'region', 'page_size'}
        if outcome['query_type'] == 'Nearby':
            query_fields |= {'center', 'radius_m'}
        elif outcome['query_type'] != 'TextSearch':
            raise SourceRejected('selection.query', 'explicit keyword query required; no detail/name inference')
        _fields(query, query_fields, 'selection.query', 'original keyword query required')
        _text(query['keyword'], 320)
        selected = outcome['targets']
        if (type(selected) is not list or not 1 <= len(selected) <= 60
                or any(type(target) is not str for target in selected)
                or len(set(selected)) != len(selected)):
            raise SourceRejected('selection.targets', 'nonempty distinct code-owned targets required')
        for target in selected:
            identifier(target)
            if target in targets:
                raise SourceRejected('selection.targets', 'one original keyword operation per target required')
            targets.add(target)
    seen = set()
    for record in records:
        _fields(record, {'provider', 'kind', 'reference', 'sha256', 'payload'},
                'selection.records', 'complete eligible record required')
        ref = {key: record[key] for key in ('provider', 'kind', 'reference', 'sha256')}
        source_ref(ref)
        if type(record['payload']) is not dict or sha256(packed(record['payload'])).hexdigest() != record['sha256']:
            raise SourceRejected('selection.records', 'original eligible projection digest differs')
        if packed(ref) in seen:
            raise SourceRejected('selection.records', 'distinct eligible record required')
        seen.add(packed(ref))
        if (record['provider'], record['kind']) == ('amap', 'route'):
            if sum(outcome['registration'] == ROUTE_REGISTRATION and record['reference'] == operation_id+':route'
                   for operation_id, (outcome, _) in operations.items()) != 1:
                raise SourceRejected('selection.records', 'route must belong to its exact original operation')
            continue
        if (record['provider'], record['kind']) != ('amap', 'place'):
            raise SourceRejected('selection.records', 'only registered original place/route projections required')
        payload = record['payload']
        if not {'amap_id', 'name_zh'} <= payload.keys():
            raise SourceRejected('selection.records', 'original place identity fields required')
        provider_id(payload['amap_id'])
        _text(payload['name_zh'], 500)
        matches = [entry for operation_id, entry in operations.items()
                   if entry[0]['registration'] == POI_REGISTRATION
                   and record['reference'] == operation_id+':poi:'+payload['amap_id']]
        if len(matches) != 1:
            raise SourceRejected('selection.records', 'place must belong to its exact original POI operation')
        matches[0][1].append(record)
    result = []
    for outcome, eligible in operations.values():
        if outcome['registration'] != POI_REGISTRATION:
            continue
        if len(eligible) > outcome['item_count']:
            raise SourceRejected('selection.records', 'eligible set exceeds the original complete page')
        exact = [record for record in eligible if record['payload']['name_zh'] == outcome['query']['keyword']]
        if outcome['status'] == 'unavailable':
            status, reason = 'unavailable', 'provider_unavailable'
        elif outcome['item_count'] == 0:
            status, reason = 'unavailable', 'empty_page'
        elif not exact:
            status, reason = 'unavailable', 'no_exact_eligible_place'
        elif len(exact) > 1:
            status, reason = 'ambiguous', 'multiple_exact_places'
        else:
            status, reason = 'matched', 'unique_exact_place'
        for target in outcome['targets']:
            result.append(dict(version=VERSION, target=target, operation_id=outcome['operation_id'],
                query_keyword=outcome['query']['keyword'],
                provider_outcome_sha256=sha256(packed(outcome)).hexdigest(),
                eligible_refs=[{key: record[key] for key in ('provider', 'kind', 'reference', 'sha256')}
                               for record in eligible],
                status=status, reason=reason, selected_record=exact[0] if status == 'matched' else None))
    return result


def validate_basis(value):
    """Validate new persisted selection data; never reconstruct live authority."""
    if (value.get('version') != PLAN_SOURCE or value.get('place_selection_version') != VERSION
            or packed(value.get('place_selections')) != packed(selections(value['provider_outcomes'], value['provider_records']))):
        raise SourceRejected('selection.basis', 'retained selection differs from complete original provider capture')
