"""Synthetic-only NEEDS fixtures. No SQL, auth calls, external services or writes."""
from copy import deepcopy
from dataclasses import replace
from decimal import localcontext
import json
import unittest

from cj_needs.domain import Command, Revision, Snapshot, validate_fields
from cj_feasibility import Candidate, evaluate, protect


def known(value):
    return {'state': 'known', 'value': value}


def event(day='2026-11-02', wall='09:00', zone='Asia/Shanghai'):
    return {'date': known(day), 'time': known(wall), 'timezone': known(zone),
            'place': {'state': 'unknown'}}


def item(key='a', start=None, end=None, subjects=None, locked=False, kind='appointment', status='booked'):
    return dict(item_id=key, kind=kind, description='synthetic appointment / 合成预约',
                applies_to=subjects or ['self'], locked=known(locked),
                start=start or event(), end=end or event(wall='10:00'), booking_status=known(status))


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def history(*patches):
    fields, revisions = {}, []
    for number, patch in enumerate(patches, 1):
        raw = encode(dict(action_id=f'synthetic-{number}', needs_id='synthetic-needs', expected_version=number - 1,
                          source={'kind': 'manual', 'text': f'synthetic source {number} / 合成来源'}, changes=patch))
        cmd = Command(raw)  # Exercise actual fixed NEEDS grammar, not a mirror schema.
        fields.update(cmd.data['changes'])
        validate_fields(fields, complete=True)
        revisions.append(Revision('synthetic-needs', number, cmd.action_id, raw, encode(fields)))
    return Snapshot('synthetic-needs', len(revisions), encode(fields)), tuple(revisions)


def codes(report, status=None):
    return {c.code for c in report.checks if status is None or c.status == status}


