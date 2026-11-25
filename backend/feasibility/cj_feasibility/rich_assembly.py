"""Pure WP9 structured.4 assembly; the admitted host remains the sole writer.

Ordering precedes route collection. Once routes exist, final scheduling only
moves times. Source acquisition, default application, date-check recomputation,
native authorization/epoch checks and publication stay with the WP8 host.
"""
from copy import deepcopy
from dataclasses import dataclass
from math import ceil

from cj_trip.domain import identifier, packed
from cj_trip.rich_reasons import brief, filter_reason_text
from cj_trip.structured import SourceRejected
from cj_trip.structured_v4 import ITEM_EXTRA, adjacent_pairs, validate_candidate, validate_document
from .rich_edges import EdgeWindows
from .rich_solver import DAY, Limits, Problem, Transfer, Visit, Window, solve


@dataclass(frozen=True)
class Activity:
    """Host-compiled source windows and code-qualified hotel proximity.

    None proximity is explicitly unknown; true must come from the host's actual
    place/hotel observations. Meal period is a typed skeleton choice, not a fact
    inferred from the restaurant name. These fields are not client authority.
    """
    item_id: str
    windows: tuple[Window, ...]
    nearby: bool | None = None
    meal_period: str | None = None

    def __post_init__(self):
        identifier(self.item_id)
        if type(self.windows) is not tuple or any(type(w) is not Window for w in self.windows):
            raise ValueError('explicit immutable source windows required')
        if self.nearby is not None and type(self.nearby) is not bool:
            raise ValueError('code-qualified proximity or unknown required')
        if self.meal_period not in (None, 'breakfast', 'lunch', 'dinner'):
            raise ValueError('explicit meal period or unknown required')


@dataclass(frozen=True)
class Assembly:
    status: str
    reason: str
    content: bytes | None = None
    unknown_transfers: tuple[tuple[str, str], ...] = ()
    removed_reasons: tuple[tuple[str, tuple[str, ...]], ...] = ()
    summary: str = ''
    date_checks_must_be_recomputed: bool = False
    unconfirmed_items: tuple[str, ...] = ()
    # First/last-day stops whose hotel proximity stayed unknown because the host
    # had no observed lodging point (JT 2026-11-25: save and disclose, not refuse).
    edge_proximity_unconfirmed: tuple[str, ...] = ()


def _seconds(event):
    if event['time']['state'] != 'known' or event['timezone'] != dict(state='known', value='Asia/Shanghai'):
        return None
    hours, minutes = map(int, event['time']['value'].split(':'))
    return (event['day_index']-1)*DAY + hours*3600 + minutes*60


def _set_time(event, seconds):
    day, clock = divmod(seconds, DAY)
    hours, remainder = divmod(clock, 3600)
    event['day_index'] = day+1
    event['time'] = dict(state='known', value=f'{hours:02d}:{remainder//60:02d}')


def _intersection(original, policy):
    return tuple(Window(max(a.start,b.start), min(a.end,b.end)) for a in original for b in policy
                 if max(a.start,b.start) <= min(a.end,b.end))


def assemble(document, *, source, facts, activities, edges: EdgeWindows, phase,
             locale, limits: Limits, stop, lodging_unconfirmed=False):
    """Return a bounded conditional candidate; never write or mark verified.

    phase='order': no observed legs allowed; regenerate unconfirmed adjacency.
    phase='schedule': keep every pair frozen and use its original route estimate.
    All protected source items must remain present and unchanged. Unknown edge
    proximity or clocks produce UNKNOWN, not an invented feasible schedule.
    lodging_unconfirmed=True is the host's statement that it has no observed
    lodging point: only unknown first/last-day proximity is then returned in
    edge_proximity_unconfirmed for disclosure instead of refusing.
    """
    return _assemble(document,source=source,facts=facts,activities=activities,edges=edges,
        phase=phase,locale=locale,limits=limits,stop=stop,unconfirmed_items=frozenset(),
        lodging_unconfirmed=lodging_unconfirmed)


