"""Formal PLACE/NEEDS input adapters for the one FEASIBILITY@1.0 engine.

Decoded data never conveys ownership, freshness, collection or publication
permission. Trusted hosts must retain original protected-reader/lease lifetimes.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import json

from cj_needs.contract_v1 import decode_snapshot, decode_revision
from cj_needs.domain import InvalidInput
from cj_place.contract_v1 import decode_result, decode_query, QUERY_VERSION
from cj_place import FieldState, Observed, Outcome, Quantity, Result, Route, RouteQuery, Source
from . import v1
from .routes import RouteAssessment, assess_route
from .validator import Report

INPUT_PROFILE = 'CJ-FEASIBILITY-FORMAL-INPUTS@1'


@dataclass(frozen=True, repr=False)
class FormalResult:
    operation: str
    report: Report | RouteAssessment
    place_original: bytes | None = field(default=None, repr=False)
    version: str = field(default=v1.VERSION, init=False)
    input_profile: str = field(default=INPUT_PROFILE, init=False)

    @property
    def status(self):
        return self.report.status


def _inputs(snapshot_raw, revision_raws, *, max_revisions, max_input_bytes):
    """Explicit host bounds; enforce before decoding an unbounded history chain."""
    if (type(max_revisions) is not int or max_revisions < 1
            or type(max_input_bytes) is not int or max_input_bytes < 1):
        raise ValueError('positive fixed host input bounds required')
    if (type(snapshot_raw) is not bytes or type(revision_raws) is not tuple
            or not 1 <= len(revision_raws) <= max_revisions
            or any(type(raw) is not bytes for raw in revision_raws)):
        raise InvalidInput('bounded original NEEDS envelopes required')
    if len(snapshot_raw) + sum(map(len, revision_raws)) > max_input_bytes:
        raise InvalidInput('NEEDS envelope input bound exceeded')
    snapshot = decode_snapshot(snapshot_raw)
    if snapshot.version != len(revision_raws):
        raise InvalidInput('complete original NEEDS revision chain required')
    revisions = tuple(decode_revision(raw) for raw in revision_raws)
    # Existing FEAS alone replays retained fields, ordering, final exact bytes and
    # original action provenance. No second history/constraint implementation.
    return snapshot, revisions


def check_constraints(snapshot_raw, revision_raws, *, max_revisions, max_input_bytes):
    snapshot, revisions = _inputs(snapshot_raw, revision_raws,
        max_revisions=max_revisions, max_input_bytes=max_input_bytes)
    return FormalResult('check', v1.check_constraints(snapshot, revisions).report)


def check_edit_scope(snapshot_raw, revision_raws, candidate, *, selected_fields,
                     selected_item_ids, max_revisions, max_input_bytes):
    snapshot, revisions = _inputs(snapshot_raw, revision_raws,
        max_revisions=max_revisions, max_input_bytes=max_input_bytes)
    return FormalResult('protect', v1.check_edit_scope(snapshot, revisions, candidate,
        selected_fields=selected_fields, selected_item_ids=selected_item_ids).report)


def check_route(snapshot_raw, revision_raws, candidate, window, result_raw, *,
                route_index, request, config, as_of, selected_fields,
                selected_item_ids, max_revisions, max_input_bytes):
    snapshot, revisions = _inputs(snapshot_raw, revision_raws,
        max_revisions=max_revisions, max_input_bytes=max_input_bytes)
    result = _route_result(result_raw)
    return FormalResult('route', assess_route(snapshot, revisions, candidate, window, result,
        route_index=route_index, request=request, config=config, as_of=as_of,
        selected_fields=selected_fields, selected_item_ids=selected_item_ids), result_raw)


def _route_result(raw):
    """Bridge validated formal data into the existing conditional-only checker.

    The old internal Source supports synthetic/unverified only. Other formal
    evidence labels are conservatively unverified in that checker; exact frozen
    labels/recording refs/offsets remain in FormalResult.place_original. This
    bridge ends when the checker consumes formal wire directly; it grants no
    dispatch/owner/freshness and never upgrades evidence.
    """
    value = decode_result(raw)
    query = decode_query(json.dumps(dict(version=QUERY_VERSION, query=value['query']),
        ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode())
    if type(query) is not RouteQuery: raise ValueError('explicit formal route query required')
    def quantity(observed):
        state = FieldState(observed['state'])
        if state is not FieldState.PRESENT: return Observed(state)
        item = observed['value']
        return Observed(state, Quantity(item['raw'], Decimal(item['value']), item['unit']))
    routes = tuple(Route(query, quantity(route['distance']), quantity(route['duration']))
                   for route in value['routes'])
    original = value['source']
    source = None
    if original is not None:
        def instant(value):
            return datetime.fromisoformat(value['iso8601']).replace(fold=value['fold'])
        source = Source(original['endpoint'], instant(original['query_started_at']),
            instant(original['received_at']), original['request_ref'], original['binding_digest'],
            'synthetic' if original['evidence_kind']=='synthetic' else 'unverified_bytes')
    return Result(Outcome(value['outcome']), query, value['reason'], source=source,
                  routes=routes, provider_code=value['provider_code'], provider_count=value['provider_count'])