class ValidatorTests(unittest.TestCase):
    def test_empty_and_all_four_states_preserved(self):
        for observation in (known(3), {'state': 'missing'}, {'state': 'unknown'},
                            {'state': 'uncertain', 'note': 'not yet decided / 未定'}):
            s, rs = history({'party_size': observation})
            r = evaluate(s, rs)
            self.assertEqual(r.status, 'UNKNOWN')
            check = next(c for c in r.checks if c.code == 'OBSERVATION_' + observation['state'].upper())
            self.assertEqual(json.loads(check.evidence[0].declaration), observation)
            self.assertIn('FIELD_ABSENT', codes(r))
            self.assertEqual(check.evidence[0].original_input, rs[0].original_input)

    def test_every_declared_field_has_source(self):
        s, rs = history({'party_size': known(3), 'budget_total': known('100.000001')},
                        {'party_size': known(4)})
        r = evaluate(s, rs)
        fields = {c.evidence[0].path: c.evidence[0] for c in r.checks if c.code == 'FIELD_DECLARED'}
        self.assertEqual(fields['budget_total'].revision, 1)
        self.assertEqual(fields['party_size'].revision, 2)
        self.assertEqual(fields['budget_total'].original_input, rs[0].original_input)
        self.assertEqual(s.version, 2)
        # An older explicit snapshot is evaluated with its own original source.
        old = Snapshot(s.needs_id, 1, rs[0].content)
        self.assertNotIn('INPUT_INVALID', codes(evaluate(old, rs[:1])))
        self.assertEqual(evaluate(old, rs).status, 'INVALID')

    def test_chain_mismatch_and_source_tampering_invalid(self):
        s, rs = history({'party_size': known(3)})
        cases = [(replace(s, version=True), rs), (replace(s, source_kind='verified'), rs),
                 (replace(s, needs_id='other'), rs), (s, ()),
                 (s, (replace(rs[0], action_id='other'),)),
                 (s, (replace(rs[0], source_kind='verified'),)),
                 (s, (replace(rs[0], content=encode({'party_size': known(5)})),)),
                 (replace(s, content=b'null'), rs), (replace(s, content=b'{'), rs)]
        for snap, revisions in cases:
            with self.subTest(snap=snap, revisions=revisions):
                self.assertEqual(evaluate(snap, revisions).status, 'INVALID')
        self.assertEqual(evaluate(None, rs).status, 'INVALID')

    def test_duplicate_id_is_invalid_input_not_feasible(self):
        s, rs = history({'fixed_items': [item()]})
        raw_fields = {'fixed_items': [item(), item()]}
        self.assertEqual(evaluate(replace(s, content=encode(raw_fields)), rs).status, 'INVALID')

    def test_cross_day_and_explicit_zones(self):
        a = item(start=event('2026-11-02', '23:30'), end=event('2026-11-03', '00:30'))
        s, rs = history({'fixed_items': [a]})
        self.assertIn('ITEM_TIME_ORDER', codes(evaluate(s, rs), 'PASS'))
        b = item(start=event('2026-11-02', '18:00', 'Asia/Shanghai'),
                 end=event('2026-11-02', '09:30', 'Europe/London'))
        s, rs = history({'fixed_items': [b]})
        self.assertIn('ITEM_TIME_REVERSED', codes(evaluate(s, rs), 'CONFLICT'))

    def test_dst_ambiguous_and_nonexistent_unknown(self):
        for day, wall, reason in [('2026-11-01', '01:30', 'ambiguous'),
                                  ('2026-03-08', '02:30', 'nonexistent')]:
            s, rs = history({'fixed_items': [item(start=event(day, wall, 'America/New_York'),
                                                end=event(day, '04:00', 'America/New_York'))]})
            r = evaluate(s, rs)
            self.assertEqual(r.status, 'UNKNOWN')
            check = next(c for c in r.checks if c.code == 'ITEM_TIME_UNKNOWN')
            self.assertIn(reason, check.en)
            self.assertIn('fixed_items.0.start.unambiguous_instant', check.missing)
        # Non-hour DST transition: 02:15 is nonexistent on Lord Howe spring change.
        s, rs = history({'fixed_items': [item(start=event('2026-10-04', '02:15', 'Australia/Lord_Howe'),
                                            end=event('2026-10-04', '03:00', 'Australia/Lord_Howe'))]})
        self.assertIn('ITEM_TIME_UNKNOWN', codes(evaluate(s, rs)))

    def test_missing_date_does_not_use_host_or_destination_zone(self):
        a = item()
        a['start']['date'] = {'state': 'missing'}
        a['end']['timezone'] = {'state': 'unknown'}
        s, rs = history({'destination_timezone': known('Asia/Shanghai'), 'fixed_items': [a]})
        r = evaluate(s, rs)
        self.assertEqual(r.status, 'UNKNOWN')
        self.assertNotIn('ITEM_TIME_ORDER', codes(r))
        c = next(c for c in r.checks if c.code == 'ITEM_TIME_UNKNOWN')
        self.assertEqual(c.missing, ('fixed_items.0.start.date', 'fixed_items.0.end.timezone'))

    def test_overlap_subjects_party_and_touching(self):
        for sa, sb, overlap in [(['self'], ['self'], True), (['party'], ['companion:m'], True),
                                (['self'], ['companion:m'], False),
                                (['companion:m'], ['companion:n'], False)]:
            s, rs = history({'companions': {'m': 'Mother', 'n': 'Friend'},
                             'fixed_items': [item('a', subjects=sa), item('b', subjects=sb)]})
            self.assertEqual('DECLARED_OCCUPANCY_OVERLAP' in codes(evaluate(s, rs)), overlap)
        s, rs = history({'fixed_items': [item('a'), item('b', start=event(wall='10:00'), end=event(wall='11:00'))]})
        self.assertNotIn('DECLARED_OCCUPANCY_OVERLAP', codes(evaluate(s, rs)))

    def test_hotel_intent_cancelled_and_unknown_are_not_certain_conflicts(self):
        for kind in ('hotel', 'intent'):
            s, rs = history({'fixed_items': [item('a'), item('b', kind=kind)]})
            self.assertIn('OVERLAP_MEANING_UNKNOWN', codes(evaluate(s, rs), 'UNKNOWN'))
            self.assertEqual(evaluate(s, rs).status, 'UNKNOWN')
        s, rs = history({'fixed_items': [item('a'), item('b', status='cancelled')]})
        self.assertIn('OVERLAP_CANCELLED', codes(evaluate(s, rs), 'NOT_APPLICABLE'))
        a = item('b')
        a['booking_status'] = {'state': 'unknown'}
        s, rs = history({'fixed_items': [item('a'), a]})
        self.assertIn('OVERLAP_MEANING_UNKNOWN', codes(evaluate(s, rs)))

    def test_arrival_departure_explicit_and_unknown(self):
        s, rs = history({'arrival': event(wall='11:00'), 'departure': event(wall='10:00')})
        self.assertIn('ARRIVAL_DEPARTURE_ORDER', codes(evaluate(s, rs), 'CONFLICT'))
        s, rs = history({'arrival': event(), 'departure': {**event(), 'date': {'state': 'unknown'}}})
        self.assertIn('ARRIVAL_DEPARTURE_ORDER', codes(evaluate(s, rs), 'UNKNOWN'))

    def test_high_precision_budget_does_not_use_decimal_context_or_infer_cost(self):
        patch = {'party_size': known(100000), 'budget_total': known('999999999999999.999999'),
                 'budget_per_person': known('9999999999.999999'), 'budget_paid': known('999999999999999.999999'),
                 'budget_currency': known('CNY'), 'budget_basis': known('total'),
                 'budget_includes': known(['includes hotels', 'excludes international airfare'])}
        s, rs = history(patch)
        with localcontext() as ctx:
            ctx.prec = 2
            ctx.Emax, ctx.Emin = 2, -2
            r = evaluate(s, rs)
        c = next(c for c in r.checks if c.code == 'BUDGET_SCOPE_UNPROVEN')
        self.assertIn('greater', c.en)
        self.assertEqual(c.status, 'UNKNOWN')
        self.assertEqual(json.loads(c.evidence[4].declaration), patch['budget_total'])
        self.assertNotIn('CONFLICT', {c.status for c in r.checks})
        for key in ('party_size', 'budget_currency', 'budget_basis', 'budget_includes'):
            broken = deepcopy(patch)
            broken[key] = {'state': 'unknown'}
            broken['companions'] = {'m': 'Mother', 'f': 'Father'}
            s, rs = history(broken)
            c = next(c for c in evaluate(s, rs).checks if c.code == 'BUDGET_SCOPE_UNPROVEN')
            self.assertIn(key, c.missing)
            self.assertIn('unavailable', c.en)

    def test_currency_and_paid_remain_original(self):
        for currency in ('CNY', 'USD', 'XXX'):
            s, rs = history({'budget_currency': known(currency), 'budget_paid': known('900.000001'),
                             'budget_total': known('1.000000')})
            r = evaluate(s, rs)
            self.assertEqual(r.status, 'UNKNOWN')
            self.assertNotIn('CONFLICT', {c.status for c in r.checks})
        # Labels named 'state' and identifiers with dots are valid companions, not observations.
        s, rs = history({'companions': {'state': 'known', 'a.b': 'Label'},
                         'fixed_items': [item(subjects=['companion:a.b'])]})
        self.assertNotIn('INPUT_INVALID', codes(evaluate(s, rs)))

    def test_invalid_grammar_and_unknown_are_distinct(self):
        s, rs = history({'party_size': {'state': 'unknown'}})
        for value in [known(True), known(0), {'state': 'not_provided'}, {'state': 'deferred'}]:
            self.assertEqual(evaluate(replace(s, content=encode({'party_size': value})), rs).status, 'INVALID')
        self.assertEqual(evaluate(s, rs).status, 'UNKNOWN')

    def test_two_languages_share_same_check_and_inputs_unmodified(self):
        s, rs = history({'fixed_items': [item('a'), item('b')]})
        saved = deepcopy((s, rs))
        a, b = evaluate(s, rs), evaluate(s, rs)
        self.assertEqual(a, b)
        self.assertEqual((s, rs), saved)
        for c in a.checks:
            self.assertTrue(c.zh and c.en and c.code and c.status)
            if c.status == 'UNKNOWN':
                self.assertTrue(c.missing)


