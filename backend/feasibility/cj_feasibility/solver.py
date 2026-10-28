"""Bounded CP-SAT scheduling of explicit NEEDS candidates, never real feasibility.

The separate output checker uses original objects and public protection/route
checks, not CP-SAT variables or its status. No IO or domain writes in this module.
"""
from dataclasses import dataclass
from datetime import datetime
from threading import Event

# Process initialization, outside every request budget. Import errors must escape
# startup rather than being converted to a solver UNKNOWN result (#176).
from ortools.sat.python import cp_model

from cj_needs.domain import Revision, Snapshot
from .validator import Candidate
from .routes import RouteAssessment

VERSION = 'CJ-FEASIBILITY-BOUNDED@0.1.0-candidate.1'


@dataclass(frozen=True)
class StartWindow:
    """Explicit inclusive start bounds as aware instants, not inferred wall dates."""
    item_id: str
    earliest: datetime
    latest: datetime


@dataclass(frozen=True)
class Limits:
    epoch: datetime
    horizon_seconds: int
    ticks_per_second: int
    max_abs_ticks: int
    max_items: int
    max_edges: int
    max_revisions: int
    max_solve_seconds: float
    max_deterministic_seconds: float
    max_conflicts: int


@dataclass(frozen=True, repr=False)
class Problem:
    before: Snapshot
    revisions: tuple[Revision, ...]
    candidate: Candidate
    selected_fields: frozenset[str]
    selected_item_ids: frozenset[str]
    windows: tuple[StartWindow, ...]
    routes: tuple[RouteAssessment, ...]


@dataclass(frozen=True)
class Verification:
    accepted: bool
    codes: tuple[str, ...]
    zh: str
    en: str


@dataclass(frozen=True, repr=False)
class SolveResult:
    status: str
    reason: str
    native_status: str | None
    candidate: Candidate | None
    verification: Verification | None
    problem: Problem
    limits: Limits
    overall: str = 'UNKNOWN'
    version: str = VERSION

    @property
    def zh(self):
        return {'CONDITIONAL_SOLUTION':'给定约束下找到并独立校验了条件候选；现实可行性未知。',
                'CONDITIONAL_UNSAT':'仅在给定明确约束下已证明无解；现实事实未核实。',
                'TIMEOUT':'有界运行未形成可发布结论，不能视为无解证明。',
                'UNKNOWN':'证据、输入或执行结果不足，未发布候选。'}[self.status]

    @property
    def en(self):
        return {'CONDITIONAL_SOLUTION':'Conditional candidate found and independently checked; real feasibility is unknown.',
                'CONDITIONAL_UNSAT':'Unsatisfiable only under the explicit supplied constraints; real facts remain unverified.',
                'TIMEOUT':'Bounded execution produced no releasable conclusion; this is not an unsatisfiability proof.',
                'UNKNOWN':'Insufficient evidence, input or execution result; no candidate released.'}[self.status]


class _Incomplete(ValueError):
    pass


def _whole_seconds(delta):
    if delta.microseconds:
        raise _Incomplete('TIME_NOT_REPRESENTABLE_IN_NEEDS')
    return delta.days * 86400 + delta.seconds


def _scaled(value, scale, bound):
    """Exact rational scaling, independent of ambient Decimal context."""
    numerator, denominator = value.as_integer_ratio()
    ticks, remainder = divmod(numerator * scale, denominator)
    if remainder:
        raise _Incomplete('INEXACT_TIME_SCALE')
    if not 0 <= ticks <= bound:
        raise _Incomplete('INTEGER_RANGE_EXCEEDED')
    return ticks


def _movable(problem, old, item):
    return (item['item_id'] in problem.selected_item_ids and 'fixed_items' in problem.selected_fields
            and old['locked'] == {'state': 'known', 'value': False}
            and item['locked'] == {'state': 'known', 'value': False})


