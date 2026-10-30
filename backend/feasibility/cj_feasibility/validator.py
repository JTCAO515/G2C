"""NEEDS-only checks. No IO, authority, solver or domain writes.

Caller must obtain each object through the existing authorized NEEDS read boundary.
Revision chains establish source association, never authorization or supplier truth.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from .time_checks import known as _known, instant as _instant

from cj_needs.domain import (Command, InvalidInput, Revision, Snapshot, decode,
                             identifier, validate_fields)

VERSION = 'CJ-FEASIBILITY-NEEDS@0.1.0-candidate.1'
NEEDS_COMMIT = 'c821b34d607016c6dbc1020c203621841f1a60e8'


@dataclass(frozen=True, repr=False)
class Candidate:
    """Uncommitted resultant NEEDS fields, explicitly bound to an original version.

    This wrapper adds no collection schema or authority; content is validated by
    the pinned NEEDS validator. Candidate declarations have no committed source.
    """
    needs_id: str
    base_version: int
    content: bytes


@dataclass(frozen=True)
class Evidence:
    path: str
    declaration: bytes  # JSON of unmodified field; invalid input may contain raw malformed JSON
    revision: int | None
    action_id: str | None
    original_input: bytes | None  # exact source bytes, never reconstructed


@dataclass(frozen=True)
class Check:
    code: str
    status: str  # PASS / CONFLICT / UNKNOWN / INVALID / NOT_APPLICABLE
    evidence: tuple[Evidence, ...]
    missing: tuple[str, ...]
    zh: str
    en: str
    details: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Report:
    status: str  # INVALID, CONFLICT, UNKNOWN; this slice never proves feasibility
    checks: tuple[Check, ...]
    needs_id: str | None
    revision: int | None
    content_sha256: str | None
    version: str = VERSION


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def _read(snapshot, revisions):
    if type(snapshot) is not Snapshot or snapshot.source_kind != 'user_provided':
        raise InvalidInput('public user-provided Snapshot required')
    identifier(snapshot.needs_id)
    if type(snapshot.version) is not int or snapshot.version < 1:
        raise InvalidInput('positive snapshot version required')
    if type(revisions) not in (tuple, list) or len(revisions) != snapshot.version:
        raise InvalidInput('exact revision chain 1..snapshot.version required')
    fields = decode(snapshot.content)
    validate_fields(fields, complete=True)
    replay, sources, actions = {}, {}, set()
    for version, rev in enumerate(revisions, 1):
        if (type(rev) is not Revision or rev.needs_id != snapshot.needs_id
                or type(rev.version) is not int or rev.version != version
                or rev.source_kind != 'user_provided'):
            raise InvalidInput('revision record/version/source mismatch')
        cmd = Command(rev.original_input).data
        if (cmd['needs_id'] != snapshot.needs_id or cmd['expected_version'] != version - 1
                or cmd['action_id'] != rev.action_id or rev.action_id in actions):
            raise InvalidInput('revision original action mismatch')
        actions.add(rev.action_id)
        replay.update(cmd['changes'])
        validate_fields(replay, complete=True)
        content = decode(rev.content)
        validate_fields(content, complete=True)
        if content != replay:
            raise InvalidInput('revision content does not match original patches')
        for key in cmd['changes']:
            sources[key] = rev
    if revisions[-1].content != snapshot.content:
        raise InvalidInput('snapshot is not the exact supplied final revision')
    return fields, sources


def _evidence(fields, sources, *paths):
    out = []
    for path in paths:
        root = path.split('.')[0]
        value = fields.get(root)
        # Paths into list entries use their numeric index, never an inferred ID.
        for part in path.split('.')[1:]:
            value = value[int(part)] if isinstance(value, list) else value[part]
        source = sources.get(root)
        out.append(Evidence(path, _json(value), source.version if source else None,
                            source.action_id if source else None,
                            source.original_input if source else None))
    return tuple(out)


def _report(snapshot, checks):
    status = ('INVALID' if any(c.status == 'INVALID' for c in checks) else
              'CONFLICT' if any(c.status == 'CONFLICT' for c in checks) else 'UNKNOWN')
    valid = type(snapshot) in (Snapshot, Candidate)
    revision = (snapshot.version if type(snapshot) is Snapshot else snapshot.base_version) if valid else None
    return Report(status, tuple(checks), snapshot.needs_id if valid else None,
                  revision,
                  sha256(snapshot.content).hexdigest() if valid and type(snapshot.content) is bytes else None)


def _invalid(snapshot, reason):
    evidence = (Evidence('snapshot.content', snapshot.content, None, None, None),) if (
        type(snapshot) in (Snapshot, Candidate) and type(snapshot.content) is bytes) else ()
    code = 'NEEDS_DUPLICATE_ITEM_ID' if reason == 'duplicate item' else 'INPUT_INVALID'
    return _report(snapshot, [Check(code, 'INVALID', evidence, ('valid_snapshot_and_revisions',),
                                   '输入结构或版本来源无效：' + reason,
                                   'Invalid input structure or revision source: ' + reason)])


def evaluate(snapshot: Snapshot, revisions: tuple[Revision, ...]) -> Report:
    """Check an explicit historical snapshot, never implicitly read latest."""
    try:
        fields, sources = _read(snapshot, revisions)
    except (InvalidInput, RecursionError) as exc:
        return _invalid(snapshot, str(exc))
    checks = []

    def add(code, status, paths, missing, zh, en):
        checks.append(Check(code, status, _evidence(fields, sources, *paths), tuple(missing), zh, en))

    # Emit every actual field and every observation, including absent top-level fields.
    from cj_needs.domain import OBSERVATIONS, EVENTS, COLLECTIONS

    def visit(value, path):
        if isinstance(value, dict) and 'state' in value:
            state = value['state']
            add('OBSERVATION_' + state.upper(), 'PASS' if state == 'known' else 'UNKNOWN',
                (path,), () if state == 'known' else (path,),
                '原声明状态：' + state, 'Original observation state: ' + state)
        elif isinstance(value, dict):
            for key, child in value.items():
                visit(child, path + '.' + key)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                visit(child, path + '.' + str(i))

    for key in sorted(set(OBSERVATIONS) | EVENTS | set(COLLECTIONS)):
        if key not in fields:
            add('FIELD_ABSENT', 'UNKNOWN', (key,), (key,), '字段未提供。', 'Field not provided.')
        else:
            add('FIELD_DECLARED', 'PASS', (key,), (), '保留原字段声明与来源。', 'Original field and source retained.')
            if key in OBSERVATIONS or key in EVENTS or key == 'fixed_items':
                visit(fields[key], key)

    intervals = []
    for i, item in enumerate(fields.get('fixed_items', [])):
        path = f'fixed_items.{i}'
        start, sm, sr = _instant(item['start'], path + '.start')
        end, em, er = _instant(item['end'], path + '.end')
        if start is None or end is None:
            add('ITEM_TIME_UNKNOWN', 'UNKNOWN', (path,), sm + em,
                f'不能确定起止时刻（{sr}/{er}）。', f'Start/end instant unresolved ({sr}/{er}).')
        else:
            bad = end < start
            add('ITEM_TIME_REVERSED' if bad else 'ITEM_TIME_ORDER', 'CONFLICT' if bad else 'PASS',
                (path,), (), '结束早于开始。' if bad else '声明起止顺序一致。',
                'End precedes start.' if bad else 'Declared start/end order is consistent.')
            if not bad and start < end:
                intervals.append((i, item, start, end))
    for n, (i, a, start, end) in enumerate(intervals):
        for j, b, bs, be in intervals[n + 1:]:
            if start >= be or bs >= end:
                continue
            sa, sb = set(a['applies_to']), set(b['applies_to'])
            shared = bool(sa & sb) or 'party' in sa or 'party' in sb
            if not shared:
                continue
            paths = (f'fixed_items.{i}', f'fixed_items.{j}')
            statuses = (_known(a['booking_status']), _known(b['booking_status']))
            if 'cancelled' in statuses:
                add('OVERLAP_CANCELLED', 'NOT_APPLICABLE', paths, (),
                    '已声明取消的事项不参与同时占用判定。', 'Declared cancelled item excluded from occupancy checks.')
            elif (all(s in ('booked', 'intended') for s in statuses)
                  and a['kind'] in ('appointment', 'transport') and b['kind'] in ('appointment', 'transport')):
                add('DECLARED_OCCUPANCY_OVERLAP', 'CONFLICT', paths, (),
                    '同一适用人的明确预约或交通声明区间重叠；未核实供应商事实。',
                    'Declared appointment/transport intervals overlap for a shared subject; supplier facts are unverified.')
            else:
                add('OVERLAP_MEANING_UNKNOWN', 'UNKNOWN', paths, ('exclusive_occupancy',),
                    '区间相交，但酒店、意图或未知状态不足以证明占用冲突。',
                    'Intervals intersect; hotel, intent or unknown status does not prove an occupancy conflict.')

    if 'arrival' in fields and 'departure' in fields:
        start, sm, sr = _instant(fields['arrival'], 'arrival')
        end, em, er = _instant(fields['departure'], 'departure')
        status = 'UNKNOWN' if start is None or end is None else 'CONFLICT' if end < start else 'PASS'
        add('ARRIVAL_DEPARTURE_ORDER', status, ('arrival', 'departure'), sm + em,
            '按明确时刻检查抵达与离开顺序；未决时刻不作推断。',
            'Compare arrival/departure order only for unique explicit instants.')

    budget = ('budget_currency', 'budget_basis', 'party_size', 'budget_includes',
              'budget_total', 'budget_per_person', 'budget_paid')
    comparison_fields = budget[:-1]  # Paid is not needed for total/per-person arithmetic.
    missing = tuple(key for key in comparison_fields if _known(fields.get(key)) is None)
    # NEEDS provides only free-text coverage and a single basis. It has no typed cost
    # ledger or assertion that total/per-person caps are equivalent or paid is included.
    # Exact arithmetic can expose a relation, but cannot prove inconsistent caps.
    total, per, count = (_known(fields.get(k)) for k in ('budget_total', 'budget_per_person', 'party_size'))
    relation, product_text = 'unavailable', ''
    if not missing:
        with localcontext(Context(prec=40)):
            # Independent of ambient precision, exponent limits and traps.
            # NEEDS bounds: 15 integer + 6 fractional, party <=100000.
            product = Decimal(per) * count
            product_text = format(product, 'f')
            relation = 'equal' if Decimal(total) == product else 'less' if Decimal(total) < product else 'greater'
    if not missing:
        checks.append(Check('BUDGET_DECLARED_ARITHMETIC', 'UNKNOWN',
                            _evidence(fields, sources, *comparison_fields), ('same_coverage_equivalence',),
                            '仅计算声明的总额与每人乘人数的数值关系，不证明预算冲突或满足。',
                            'Arithmetic relation only; this does not prove budget conflict or satisfaction.',
                            (('relation', relation), ('per_person_times_party', product_text))))
    add('BUDGET_SCOPE_UNPROVEN', 'UNKNOWN', budget,
        missing + ('typed_cost_coverage', 'paid_inclusion_and_basis'),
        '预算保留原十进制声明；总额与每人乘人数关系：' + relation + '。文字范围不能证明费用同口径，不能推定支出或扣减已付。',
        'Exact declared budget relation (total versus per-person times party): ' + relation
        + '. Text coverage cannot establish comparable costs or justify subtracting paid amounts.')
    add('OVERALL_EVIDENCE_INCOMPLETE', 'UNKNOWN', (), ('sourced_routes', 'rest_constraints', 'sourced_costs'),
        '局部检查不能证明整体行程可行；路线、休息与费用依据未验证。',
        'Local checks do not prove trip feasibility; routes, rest and costs remain unverified.')
    return _report(snapshot, checks)


def protect(before: Snapshot, before_revisions: tuple[Revision, ...],
            candidate: Candidate, *,
            selected_fields: frozenset[str], selected_item_ids: frozenset[str]) -> Report:
    """Check an uncommitted candidate against an explicit historical NEEDS read.

    Unselected top-level fields are protected. Selecting fixed_items permits only
    explicitly selected IDs; locked/undetermined-lock items remain protected.
    """
    try:
        old, os = _read(before, before_revisions)
        if type(candidate) is not Candidate:
            raise InvalidInput('explicit uncommitted Candidate required')
        if (type(candidate.base_version) is not int or candidate.base_version != before.version
                or candidate.needs_id != before.needs_id):
            raise InvalidInput('candidate must bind exact before record/version')
        new = decode(candidate.content)
        validate_fields(new, complete=True)
        ns = {}  # Proposed fields have no committed revision/source; never borrow old provenance.
        from cj_needs.domain import OBSERVATIONS, EVENTS, COLLECTIONS
        keys = set(OBSERVATIONS) | EVENTS | set(COLLECTIONS)
        if (type(selected_fields) is not frozenset or not selected_fields <= keys
                or type(selected_item_ids) is not frozenset):
            raise InvalidInput('explicit field and item selection required')
        for key in selected_item_ids:
            identifier(key)
        old_items = {x['item_id']: x for x in old.get('fixed_items', [])}
        new_items = {x['item_id']: x for x in new.get('fixed_items', [])}
        if not selected_item_ids <= old_items.keys() | new_items.keys():
            raise InvalidInput('selected item ID unavailable')
        if selected_item_ids and 'fixed_items' not in selected_fields:
            raise InvalidInput('item selection requires fixed_items selection')
    except (InvalidInput, RecursionError) as exc:
        return _invalid(candidate, str(exc))
    checks = []

    def changed(code, path, status='CONFLICT', missing=(), item_id=None):
        evidence = tuple(Evidence('before.' + e.path, e.declaration, e.revision, e.action_id, e.original_input)
                         for e in _evidence(old, os, path)) + tuple(
                         Evidence('candidate.' + e.path, e.declaration, e.revision, e.action_id, e.original_input)
                         for e in _evidence(new, ns, path))
        checks.append(Check(code, status, evidence, missing,
                            '保护范围发生变化，需审阅；此结果不授予写入权限。',
                            'Protected scope changed; review required. This result grants no write authority.',
                            (('item_id', item_id),) if item_id is not None else ()))

    absent = object()
    for key in sorted(set(old) | set(new)):
        if key not in selected_fields and old.get(key, absent) != new.get(key, absent):
            changed('UNSELECTED_FIELD_CHANGED', key)
    # Retained item order is part of the explicit collection, not a set.
    if ([key for key in old_items if key in new_items]
            != [key for key in new_items if key in old_items]):
        changed('ITEM_ORDER_CHANGED', 'fixed_items')
    # Compare fixed-item objects exactly, without string/date/decimal normalization.
    for key in sorted(old_items.keys() | new_items.keys()):
        a, b = old_items.get(key), new_items.get(key)
        if a == b:
            continue
        if key not in selected_item_ids or 'fixed_items' not in selected_fields:
            changed('UNSELECTED_ITEM_CHANGED', 'fixed_items', item_id=key)
        elif a is not None and _known(a['locked']) is not False:
            unknown = _known(a['locked']) is None
            changed('LOCK_UNKNOWN_CHANGED' if unknown else 'LOCKED_ITEM_CHANGED', 'fixed_items',
                    'UNKNOWN' if unknown else 'CONFLICT', (f'fixed_items:{key}.locked',) if unknown else (), item_id=key)
    if not checks:
        checks.append(Check('PROTECTED_SCOPE_UNCHANGED', 'PASS',
                            _evidence(old, os, *sorted(old)) + _evidence(new, ns, *sorted(new)), (),
                            '固定与未选中内容保持相等；不代表整体可行或允许写入。',
                            'Locked and unselected content is equal; this proves neither feasibility nor write permission.'))
    return _report(candidate, checks)