class ProtectionTests(unittest.TestCase):
    def compare(self, patch, *, locked=False, selected_fields=frozenset({'fixed_items'}), selected_ids=frozenset({'a'})):
        first = {'fixed_items': [item('a', locked=locked), item('b')], 'party_size': known(2)}
        old, ors = history(first)
        new, nrs = history(first, patch)
        saved = deepcopy((old, ors, new, nrs))
        result = protect(old, ors, Candidate(old.needs_id, old.version, new.content), selected_fields=selected_fields, selected_item_ids=selected_ids)
        self.assertEqual((old, ors, new, nrs), saved)
        return result

    def test_locked_item_edit_and_delete_blocked_even_when_selected(self):
        for patch in ({'fixed_items': [item('a', locked=False), item('b')]}, {'fixed_items': [item('b')]}):
            self.assertIn('LOCKED_ITEM_CHANGED', codes(self.compare(patch, locked=True), 'CONFLICT'))

    def test_unselected_item_and_field_blocked(self):
        self.assertIn('UNSELECTED_ITEM_CHANGED', codes(self.compare({'fixed_items': [item('a')]}), 'CONFLICT'))
        self.assertIn('UNSELECTED_FIELD_CHANGED', codes(self.compare({'party_size': known(3)}), 'CONFLICT'))

    def test_exact_string_values_not_normalized(self):
        first = {'budget_total': known('1.0')}
        old, ors = history(first)
        new, nrs = history(first, {'budget_total': known('1.00')})
        r = protect(old, ors, Candidate(old.needs_id, old.version, new.content), selected_fields=frozenset(), selected_item_ids=frozenset())
        self.assertIn('UNSELECTED_FIELD_CHANGED', codes(r))

    def test_selected_unlocked_edit_allowed_locally_only(self):
        a = item('a', start=event(wall='08:00'))
        r = self.compare({'fixed_items': [a, item('b')]})
        self.assertEqual(r.status, 'UNKNOWN')
        self.assertIn('PROTECTED_SCOPE_UNCHANGED', codes(r, 'PASS'))

    def test_unknown_lock_cannot_be_relaxed(self):
        a = item('a')
        a['locked'] = {'state': 'unknown'}
        old, ors = history({'fixed_items': [a]})
        new, nrs = history({'fixed_items': [a]}, {'fixed_items': [item('a')]})
        r = protect(old, ors, Candidate(old.needs_id, old.version, new.content), selected_fields=frozenset({'fixed_items'}), selected_item_ids=frozenset({'a'}))
        self.assertIn('LOCK_UNKNOWN_CHANGED', codes(r, 'UNKNOWN'))
        self.assertNotIn('PROTECTED_SCOPE_UNCHANGED', codes(r))

    def test_reordering_retained_items_requires_review(self):
        self.assertIn('ITEM_ORDER_CHANGED', codes(self.compare({'fixed_items': [item('b'), item('a')]})))

    def test_invalid_selection_or_candidate_binding_rejected(self):
        old, ors = history({'party_size': known(2)})
        new, nrs = history({'party_size': known(3)})
        for fields, ids in [(set(), frozenset()), (frozenset({'imagined'}), frozenset()),
                            (frozenset(), frozenset({'missing'}))]:
            self.assertEqual(protect(old, ors, Candidate(old.needs_id, old.version, new.content), selected_fields=fields, selected_item_ids=ids).status, 'INVALID')

    def test_same_snapshot_is_local_pass_not_feasible(self):
        old, ors = history({'party_size': known(2)})
        r = protect(old, ors, Candidate(old.needs_id, old.version, old.content), selected_fields=frozenset(), selected_item_ids=frozenset())
        self.assertEqual(r.status, 'UNKNOWN')
        self.assertEqual(codes(r, 'PASS'), {'PROTECTED_SCOPE_UNCHANGED'})

