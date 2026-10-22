"""Fixed PLACE evidence consumption; conditional estimates never prove reality."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Context, Decimal, localcontext
import re

from cj_place import (CONTRACT_VERSION, Config, FieldState, Observed, Outcome,
                      PreparationError, PreparedRequest, Quantity, Result, Route,
                      RouteQuery, Source, prepare)
from cj_needs.domain import InvalidInput, decode, validate_fields
from .validator import Candidate, Check, Report, _evidence, _instant, protect

PLACE_COMMIT = 'dd4c375a731bbaef1d436bc3e88466040ac02294'
VERSION = 'CJ-FEASIBILITY-ROUTE-ESTIMATE@0.1.0-candidate.1'


@dataclass(frozen=True, repr=False)
class Window:
    """Explicit candidate item-end -> item-start selection, not an inferred place.

    query retains actual PLACE Endpoint identity/role/coordinate/mode/departure.
    Buffer and rest are explicit declarations in PLACE Observed[Quantity] seconds;
    only an explicitly supplied zero permits zero. No model/default supplies them.
    """
    origin_item_id: str
    destination_item_id: str
    query: RouteQuery
    buffer: Observed[Quantity]
    rest: Observed[Quantity]


@dataclass(frozen=True, repr=False)
class RouteAssessment:
    status: str
    conditional_relation: str | None
    checks: tuple[Check, ...]
    protection: Report
    candidate: Candidate
    window: Window
    result: Result
    request: PreparedRequest
    config: Config  # includes the explicit freshness policy bound by PLACE
    as_of: datetime
    route_index: int
    version: str = VERSION


def _seconds(delta):
    # Called only inside an independent exact decimal context; no total_seconds float.
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / Decimal(1000000)


def _quantity(observed):
    if type(observed) is not Observed or observed.state is not FieldState.PRESENT:
        return None
    q = observed.value
    if (type(q) is not Quantity or q.unit != 's' or type(q.value) is not Decimal
            or type(q.raw) is not str or re.fullmatch(r'[0-9]{1,12}(?:\.[0-9]{1,6})?', q.raw) is None
            or not q.value.is_finite() or q.value < 0 or Decimal(q.raw) != q.value):
        return None
    return q.value


def _aware(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidInput('aware explicit time required')
    return value.astimezone(timezone.utc)


def assess_route(before, revisions, candidate: Candidate, window: Window, result: Result, *,
                 route_index: int, request: PreparedRequest, config: Config, as_of: datetime,
                 selected_fields: frozenset[str], selected_item_ids: frozenset[str]) -> RouteAssessment:
    """Read-only pre-write guard + exact conditional time-window arithmetic.

    This fixed PLACE version has no verified transport evidence category. Thus
    even well-bound fresh values yield UNKNOWN with a conditional relation, never
    a real-world PASS/CONFLICT. No approval/freshness boolean overrides that fact.
    """
    protection = protect(before, revisions, candidate, selected_fields=selected_fields,
                         selected_item_ids=selected_item_ids)
    checks = list(protection.checks)
    relation = None

    def add(code, status, missing, zh, en, *, evidence=(), details=()):
        checks.append(Check(code, status, evidence, tuple(missing), zh, en, tuple(details)))

    def finish():
        status = ('INVALID' if any(c.status == 'INVALID' for c in checks) else
                  'CONFLICT' if any(c.status == 'CONFLICT' for c in checks) else 'UNKNOWN')
        return RouteAssessment(status, relation, tuple(checks), protection, candidate,
                               window, result, request, config, as_of, route_index)

    if not any(c.code == 'PROTECTED_SCOPE_UNCHANGED' and c.status == 'PASS' for c in protection.checks):
        add('ROUTE_PROTECTION_WITHHELD', 'UNKNOWN', ('protected_candidate',),
            '候选保护未通过，不能采用路线计算放行候选。',
            'Candidate protection did not pass; route arithmetic cannot release it.')
        return finish()
    try:
        if (type(window) is not Window or type(window.query) is not RouteQuery
                or type(result) is not Result or type(config) is not Config
                or type(request) is not PreparedRequest or type(route_index) is not int):
            raise InvalidInput('explicit PLACE objects and integer route index required')
        now = _aware(as_of)
        if window.origin_item_id == window.destination_item_id:
            raise InvalidInput('distinct explicit item IDs required')
        fields = decode(candidate.content)
        validate_fields(fields, complete=True)
        items = fields.get('fixed_items', [])
        positions = {item['item_id']: i for i, item in enumerate(items)}
        if (window.origin_item_id not in positions or window.destination_item_id not in positions):
            raise InvalidInput('candidate item unavailable')
        ai, bi = positions[window.origin_item_id], positions[window.destination_item_id]
        a, b = items[ai], items[bi]
        add('ROUTE_ENDPOINT_MAPPING_DECLARED', 'UNKNOWN', ('confirmed_candidate_endpoint_mapping',),
            '事项到PLACE起终点的关联由本次显式输入声明；不能由NEEDS地点文字反推或冒称已验证。',
            'Item-to-PLACE endpoint mapping is explicitly supplied, not inferred from NEEDS place text or independently verified.',
            details=(('origin_item_id', window.origin_item_id), ('destination_item_id', window.destination_item_id)))
        a_end, am, ar = _instant(a['end'], f'fixed_items.{ai}.end')
        b_start, bm, br = _instant(b['start'], f'fixed_items.{bi}.start')
        evidence = _evidence(fields, {}, f'fixed_items.{ai}', f'fixed_items.{bi}')
        if a_end is None or b_start is None:
            add('ROUTE_WINDOW_TIME_UNKNOWN', 'UNKNOWN', am + bm,
                '候选起终时刻未确定，不能补造窗口。', 'Candidate window instants unresolved; no invented window.',
                evidence=evidence, details=(('origin_end', ar), ('destination_start', br)))
            return finish()
        sa, sb = set(a['applies_to']), set(b['applies_to'])
        if not (sa & sb or 'party' in sa or 'party' in sb):
            add('ROUTE_SUBJECT_UNPROVEN', 'UNKNOWN', ('same_applicable_subject',),
                '两事项没有明确相同适用人，不能强加移动约束。',
                'Items have no explicit shared subject; a travel constraint cannot be imposed.', evidence=evidence)
            return finish()
        if any(item['booking_status'].get('state') != 'known'
               or item['booking_status'].get('value') == 'cancelled' for item in (a, b)):
            add('ROUTE_ITEM_ACTIVITY_UNKNOWN', 'UNKNOWN', ('active_item_declarations',),
                '事项已取消或状态未知，移动约束的适用性未确定。',
                'Cancelled or unresolved item status leaves travel applicability unknown.', evidence=evidence)
            return finish()
        if window.query.departure.condition != 'at_query_time':
            add('ROUTE_DEPARTURE_UNSUPPORTED', 'UNKNOWN', ('supported_departure_evidence',),
                '固定PLACE不支持指定出发时刻查询。', 'Pinned PLACE does not support specified-time departure queries.')
            return finish()
        expected = prepare(config, window.query, request.request_ref, request.started_at)
        if expected != request or result.query != window.query or result.contract_version != CONTRACT_VERSION:
            add('ROUTE_QUERY_BINDING_UNKNOWN', 'UNKNOWN', ('exact_original_query_binding',),
                '原请求、候选起终点或契约版本不匹配。',
                'Original request, candidate endpoints or contract version does not match.')
            return finish()
        if result.outcome is not Outcome.OK:
            add('ROUTE_RESULT_UNAVAILABLE', 'UNKNOWN', ('successful_route_result',),
                '路线结果不可用，不能替换为零时长。', 'Route result unavailable; duration cannot become zero.',
                details=(('outcome', str(result.outcome)),))
            return finish()
        source = result.source
        if type(source) is not Source:
            add('ROUTE_SOURCE_MISSING', 'UNKNOWN', ('result.source',),
                '原Result.source缺失。', 'Original Result.source is missing.')
            return finish()
        if (source.provider != 'gaode' or source.api_version != 'v3'
                or source.endpoint != request.origin + request.path
                or source.request_ref != request.request_ref or source.binding_digest != request.binding_digest
                or _aware(source.query_started_at) != _aware(request.started_at)
                or source.provider_updated_at is not None):
            add('ROUTE_SOURCE_BINDING_UNKNOWN', 'UNKNOWN', ('original_source_binding',),
                '来源与原请求绑定不一致，不能采用时长。', 'Source does not match the original request; duration withheld.')
            return finish()
        started, received = _aware(source.query_started_at), _aware(source.received_at)
        if not started <= received <= now:
            add('ROUTE_SOURCE_TIME_UNKNOWN', 'UNKNOWN', ('ordered_source_timestamps',),
                '查询、接收与检查时点顺序不成立。', 'Query, receipt and assessment timestamps are not ordered.')
            return finish()
        with localcontext(Context(prec=40)):
            age = _seconds(now - started)
            max_age = Decimal(config.max_age_seconds) if type(config.max_age_seconds) is int else Decimal.from_float(config.max_age_seconds)
        details = (('query_age_seconds', format(age, 'f')), ('max_age_seconds', format(max_age, 'f')),
                   ('request_ref', source.request_ref), ('binding_digest', source.binding_digest),
                   ('evidence', source.evidence))
        if age > max_age:
            add('ROUTE_SOURCE_STALE', 'UNKNOWN', ('fresh_route_evidence',),
                '来源超过显式最大查询年龄；不代表供应商更新时间。',
                'Source exceeds explicit maximum query age; this is not a provider update timestamp.', details=details)
            return finish()
        add('ROUTE_QUERY_AGE_CHECKED', 'PASS', (),
            '原查询年龄在显式策略内；不证明供应商数据新鲜或真实。',
            'Original query age meets explicit policy; this proves neither provider data freshness nor authenticity.', details=details)
        # This pinned Source can only label fixtures or unverified bytes. Never add
        # a caller "trusted" flag, reinterpret those categories or permit promotion.
        add('ROUTE_EVIDENCE_UNVERIFIED', 'UNKNOWN', ('verified_transport_evidence',),
            '固定PLACE只有合成或未验证来源；条件算术不是真实行程结论。',
            'Pinned PLACE provides synthetic or unverified evidence only; conditional arithmetic is not a real trip verdict.',
            details=(('evidence', str(source.evidence)),))
        if source.evidence not in ('synthetic', 'unverified_bytes'):
            add('ROUTE_EVIDENCE_CATEGORY_INVALID', 'INVALID', ('fixed_place_evidence_category',),
                '不能通过伪造来源类别获得可信结论。', 'Invented evidence categories cannot establish trust.')
            return finish()
        if a_end != started:
            add('ROUTE_FUTURE_APPLICABILITY_UNKNOWN', 'UNKNOWN', ('route_for_candidate_departure',),
                '候选离开时刻不同于原查询时刻，不能外推估计到过去或未来。',
                'Candidate departure differs from original query time; estimate cannot be extrapolated to past or future.',
                evidence=evidence)
            return finish()
        if type(result.routes) is not tuple or not 0 <= route_index < len(result.routes):
            add('ROUTE_SELECTION_UNKNOWN', 'UNKNOWN', ('explicit_available_route_index',),
                '选中路线不存在，不自动选第一条。', 'Selected route unavailable; first route is not chosen automatically.')
            return finish()
        route = result.routes[route_index]
        if (type(route) is not Route or route.query != window.query
                or route.time_semantics != 'provider_estimate_at_query_time' or route.future_guaranteed is not False):
            add('ROUTE_VALUE_BINDING_UNKNOWN', 'UNKNOWN', ('bound_query_time_estimate',),
                '路线条目绑定或估计时间语义不匹配。', 'Route entry binding or estimate time semantics do not match.')
            return finish()
        values = (_quantity(route.duration), _quantity(window.buffer), _quantity(window.rest))
        missing = tuple(name for name, value in zip(('route.duration', 'explicit_buffer', 'explicit_rest'), values) if value is None)
        if missing:
            add('ROUTE_REQUIRED_SECONDS_UNKNOWN', 'UNKNOWN', missing,
                '时长、缓冲或休息未明确为有效秒数；不能补零。',
                'Duration, buffer or rest is not an explicit valid seconds quantity; no zero fill.')
            return finish()
        with localcontext(Context(prec=40)):
            required = sum(values, Decimal(0))
            gap = _seconds(b_start - a_end)
            relation = 'required_exceeds_gap' if required > gap else 'required_within_gap'
        add('ROUTE_CONDITIONAL_WINDOW', 'UNKNOWN', ('verified_applicable_route_evidence',),
            '仅在所给查询时估计成立的假设下比较移动、显式缓冲与休息；不是真实可行性结论。',
            'Compare travel, explicit buffer and rest conditional on the supplied query-time estimate; no real feasibility verdict.',
            evidence=evidence, details=(('relation', relation), ('duration_seconds', format(values[0], 'f')),
                                       ('buffer_seconds', format(values[1], 'f')), ('rest_seconds', format(values[2], 'f')),
                                       ('required_seconds', format(required, 'f')), ('gap_seconds', format(gap, 'f'))))
    except (InvalidInput, PreparationError, TypeError, ValueError, OverflowError, AttributeError):
        # Expose a stable local code, never raw provider/private exception content.
        add('ROUTE_INPUT_INVALID', 'INVALID', ('valid_explicit_route_input',),
            '路线输入对象或时间结构无效。', 'Invalid route input objects or timestamp structure.')
    return finish()
