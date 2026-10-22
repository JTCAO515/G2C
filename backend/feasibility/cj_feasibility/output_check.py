"""Independent candidate validation: no CP-SAT import, variables or status codes."""
from cj_needs.domain import decode, validate_fields
from .validator import Candidate, _instant, protect
from .routes import _aware, assess_route
from .solver import Problem, Verification


def verify_output(problem: Problem, output: Candidate, limits) -> Verification:
    """Re-read actual candidate fields, original windows and original route evidence.

    This can be called on a deliberately altered candidate independently of solve.
    The compiler's scaled numbers, movable flags and booleans are not accepted.
    """
    errors = []
    try:
        guard = protect(problem.before, problem.revisions, output,
                        selected_fields=problem.selected_fields, selected_item_ids=problem.selected_item_ids)
        if not any(c.code == 'PROTECTED_SCOPE_UNCHANGED' and c.status == 'PASS' for c in guard.checks):
            errors.append('PUBLIC_PROTECTION_REJECTED')
        original, proposed = decode(problem.candidate.content), decode(output.content)
        validate_fields(original, complete=True)
        validate_fields(proposed, complete=True)
        if (output.needs_id != problem.candidate.needs_id or output.base_version != problem.candidate.base_version
                or set(original) != set(proposed)):
            errors.append('ORIGINAL_CANDIDATE_BINDING_CHANGED')
        for field in set(original) | set(proposed):
            if field != 'fixed_items' and original.get(field) != proposed.get(field):
                errors.append('NON_TIME_DECLARATION_CHANGED')
        old_items, new_items = original.get('fixed_items', []), proposed.get('fixed_items', [])
        if [item['item_id'] for item in old_items] != [item['item_id'] for item in new_items]:
            errors.append('ITEM_IDENTITIES_OR_ORDER_CHANGED')
        instants = {}
        for index, (old, new) in enumerate(zip(old_items, new_items)):
            for field in old:
                if field not in ('start', 'end') and old[field] != new[field]:
                    errors.append('NON_TIME_DECLARATION_CHANGED')
            old_start, _, _ = _instant(old['start'], f'fixed_items.{index}.start')
            old_end, _, _ = _instant(old['end'], f'fixed_items.{index}.end')
            start, _, _ = _instant(new['start'], f'fixed_items.{index}.start')
            end, _, _ = _instant(new['end'], f'fixed_items.{index}.end')
            if None in (old_start, old_end, start, end):
                errors.append('OUTPUT_INSTANT_UNRESOLVED')
                continue
            from datetime import timedelta
            epoch = _aware(limits.epoch)
            if not epoch <= start <= end <= epoch + timedelta(seconds=limits.horizon_seconds):
                errors.append('TIME_HORIZON_VIOLATED')
            if start > end or old_end - old_start != end - start:
                errors.append('DURATION_OR_ORDER_CHANGED')
            for edge in ('start', 'end'):
                if (old[edge]['timezone'] != new[edge]['timezone'] or old[edge]['place'] != new[edge]['place']):
                    errors.append('EVENT_BINDING_CHANGED')
            # Fixed/unselected content must also remain equal to the ORIGINAL
            # candidate, even when before-history guards happen to allow an edit.
            base = next(x for x in problem.before.fields['fixed_items'] if x['item_id'] == old['item_id'])
            movable = (old['item_id'] in problem.selected_item_ids and 'fixed_items' in problem.selected_fields
                       and base['locked'] == {'state':'known','value':False}
                       and old['locked'] == {'state':'known','value':False})
            if not movable and old != new:
                errors.append('IMMOVABLE_ITEM_CHANGED')
            instants[new['item_id']] = (new, start, end)
        for window in problem.windows:
            if window.item_id not in instants:
                errors.append('WINDOW_ITEM_UNRESOLVED')
            elif not _aware(window.earliest) <= instants[window.item_id][1] <= _aware(window.latest):
                errors.append('START_WINDOW_VIOLATED')
        # Separate direct interval comparison, not solver's pairwise ordering vars.
        values = list(instants.values())
        for i, (a, start, end) in enumerate(values):
            for b, bs, be in values[i + 1:]:
                active = all(x['kind'] in ('appointment','transport')
                             and x['booking_status'].get('state') == 'known'
                             and x['booking_status'].get('value') in ('booked','intended') for x in (a,b))
                sa, sb = set(a['applies_to']), set(b['applies_to'])
                if (active and (sa & sb or 'party' in sa or 'party' in sb)
                        and start < end and bs < be and max(start,bs) < min(end,be)):
                    errors.append('DECLARED_OCCUPANCY_OVERLAP')
        for assessment in problem.routes:
            if assessment.candidate != problem.candidate:
                errors.append('ORIGINAL_ROUTE_CANDIDATE_CHANGED')
                continue
            route = assess_route(problem.before, problem.revisions, output, assessment.window, assessment.result,
                                 route_index=assessment.route_index, request=assessment.request,
                                 config=assessment.config, as_of=assessment.as_of,
                                 selected_fields=problem.selected_fields, selected_item_ids=problem.selected_item_ids)
            if route.status in ('INVALID','CONFLICT') or route.conditional_relation != 'required_within_gap':
                errors.append('PUBLIC_ROUTE_CHECK_REJECTED')
    except (ValueError, TypeError, AttributeError, KeyError, IndexError, OverflowError):
        errors.append('OUTPUT_INPUT_INVALID')
    codes = tuple(sorted(set(errors)))
    return Verification(not codes, codes or ('INDEPENDENT_INVARIANTS_PASSED',),
                        '独立候选不变量校验通过；现实可行性仍未知。' if not codes else '独立候选不变量校验拒绝输出。',
                        'Independent candidate invariants passed; real feasibility remains unknown.' if not codes
                        else 'Independent candidate invariants rejected the output.')