class AdditionalRiskTests(unittest.TestCase):
    def test_budget_exact_relation_without_paid_and_never_subtracts(self):
        base = {'party_size': known(3), 'budget_per_person': known('1.000001'),
                'budget_currency': known('CNY'), 'budget_basis': known('per_person'),
                'budget_includes': known(['one explicit text statement'])}
        for amount, expected in [('3.000002', 'less'), ('3.000003', 'equal'), ('3.000004', 'greater')]:
            s, rs = history({**base, 'budget_total': known(amount)})
            c = next(c for c in evaluate(s, rs).checks if c.code == 'BUDGET_DECLARED_ARITHMETIC')
            self.assertEqual(dict(c.details), {'relation': expected, 'per_person_times_party': '3.000003'})
            self.assertEqual(c.status, 'UNKNOWN')

    def test_date_bounds_do_not_crash_or_invent_instant(self):
        s, rs = history({'fixed_items': [item(start=event('0001-01-01', '00:00', 'Asia/Shanghai'),
                                            end=event('0001-01-01', '01:00', 'Asia/Shanghai'))]})
        self.assertIn('ITEM_TIME_UNKNOWN', codes(evaluate(s, rs), 'UNKNOWN'))

    def test_duplicate_is_stable_diagnostic_with_actual_input(self):
        s, rs = history({'fixed_items': [item()]})
        broken = replace(s, content=encode({'fixed_items': [item(), item()]}))
        r = evaluate(broken, rs)
        self.assertEqual(r.checks[0].code, 'NEEDS_DUPLICATE_ITEM_ID')
        self.assertEqual(r.checks[0].evidence[0].declaration, broken.content)

    def test_order_and_overlap_properties_bounded_counterexamples(self):
        # Exhaustive small interval grid: touching and separated intervals never conflict.
        for a in range(8, 11):
            for b in range(a + 1, 12):
                for c in range(8, 11):
                    for d in range(c + 1, 12):
                        first = item('a', start=event(wall=f'{a:02}:00'), end=event(wall=f'{b:02}:00'))
                        second = item('b', start=event(wall=f'{c:02}:00'), end=event(wall=f'{d:02}:00'))
                        s, rs = history({'fixed_items': [first, second]})
                        r = evaluate(s, rs)
                        self.assertEqual('DECLARED_OCCUPANCY_OVERLAP' in codes(r), max(a, c) < min(b, d))
                        s2, rs2 = history({'fixed_items': [second, first]})
                        self.assertEqual(r.status, evaluate(s2, rs2).status)

    def test_all_nonknown_locks_require_review_and_cannot_delete(self):
        for lock in ({'state': 'missing'}, {'state': 'unknown'}, {'state': 'uncertain', 'note': 'maybe'}):
            a = item('a')
            a['locked'] = lock
            old, ors = history({'fixed_items': [a]})
            new, nrs = history({'fixed_items': [a]}, {'fixed_items': []})
            r = protect(old, ors, Candidate(old.needs_id, old.version, new.content), selected_fields=frozenset({'fixed_items'}), selected_item_ids=frozenset({'a'}))
            self.assertIn('LOCK_UNKNOWN_CHANGED', codes(r, 'UNKNOWN'))
            self.assertNotIn('PROTECTED_SCOPE_UNCHANGED', codes(r))