def assemble_unconfirmed(document, *, source, facts, activities, edges: EdgeWindows, phase,
                         locale, limits: Limits, stop, unconfirmed_items, lodging_unconfirmed=False):
    """Conditional data after code-qualified terminal tool unavailability.

    The host derives these IDs from the actual sealed outcomes and rechecks
    their coverage in the final source frame. This argument and the returned
    status grant no authority. Only unknown proximity for those IDs may remain
    unconfirmed; known false proximity, hard conflicts and every other UNKNOWN
    keep the normal refusal. No coordinates, route durations or facts are made up.
    """
    if type(unconfirmed_items) is not frozenset or not unconfirmed_items:
        raise ValueError('explicit code-qualified unavailable item set required')
    if not unconfirmed_items <= {item['id']for item in document['items']}:
        raise ValueError('unavailable item outside this complete candidate')
    return _assemble(document,source=source,facts=facts,activities=activities,edges=edges,
        phase=phase,locale=locale,limits=limits,stop=stop,unconfirmed_items=unconfirmed_items,
        lodging_unconfirmed=lodging_unconfirmed)


def _assemble(document, *, source, facts, activities, edges, phase, locale, limits, stop,
              unconfirmed_items, lodging_unconfirmed):
    if type(lodging_unconfirmed) is not bool:
        raise ValueError('explicit host lodging observation state required')
    if phase not in ('order','schedule') or locale not in ('zh','en'):
        raise ValueError('explicit phase and locale required')
    value = deepcopy(document)
    validate_document(value)
    if len(edges.windows) != len(value['days']):
        raise ValueError('edge rules must use the same explicit calendar')
    native = {fact.key: fact.state for fact in facts}
    if len(native) != len(facts) or native != source.document['profile_states']:
        raise SourceRejected('assembly.profile', 'complete accepted profile states required')
    removed = []
    targets = [(item['id'], item) for item in value['items']]
    targets += [('lodging-'+str(index), hotel) for index,hotel in enumerate(value['lodging']['recommendations'])]
    for key,target in targets:
        target['note'], refs, dropped = filter_reason_text(target['note'],target['reason_refs'],facts)
        target['reason_refs'] = list(refs)
        if dropped:
            removed.append((key,dropped))
    validate_candidate(value,source)
    protected = {}
    for record in source.document['records']:
        if (record['provider'],record['kind']) in (('trip','retained_item'),('needs','fixed_item')):
            item = record['payload']['item']
            if item['id'] in protected and packed(protected[item['id']]) != packed(item):
                raise SourceRejected('assembly.fixed', 'incompatible protected originals')
            protected[item['id']] = item
    items = {item['id']:item for item in value['items']}
    for key,original in protected.items():
        if key not in items or packed({k:v for k,v in items[key].items() if k not in ITEM_EXTRA}) != packed(original):
            raise SourceRejected('assembly.fixed', 'complete unchanged protected original set required')
    bounds = {activity.item_id:activity for activity in activities}
    if len(bounds) != len(activities) or bounds.keys() != items.keys():
        raise ValueError('exact source constraint set for all items required')
    if edges.status in ('CONFLICT','UNKNOWN'):
        return Assembly(edges.status, 'EDGE_WINDOWS_'+edges.status)
    if edges.unknowns:
        return Assembly('UNKNOWN','EDGE_CONSTRAINTS_UNCONFIRMED')
    if any(check['kind']=='day_opening' and check['state']=='conflict' for check in value['date_checks']):
        return Assembly('CONFLICT','KNOWN_OPENING_CONFLICT')
    proposed = [item for item in value['items'] if item['id'] not in protected and item['kind'] in ('sight','meal','free_time')]
    # A retained planned stop still occupies its first/last-day recipe slot.
    # Original NEEDS commitments remain distinct from the suggested light plan.
    source_fixed = {record['payload']['item']['id'] for record in source.document['records']
                    if (record['provider'], record['kind']) == ('needs', 'fixed_item')}
    planned = [item for item in value['items'] if item['id'] not in source_fixed
               and item['kind'] in ('sight','meal','free_time')]
    first = [item for item in planned if item['schedule']['start']['day_index']==1]
    last = [item for item in planned if item['schedule']['start']['day_index']==len(value['days'])]
    precedence=()
    if edges.first_unknown_recipe:
        if (len(first)!=2 or sorted(item['kind'] for item in first)!=['meal','sight']):
            return Assembly('CONFLICT','FIRST_DAY_LIGHT_RECIPE_REQUIRED')
        meal = next(item for item in first if item['kind']=='meal')
        if bounds[meal['id']].meal_period is None:
            return Assembly('UNKNOWN','FIRST_DAY_MEAL_PERIOD_UNKNOWN')
        if bounds[meal['id']].meal_period != 'dinner':
            return Assembly('CONFLICT','FIRST_DAY_DINNER_REQUIRED')
        sight=next(item for item in first if item['kind']=='sight')
        precedence=((sight['id'],meal['id']),)
    edge_unconfirmed=[]
    for item in (first if edges.first_unknown_recipe else []) + (last if edges.last_unknown_morning else []):
        nearby = bounds[item['id']].nearby
        if nearby is None:
            if item['id'] in unconfirmed_items:
                continue
            if lodging_unconfirmed:
                # No observed lodging point: disclose, never assume nearby.
                edge_unconfirmed.append(item['id'])
                continue
            return Assembly('UNKNOWN','EDGE_DAY_PROXIMITY_UNCONFIRMED')
        if not nearby:
            return Assembly('CONFLICT','EDGE_DAY_NEARBY_REQUIRED')
    if phase=='order' and any(leg['state']=='estimated' for leg in value['legs']):
        raise SourceRejected('assembly.phase','observed routes cannot survive a new ordering phase')
    visits=[]
    for item in value['items']:
        start,end = (_seconds(item['schedule'][edge]) for edge in ('start','end'))
        if start is None or end is None:
            return Assembly('UNKNOWN','EXPLICIT_CLOCK_OR_ZONE_REQUIRED')
        if end < start:
            return Assembly('CONFLICT','NEGATIVE_DECLARED_DURATION')
        windows = bounds[item['id']].windows
        if item in proposed:
            windows = _intersection(windows, edges.windows[item['schedule']['start']['day_index']-1])
        # Protected/retained facts never move to accommodate a soft default.
        visits.append(Visit(item['id'],item['schedule']['start']['day_index'],end-start,windows,
                            start if item['id'] in protected else None))
    transfers = tuple(Transfer(leg['from_item_id'],leg['to_item_id'],
                               ceil(leg['duration_seconds']) if leg['state']=='estimated' else None)
                      for leg in value['legs'])
    frozen = tuple(item['id'] for item in value['items']) if phase=='schedule' else ()
    problem = Problem(len(value['days']),tuple(visits),transfers,frozen,time_quantum=60,precedence=precedence)
    result = solve(problem,limits,stop=stop)
    if result.status!='CONDITIONAL_SCHEDULE':
        return Assembly(result.status,result.reason)
    ordered=[]
    changed=False
    for placement in result.placements:
        item=items[placement.item_id]
        original_schedule=packed(item['schedule'])
        _set_time(item['schedule']['start'],placement.start)
        _set_time(item['schedule']['end'],placement.end)
        changed |= packed(item['schedule'])!=original_schedule
        ordered.append(item)
    value['items']=ordered
    if phase=='order':
        value['legs']=[dict(day_index=day,from_item_id=a,to_item_id=b,state='unconfirmed',mode=None,
                            duration_seconds=None,distance_m=None,source=None,
                            time_semantics='provider_estimate_at_query_time',future_guaranteed=False)
                       for day,a,b in adjacent_pairs(value)]
    # This is an intermediate candidate. The host must recompute any dated
    # checks over the actual final times and capture those new code results.
    validate_candidate(value,source)
    dated = value['calendar']['state']=='dated'
    status = 'UNCONFIRMED_SKELETON'if unconfirmed_items else'CONDITIONAL_SCHEDULE'
    reason = 'TERMINAL_TOOL_UNCONFIRMED'if unconfirmed_items else result.reason
    return Assembly(status,reason,packed(value),result.unknown_transfers,
                    tuple(removed),brief(facts,locale=locale,first_day_full=bool(edges.override_explanations)),
                    dated and changed,tuple(sorted(unconfirmed_items)),tuple(sorted(edge_unconfirmed)))