def _prepare(problem, limits):
    from math import isfinite
    from cj_needs.domain import decode, validate_fields
    from .routes import _aware, _quantity, assess_route
    from .validator import _instant, protect
    if type(problem) is not Problem or type(limits) is not Limits:
        raise _Incomplete('EXPLICIT_PROBLEM_LIMITS_REQUIRED')
    for name in ('horizon_seconds', 'ticks_per_second', 'max_abs_ticks', 'max_items',
                 'max_edges', 'max_revisions', 'max_conflicts'):
        value = getattr(limits, name)
        if type(value) is not int or value <= 0:
            raise _Incomplete('EXPLICIT_POSITIVE_LIMIT_REQUIRED')
    if limits.max_abs_ticks > 2**60 - 1 or limits.horizon_seconds * limits.ticks_per_second > limits.max_abs_ticks:
        raise _Incomplete('INTEGER_RANGE_EXCEEDED')
    for value in (limits.max_solve_seconds, limits.max_deterministic_seconds):
        if type(value) not in (int, float) or not isfinite(value) or value <= 0:
            raise _Incomplete('EXPLICIT_FINITE_SEARCH_LIMIT_REQUIRED')
    epoch = _aware(limits.epoch)
    if epoch.microsecond:
        raise _Incomplete('TIME_NOT_REPRESENTABLE_IN_NEEDS')
    if (type(problem.revisions) is not tuple or len(problem.revisions) > limits.max_revisions
            or type(problem.windows) is not tuple or type(problem.routes) is not tuple
            or len(problem.windows) > limits.max_items or len(problem.routes) > limits.max_edges):
        raise _Incomplete('INPUT_LIMIT_EXCEEDED')
    protected = protect(problem.before, problem.revisions, problem.candidate,
                        selected_fields=problem.selected_fields, selected_item_ids=problem.selected_item_ids)
    if not any(c.code == 'PROTECTED_SCOPE_UNCHANGED' and c.status == 'PASS' for c in protected.checks):
        raise _Incomplete('INITIAL_PROTECTION_WITHHELD')
    fields = decode(problem.candidate.content)
    validate_fields(fields, complete=True)
    old = {x['item_id']: x for x in problem.before.fields.get('fixed_items', [])}
    items = fields.get('fixed_items', [])
    if not items or len(items) > limits.max_items or set(old) != {x['item_id'] for x in items}:
        raise _Incomplete('EXISTING_BOUNDED_ITEMS_REQUIRED')
    windows = {}
    for window in problem.windows:
        if type(window) is not StartWindow or window.item_id in windows or window.item_id not in old:
            raise _Incomplete('UNIQUE_EXPLICIT_START_WINDOW_REQUIRED')
        low = _whole_seconds(_aware(window.earliest) - epoch)
        high = _whole_seconds(_aware(window.latest) - epoch)
        if not 0 <= low <= limits.horizon_seconds or not 0 <= high <= limits.horizon_seconds:
            raise _Incomplete('TIME_HORIZON_EXCEEDED')
        windows[window.item_id] = (low, high)
    values = {}
    for index, item in enumerate(items):
        start, _, _ = _instant(item['start'], f'fixed_items.{index}.start')
        end, _, _ = _instant(item['end'], f'fixed_items.{index}.end')
        if start is None or end is None:
            raise _Incomplete('EVENT_INSTANT_UNKNOWN')
        offset, finish = _whole_seconds(start - epoch), _whole_seconds(end - epoch)
        if not 0 <= offset <= finish <= limits.horizon_seconds:
            raise _Incomplete('TIME_HORIZON_OR_ORDER_UNSUPPORTED')
        if item['booking_status'].get('state') != 'known':
            raise _Incomplete('ITEM_ACTIVITY_UNKNOWN')
        can_move = _movable(problem, old[item['item_id']], item)
        if can_move and item['item_id'] not in windows:
            raise _Incomplete('SELECTED_START_WINDOW_MISSING')
        duration = finish - offset
        if (item['item_id'] in windows
                and any(bound + duration > limits.horizon_seconds for bound in windows[item['item_id']])):
            # A representation/resource horizon may refuse a problem, never
            # truncate its user bounds and manufacture an infeasibility proof.
            raise _Incomplete('TIME_WINDOW_OUTSIDE_REPRESENTATION_HORIZON')
        values[item['item_id']] = (offset, duration, can_move)
    edges = []
    for assessment in problem.routes:
        if type(assessment) is not RouteAssessment or assessment.candidate != problem.candidate:
            raise _Incomplete('ORIGINAL_ROUTE_CANDIDATE_REQUIRED')
        # Never trust a caller-crafted RouteAssessment's verdict/amounts.
        check = assess_route(problem.before, problem.revisions, problem.candidate,
                             assessment.window, assessment.result, route_index=assessment.route_index,
                             request=assessment.request, config=assessment.config, as_of=assessment.as_of,
                             selected_fields=problem.selected_fields, selected_item_ids=problem.selected_item_ids)
        if check.conditional_relation is None or check.status in ('INVALID', 'CONFLICT'):
            raise _Incomplete('ROUTE_APPLICABILITY_UNKNOWN')
        route = assessment.result.routes[assessment.route_index]
        quantities = (route.duration, assessment.window.buffer, assessment.window.rest)
        # Each component must be representable: fractions are not silently rounded.
        amounts = tuple(_quantity(value) for value in quantities)
        if any(amount is None for amount in amounts):
            raise _Incomplete('ROUTE_SECONDS_UNKNOWN')
        required = sum(_scaled(value, limits.ticks_per_second, limits.max_abs_ticks) for value in amounts)
        if required > limits.max_abs_ticks:
            raise _Incomplete('INTEGER_RANGE_EXCEEDED')
        edges.append((assessment.window.origin_item_id, assessment.window.destination_item_id, required))
    return fields, items, windows, values, edges, epoch


