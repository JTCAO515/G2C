"""Additive ordinal CP-SAT problem, distinct from the frozen NEEDS Problem.

Windows are explicit supplied constraints, not verified opening facts. The host
compiles source/edge rules before this module; no fake date or booking is needed.
"""
from dataclasses import dataclass
from math import isfinite
from threading import Event
from time import monotonic

from ortools.sat.python import cp_model
from cj_trip.domain import identifier

VERSION = 'CJ-RICH-SCHEDULE@1'
DAY = 86400


@dataclass(frozen=True)
class Window:
    start: int
    end: int

    def __post_init__(self):
        if type(self.start) is not int or type(self.end) is not int or not 0 <= self.start <= self.end < 2**60:
            raise ValueError('explicit ordered integer window required')


@dataclass(frozen=True)
class Visit:
    item_id: str
    day_index: int
    duration: int
    windows: tuple[Window, ...]
    fixed_start: int | None = None

    def __post_init__(self):
        identifier(self.item_id)
        if type(self.day_index) is not int or self.day_index < 1 or type(self.duration) is not int or not 0 <= self.duration < 2**60:
            raise ValueError('explicit ordinal and nonnegative integer duration required')
        if type(self.windows) is not tuple or any(type(w) is not Window for w in self.windows):
            raise ValueError('immutable explicit windows required')
        if self.fixed_start is not None and (type(self.fixed_start) is not int or not 0 <= self.fixed_start < 2**60):
            raise ValueError('explicit protected fixed start required')


@dataclass(frozen=True)
class Transfer:
    origin: str
    destination: str
    seconds: int | None

    def __post_init__(self):
        identifier(self.origin); identifier(self.destination)
        if self.origin == self.destination or self.seconds is not None and (type(self.seconds) is not int or not 0 <= self.seconds < 2**60):
            raise ValueError('distinct endpoints and explicit duration/unknown required')


@dataclass(frozen=True)
class Problem:
    day_count: int
    visits: tuple[Visit, ...]
    transfers: tuple[Transfer, ...]
    frozen_order: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.day_count) is not int or not 1 <= self.day_count <= 1_000_000 // 16:
            raise ValueError('bounded explicit day count required')
        if type(self.visits) is not tuple or not self.visits or any(type(v) is not Visit for v in self.visits):
            raise ValueError('immutable nonempty visits required')
        ids = {v.item_id for v in self.visits}
        if len(ids) != len(self.visits) or any(v.day_index > self.day_count for v in self.visits):
            raise ValueError('unique visits within calendar required')
        if type(self.transfers) is not tuple or any(type(t) is not Transfer for t in self.transfers):
            raise ValueError('immutable explicit transfer observations required')
        keys = {(t.origin, t.destination) for t in self.transfers}
        by_id = {v.item_id: v for v in self.visits}
        if len(keys) != len(self.transfers) or any(t.origin not in ids or t.destination not in ids for t in self.transfers):
            raise ValueError('distinct original transfer endpoints required')
        if any(by_id[t.origin].day_index != by_id[t.destination].day_index for t in self.transfers):
            raise ValueError('cross-day route requires explicit itinerary representation before scheduling')
        if type(self.frozen_order) is not tuple or self.frozen_order and (
                len(self.frozen_order) != len(ids) or set(self.frozen_order) != ids):
            raise ValueError('frozen order must contain every original visit once')


@dataclass(frozen=True)
class Limits:
    max_seconds: float = 1.0
    max_deterministic_seconds: float = 0.1
    max_conflicts: int = 10000
    max_items: int = 60
    max_days: int = 366

    def __post_init__(self):
        if any(type(v) not in (int, float) or not 0 < v < 2**60 or not isfinite(v)
               for v in (self.max_seconds, self.max_deterministic_seconds)):
            raise ValueError('positive finite search budgets required')
        if any(type(v) is not int or not 1 <= v < 2**60 for v in (self.max_conflicts, self.max_items, self.max_days)):
            raise ValueError('positive explicit resource bounds required')


@dataclass(frozen=True)
class Placement:
    item_id: str
    day_index: int
    start: int
    end: int


@dataclass(frozen=True)
class Result:
    status: str
    reason: str
    placements: tuple[Placement, ...] = ()
    unknown_transfers: tuple[tuple[str, str], ...] = ()
    real_feasibility: str = 'UNKNOWN'
    version: str = VERSION


def verify(problem, placements):
    """Independent original-value check; no CP variables/status are consulted."""
    if len(placements) != len(problem.visits) or len({p.item_id for p in placements}) != len(placements):
        return False
    original = {v.item_id: v for v in problem.visits}
    if {p.item_id for p in placements} != original.keys(): return False
    for p in placements:
        v = original[p.item_id]
        if (type(p.start) is not int or type(p.end) is not int or type(p.day_index) is not int or p.day_index != v.day_index
                or p.end != p.start + v.duration or p.end >= problem.day_count*DAY
                or not (v.day_index-1)*DAY <= p.start < v.day_index*DAY
                or not any(w.start <= p.start and p.end <= w.end for w in v.windows)
                or v.fixed_start is not None and p.start != v.fixed_start):
            return False
    # Global occupancy also covers a declared visit crossing midnight.
    for index,a in enumerate(placements):
        for b in placements[index+1:]:
            if a.end > a.start and b.end > b.start and max(a.start,b.start) < min(a.end,b.end): return False
    transfer = {(t.origin,t.destination): t.seconds for t in problem.transfers}
    for day in range(1, problem.day_count+1):
        sequence = [p for p in placements if p.day_index == day]
        if problem.frozen_order and tuple(p.item_id for p in sequence) != tuple(
                key for key in problem.frozen_order if original[key].day_index == day): return False
        for a,b in zip(sequence,sequence[1:]):
            gap = transfer.get((a.item_id,b.item_id))
            if b.start < a.end + (0 if gap is None else gap): return False
    return True