class CandidateBindingTests(unittest.TestCase):
    def test_candidate_requires_original_record_and_base_version(self):
        old, ors = history({'party_size': known(2)})
        for c in (Candidate('other', 1, old.content), Candidate(old.needs_id, 2, old.content),
                  Candidate(old.needs_id, True, old.content), old,
                  Candidate(old.needs_id, 1, b'null')):
            r = protect(old, ors, c, selected_fields=frozenset(), selected_item_ids=frozenset())
            self.assertEqual(r.status, 'INVALID')

    def test_proposed_changes_never_borrow_committed_provenance(self):
        old, ors = history({'fixed_items': [item('a', locked=True)]})
        new = Candidate(old.needs_id, old.version, encode({'fixed_items': [item('a')]}))
        r = protect(old, ors, new, selected_fields=frozenset({'fixed_items'}), selected_item_ids=frozenset({'a'}))
        check = next(c for c in r.checks if c.code == 'LOCKED_ITEM_CHANGED')
        self.assertEqual(check.evidence[0].original_input, ors[0].original_input)
        self.assertIsNone(check.evidence[1].revision)
        self.assertIsNone(check.evidence[1].original_input)
        self.assertEqual(r.revision, old.version)
        # No new command, revision or domain write needed for the proposal check.
        self.assertEqual(old.fields['fixed_items'][0]['locked'], known(True))


if __name__ == '__main__':
    unittest.main()