def solve(problem: Problem, limits: Limits, *, stop: Event) -> SolveResult:
    """One bounded feasibility search, single worker, no objective or retry loop.

    stop is checked at phase boundaries. An in-progress CP call is bounded by the
    remaining wall/deterministic/conflict limits; cancellation withholds its output.
    """
    from time import monotonic
    started = monotonic()
    native = None

    def result(status, reason, candidate=None, verification=None):
        return SolveResult(status, reason, native, candidate, verification, problem, limits)

    if type(stop) is not Event:
        return result('UNKNOWN', 'EXPLICIT_STOP_EVENT_REQUIRED')
    if stop.is_set():
        return result('UNKNOWN', 'STOPPED')
    try:
        fields, items, windows, values, edges, epoch = _prepare(problem, limits)
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        return result('UNKNOWN', str(exc) if type(exc) is _Incomplete else 'INPUT_INVALID')
    if stop.is_set():
        return result('UNKNOWN', 'STOPPED')
    remaining = limits.max_solve_seconds - (monotonic() - started)
    if remaining <= 0:
        return result('TIMEOUT', 'PREPARATION_BUDGET_EXHAUSTED')
    try:
        model = cp_model.CpModel()
        variables = {}
        for item in items:
            key = item['item_id']
            original, duration, movable = values[key]
            variable = model.new_int_var(0, limits.horizon_seconds - duration, key)
            variables[key] = variable
            if not movable:
                model.add(variable == original)
            if key in windows:
                low, high = windows[key]
                model.add(variable >= low)
                model.add(variable <= high)
        # Exactly the accepted declared-occupancy rule, not guessed travel/rest.
        for index, a in enumerate(items):
            for b in items[index + 1:]:
                sa, sb = set(a['applies_to']), set(b['applies_to'])
                active = all(x['booking_status'].get('value') in ('booked', 'intended')
                             and x['booking_status'].get('state') == 'known'
                             and x['kind'] in ('appointment', 'transport') for x in (a, b))
                if active and (sa & sb or 'party' in sa or 'party' in sb):
                    ak, bk = a['item_id'], b['item_id']
                    if values[ak][1] and values[bk][1]:
                        order = model.new_bool_var(f'order_{index}_{bk}')
                        model.add(variables[ak] + values[ak][1] <= variables[bk]).only_enforce_if(order)
                        model.add(variables[bk] + values[bk][1] <= variables[ak]).only_enforce_if(order.Not())
        for origin, destination, required in edges:
            scale = limits.ticks_per_second
            model.add((variables[destination] - variables[origin] - values[origin][1]) * scale >= required)
            # Query-time evidence must not be extrapolated when origin is movable.
            model.add(variables[origin] == values[origin][0])
        if model.validate():
            return result('UNKNOWN', 'MODEL_INVALID')
        remaining = limits.max_solve_seconds - (monotonic() - started)
        if remaining <= 0:
            return result('TIMEOUT', 'MODEL_BUDGET_EXHAUSTED')
        engine = cp_model.CpSolver()
        engine.parameters.max_time_in_seconds = remaining
        engine.parameters.max_deterministic_time = limits.max_deterministic_seconds
        engine.parameters.max_number_of_conflicts = limits.max_conflicts
        engine.parameters.num_search_workers = 1
        status = engine.solve(model)
        native = engine.status_name(status)
        if stop.is_set():
            return result('UNKNOWN', 'STOPPED')
        if monotonic() - started >= limits.max_solve_seconds:
            return result('TIMEOUT', 'SEARCH_BUDGET_EXHAUSTED')
        if status == cp_model.INFEASIBLE:
            return result('CONDITIONAL_UNSAT', 'EXACT_SUPPLIED_CONSTRAINTS_INFEASIBLE')
        if status == cp_model.UNKNOWN:
            return result('TIMEOUT', 'BOUNDED_SEARCH_INCOMPLETE')
        if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            return result('UNKNOWN', 'MODEL_INVALID_OR_UNRECOGNIZED_STATUS')
        if monotonic() - started >= limits.max_solve_seconds:
            return result('TIMEOUT', 'OUTPUT_BUDGET_EXHAUSTED')
        from copy import deepcopy
        from datetime import timedelta
        from zoneinfo import ZoneInfo
        from .validator import _json
        output = deepcopy(fields)
        for item in output['fixed_items']:
            key = item['item_id']
            chosen = engine.value(variables[key])
            if chosen == values[key][0]:
                continue
            for edge, offset in (('start', chosen), ('end', chosen + values[key][1])):
                local = (epoch + timedelta(seconds=offset)).astimezone(ZoneInfo(item[edge]['timezone']['value']))
                item[edge]['date']['value'] = local.date().isoformat()
                item[edge]['time']['value'] = local.strftime('%H:%M:%S')
        candidate = Candidate(problem.candidate.needs_id, problem.candidate.base_version, _json(output))
        from .output_check import verify_output
        verification = verify_output(problem, candidate, limits)
        if stop.is_set():
            return result('UNKNOWN', 'STOPPED')
        if monotonic() - started >= limits.max_solve_seconds:
            return result('TIMEOUT', 'VERIFICATION_BUDGET_EXHAUSTED')
        if not verification.accepted:
            return result('UNKNOWN', 'INDEPENDENT_OUTPUT_REJECTED', verification=verification)
        return result('CONDITIONAL_SOLUTION', 'INDEPENDENT_OUTPUT_CHECK_PASSED', candidate, verification)
    except Exception:
        # No solver/library exception is converted to a feasible/unsat result.
        return result('UNKNOWN', 'SOLVER_OR_OUTPUT_ERROR')