def solve(problem: Problem, limits: Limits, *, stop: Event):
    """One bounded search. Unknown travel never becomes real feasibility PASS."""
    began = monotonic()
    if stop.is_set(): return Result('UNKNOWN','STOPPED')
    if len(problem.visits) > limits.max_items or problem.day_count > limits.max_days:
        return Result('UNKNOWN','REPRESENTATION_OR_RESOURCE_BOUND')
    horizon = problem.day_count*DAY-1
    if any(v.duration > horizon or any(w.end > horizon for w in v.windows) for v in problem.visits):
        return Result('UNKNOWN','WINDOW_OUTSIDE_DECLARED_HORIZON')
    if any(t.seconds is not None and t.seconds > horizon for t in problem.transfers):
        return Result('UNKNOWN','TRANSFER_OUTSIDE_DECLARED_HORIZON')
    model = cp_model.CpModel(); starts = {}; arcs_by_day = {}
    intervals = []; transfer = {(t.origin,t.destination):t.seconds for t in problem.transfers}
    for v in problem.visits:
        start = model.new_int_var((v.day_index-1)*DAY, v.day_index*DAY-1, v.item_id)
        starts[v.item_id] = start
        end = model.new_int_var(0,horizon,'end-'+v.item_id)
        model.add(end == start+v.duration)
        intervals.append(model.new_interval_var(start,v.duration,end,'interval-'+v.item_id))
        options=[]
        for n,w in enumerate(v.windows):
            option=model.new_bool_var(f'window-{v.item_id}-{n}');options.append(option)
            model.add(start >= w.start).only_enforce_if(option)
            model.add(end <= w.end).only_enforce_if(option)
        model.add_exactly_one(options)
        if v.fixed_start is not None:model.add(start == v.fixed_start)
    model.add_no_overlap(intervals)
    for day in range(1,problem.day_count+1):
        nodes=[v for v in problem.visits if v.day_index==day]
        if not nodes:continue
        if problem.frozen_order:
            by_id={v.item_id:v for v in nodes};ordered=[by_id[k] for k in problem.frozen_order if k in by_id]
            for a,b in zip(ordered,ordered[1:]):
                gap=transfer.get((a.item_id,b.item_id))
                model.add(starts[b.item_id] >= starts[a.item_id]+a.duration+(0 if gap is None else gap))
        else:
            arcs=[];all_nodes=[None,*nodes]
            for i,a in enumerate(all_nodes):
                for j,b in enumerate(all_nodes):
                    if i==j:continue
                    selected=model.new_bool_var(f'arc-{day}-{i}-{j}');arcs.append((i,j,selected))
                    if a is not None and b is not None:
                        gap=transfer.get((a.item_id,b.item_id))
                        model.add(starts[b.item_id] >= starts[a.item_id]+a.duration+(0 if gap is None else gap)).only_enforce_if(selected)
            model.add_circuit(arcs);arcs_by_day[day]=(all_nodes,arcs)
    remaining=limits.max_seconds-(monotonic()-began)
    if remaining<=0:return Result('TIMEOUT','PREPARATION_BUDGET_EXHAUSTED')
    if model.validate():return Result('UNKNOWN','MODEL_INVALID')
    if stop.is_set():return Result('UNKNOWN','STOPPED')
    engine=cp_model.CpSolver();engine.parameters.num_search_workers=1
    engine.parameters.max_time_in_seconds=remaining;engine.parameters.max_deterministic_time=limits.max_deterministic_seconds
    engine.parameters.max_number_of_conflicts=limits.max_conflicts
    status=engine.solve(model)
    if stop.is_set():return Result('UNKNOWN','STOPPED')
    if monotonic()-began>=limits.max_seconds:return Result('TIMEOUT','SEARCH_BUDGET_EXHAUSTED')
    if status==cp_model.INFEASIBLE:return Result('CONFLICT','EXPLICIT_CONSTRAINTS_INFEASIBLE')
    if status==cp_model.UNKNOWN:return Result('TIMEOUT','BOUNDED_SEARCH_INCOMPLETE')
    if status not in (cp_model.FEASIBLE,cp_model.OPTIMAL):return Result('UNKNOWN','UNRECOGNIZED_SOLVER_STATUS')
    ordered_ids=[]
    for day in range(1,problem.day_count+1):
        if problem.frozen_order:
            ordered_ids.extend(k for k in problem.frozen_order if next(v for v in problem.visits if v.item_id==k).day_index==day)
        elif day in arcs_by_day:
            nodes,arcs=arcs_by_day[day];successor={i:j for i,j,selected in arcs if engine.value(selected)}
            i=successor[0]
            while i:
                ordered_ids.append(nodes[i].item_id);i=successor[i]
    by_id={v.item_id:v for v in problem.visits}
    placements=tuple(Placement(k,by_id[k].day_index,engine.value(starts[k]),engine.value(starts[k])+by_id[k].duration) for k in ordered_ids)
    if not verify(problem,placements):return Result('UNKNOWN','INDEPENDENT_OUTPUT_REJECTED')
    unknown=tuple((a.item_id,b.item_id) for day in range(1,problem.day_count+1)
                  for sequence in [[p for p in placements if p.day_index==day]]
                  for a,b in zip(sequence,sequence[1:]) if transfer.get((a.item_id,b.item_id)) is None)
    return Result('CONDITIONAL_SCHEDULE','CHECKED_EXPLICIT_CONSTRAINTS',placements,unknown)
