"""Actual OR-Tools, actual NEEDS/PLACE types; all business data synthetic."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Event
import json
import unittest
from unittest.mock import patch

from cj_place import FieldState, Observed
from cj_feasibility import Candidate
from cj_feasibility.solver import Limits, Problem, StartWindow, solve
from cj_feasibility.output_check import verify_output
from test_validator import encode, event, history, item
from test_routes import fixture, seconds
from cj_feasibility.routes import assess_route

EPOCH = datetime(2026,10,22,0,tzinfo=timezone.utc)


def limits(**changes):
    value = Limits(epoch=EPOCH,horizon_seconds=172800,ticks_per_second=1000000,
                   max_abs_ticks=2**60-1,max_items=100,max_edges=100,max_revisions=20,
                   max_solve_seconds=5.0,max_deterministic_seconds=1.0,max_conflicts=100000)
    return replace(value,**changes)


def problem(items, *, selected=frozenset(), windows=()):
    before, revisions = history({'fixed_items':items})
    return Problem(before,revisions,Candidate(before.needs_id,before.version,before.content),
                   frozenset({'fixed_items'}) if selected else frozenset(),selected,tuple(windows),())


def utc(hour, minute=0, *, day=22):
    return datetime(2026,10,day,hour,minute,tzinfo=timezone.utc)


def route_problem(*, latest=120, duration='3600', buffer='0', rest='0', selected=True):
    args=fixture(duration=duration)
    args['window']=replace(args['window'],buffer=seconds(buffer),rest=seconds(rest))
    args['selected_fields']=frozenset({'fixed_items'}) if selected else frozenset()
    args['selected_item_ids']=frozenset({'b'}) if selected else frozenset()
    assessment=assess_route(**args)
    bounds=(StartWindow('b',EPOCH+timedelta(seconds=4500),EPOCH+timedelta(seconds=latest*60)),) if selected else ()
    return Problem(args['before'],args['revisions'],args['candidate'],args['selected_fields'],
                   args['selected_item_ids'],bounds,(assessment,))


class ActualSolverTests(unittest.TestCase):
    def test_real_route_requires_moving_selected_destination_only(self):
        p=route_problem()
        saved=p.candidate.content
        r=solve(p,limits(),stop=Event())
        self.assertEqual(r.status,'CONDITIONAL_SOLUTION',r.reason)
        self.assertEqual(r.overall,'UNKNOWN')
        self.assertIn(r.native_status,('OPTIMAL','FEASIBLE'))
        self.assertTrue(r.verification.accepted)
        old,new=json.loads(saved)['fixed_items'],json.loads(r.candidate.content)['fixed_items']
        self.assertEqual(old[0],new[0])
        self.assertNotEqual(old[1]['start'],new[1]['start'])
        self.assertEqual(p.candidate.content,saved)
        self.assertTrue(verify_output(p,r.candidate,limits()).accepted)

    def test_sixty_cannot_fit_fixed_fifteen_is_conditional_unsat(self):
        p=route_problem(selected=False)
        r=solve(p,limits(),stop=Event())
        self.assertEqual(r.status,'CONDITIONAL_UNSAT',r.reason)
        self.assertEqual(r.native_status,'INFEASIBLE')
        self.assertIsNone(r.candidate)
        self.assertEqual(r.overall,'UNKNOWN')

    def test_locked_and_unselected_cannot_move_to_satisfy_window(self):
        for locked,selected in ((True,frozenset({'a'})),(False,frozenset())):
            a=item('a',start=event('2026-10-22','08:00'),end=event('2026-10-22','09:00'),locked=locked)
            # Original is UTC00:00; supplied exact start window is UTC01:00.
            p=problem([a],selected=selected,windows=(StartWindow('a',utc(1),utc(1)),))
            r=solve(p,limits(),stop=Event())
            self.assertEqual(r.status,'CONDITIONAL_UNSAT',r.reason)

    def test_missing_duration_or_buffer_not_zero(self):
        for missing in ('duration','buffer'):
            p=route_problem()
            assessment=p.routes[0]
            if missing=='duration':
                result=replace(assessment.result,routes=(replace(assessment.result.routes[0],duration=Observed(FieldState.MISSING)),))
                assessment=replace(assessment,result=result)
            else:
                assessment=replace(assessment,window=replace(assessment.window,buffer=Observed(FieldState.UNKNOWN)))
            r=solve(replace(p,routes=(assessment,)),limits(),stop=Event())
            self.assertEqual(r.status,'UNKNOWN')
            self.assertEqual(r.reason,'ROUTE_APPLICABILITY_UNKNOWN')
            self.assertIsNone(r.candidate)

    def test_precision_requires_exact_scale_and_overflow_is_unknown(self):
        p=route_problem(duration='3600.000001')
        r=solve(p,limits(ticks_per_second=1),stop=Event())
        self.assertEqual((r.status,r.reason),('UNKNOWN','INEXACT_TIME_SCALE'))
        r=solve(p,limits(ticks_per_second=1000000),stop=Event())
        self.assertEqual(r.status,'CONDITIONAL_UNSAT',r.reason)  # 3600.000001 cannot fit 3600.
        widened=route_problem(duration='3600.000001',latest=121)
        r=solve(widened,limits(ticks_per_second=1000000),stop=Event())
        self.assertEqual(r.status,'CONDITIONAL_SOLUTION',r.reason)
        for altered in (limits(max_abs_ticks=100),limits(ticks_per_second=2**60)):
            r=solve(p,altered,stop=Event())
            self.assertEqual((r.status,r.reason),('UNKNOWN','INTEGER_RANGE_EXCEEDED'))

    def test_dst_ambiguous_or_missing_date_not_inferred(self):
        for edge in (event('2026-11-01','01:30','America/New_York'),
                     {**event('2026-10-22','08:00'),'date':{'state':'unknown'}}):
            p=problem([item('a',start=edge,end=event('2026-11-01','03:00','America/New_York'))])
            r=solve(p,limits(epoch=datetime(2026,11,1,tzinfo=timezone.utc)),stop=Event())
            self.assertEqual((r.status,r.reason),('UNKNOWN','EVENT_INSTANT_UNKNOWN'))

    def test_cross_day_solution_preserves_duration_and_local_zone(self):
        a=item('a',start=event('2026-10-22','23:30'),end=event('2026-10-23','00:30'))
        p=problem([a],selected=frozenset({'a'}),windows=(StartWindow('a',utc(16,30),utc(16,30)),))
        r=solve(p,limits(),stop=Event())
        self.assertEqual(r.status,'CONDITIONAL_SOLUTION',r.reason)
        output=json.loads(r.candidate.content)['fixed_items'][0]
        self.assertEqual(output['start']['date']['value'],'2026-10-23')
        self.assertEqual(output['start']['time']['value'],'00:30:00')
        self.assertEqual(output['end']['time']['value'],'01:30:00')
        self.assertEqual(output['start']['timezone'],a['start']['timezone'])

    def test_occupancy_constraints_do_not_relax_shared_subject(self):
        a=item('a',start=event('2026-10-22','08:00'),end=event('2026-10-22','09:00'))
        b=item('b',start=event('2026-10-22','08:30'),end=event('2026-10-22','09:30'))
        p=problem([a,b],selected=frozenset({'b'}),windows=(StartWindow('b',utc(0,30),utc(2)),))
        r=solve(p,limits(),stop=Event())
        self.assertEqual(r.status,'CONDITIONAL_SOLUTION',r.reason)
        self.assertTrue(verify_output(p,r.candidate,limits()).accepted)
        fixed=problem([a,b])
        self.assertEqual(solve(fixed,limits(),stop=Event()).status,'CONDITIONAL_UNSAT')

    def test_route_origin_cannot_be_moved_to_future_query_time(self):
        p=route_problem()
        p=replace(p,selected_item_ids=frozenset({'a','b'}),windows=p.windows+(StartWindow('a',utc(1),utc(1)),))
        r=solve(p,limits(),stop=Event())
        self.assertEqual(r.status,'CONDITIONAL_UNSAT',r.reason)

    def test_pre_stop_exception_and_real_budget_exhaustion_not_unsat(self):
        p=route_problem()
        stopped=Event();stopped.set()
        r=solve(p,limits(),stop=stopped)
        self.assertEqual((r.status,r.reason),('UNKNOWN','STOPPED'))
        r=solve(p,limits(max_solve_seconds=1e-12),stop=Event())
        self.assertEqual(r.status,'TIMEOUT')
        self.assertIsNone(r.candidate)
        # Actual CP-SAT deterministic search limit, not a stubbed solver success.
        r=solve(p,limits(max_deterministic_seconds=1e-12),stop=Event())
        self.assertIn(r.status,('TIMEOUT','CONDITIONAL_SOLUTION'))
        self.assertNotEqual(r.status,'CONDITIONAL_UNSAT')
        with patch('ortools.sat.python.cp_model.CpSolver.solve',side_effect=RuntimeError('synthetic engine error')):
            r=solve(p,limits(),stop=Event())
        self.assertEqual((r.status,r.reason),('UNKNOWN','SOLVER_OR_OUTPUT_ERROR'))


class IndependentOutputTests(unittest.TestCase):
    def test_foreign_route_assessment_candidate_binding_is_rejected(self):
        p=route_problem()
        output=solve(p,limits(),stop=Event()).candidate
        foreign=replace(p.routes[0],candidate=replace(p.candidate,base_version=p.candidate.base_version+1))
        changed=replace(p,routes=(foreign,))
        check=verify_output(changed,output,limits())
        self.assertFalse(check.accepted)
        self.assertIn('ORIGINAL_ROUTE_CANDIDATE_CHANGED',check.codes)

    def test_tampered_route_window_and_fixed_item_rejected(self):
        p=route_problem()
        result=solve(p,limits(),stop=Event())
        self.assertEqual(result.status,'CONDITIONAL_SOLUTION')
        for key,time in [('b','09:15'),('a','08:55')]:
            data=json.loads(result.candidate.content)
            target=next(x for x in data['fixed_items'] if x['item_id']==key)
            if key=='b':
                target['start']=event('2026-10-22',time)
                target['end']=event('2026-10-22','12:00')
            else:
                target['end']=event('2026-10-22',time)
            candidate=replace(result.candidate,content=encode(data))
            check=verify_output(p,candidate,limits())
            self.assertFalse(check.accepted)
            self.assertIn('PUBLIC_ROUTE_CHECK_REJECTED',check.codes)

    def test_unrelated_field_duration_horizon_and_identity_tampering_rejected(self):
        p=route_problem()
        output=solve(p,limits(),stop=Event()).candidate
        for mutation in ('duration','description','id','horizon','record'):
            fields=json.loads(output.content)
            candidate=output
            if mutation=='record':
                candidate=replace(candidate,needs_id='other')
            else:
                b=fields['fixed_items'][1]
                if mutation=='duration': b['end']=event('2026-10-22','23:59')
                elif mutation=='description': b['description']='tampered'
                elif mutation=='id': b['item_id']='different'
                else:
                    b['start']=event('2026-10-25','09:00');b['end']=event('2026-10-25','12:00')
                candidate=replace(candidate,content=encode(fields))
            self.assertFalse(verify_output(p,candidate,limits()).accepted,mutation)

    def test_solver_status_does_not_bypass_public_independent_rejection(self):
        from cj_feasibility.solver import Verification
        p=route_problem()
        with patch('cj_feasibility.output_check.verify_output',return_value=Verification(False,('SYNTHETIC_REJECTION',),'拒绝','Rejected')):
            r=solve(p,limits(),stop=Event())
        self.assertEqual((r.status,r.reason),('UNKNOWN','INDEPENDENT_OUTPUT_REJECTED'))
        self.assertIsNone(r.candidate)


class LimitsAndStatusTests(unittest.TestCase):
    def test_engine_unknown_invalid_and_post_stop_are_not_unsat(self):
        from ortools.sat.python import cp_model
        p=route_problem()
        for code,expected in ((cp_model.UNKNOWN,'TIMEOUT'),(cp_model.MODEL_INVALID,'UNKNOWN')):
            with patch.object(cp_model.CpSolver,'solve',return_value=code):
                r=solve(p,limits(),stop=Event())
            self.assertEqual(r.status,expected)
            self.assertIsNone(r.candidate)
        stopped=Event()
        def stop_during_search(*args):
            stopped.set()
            return cp_model.UNKNOWN
        with patch.object(cp_model.CpSolver,'solve',side_effect=stop_during_search):
            r=solve(p,limits(),stop=stopped)
        self.assertEqual((r.status,r.reason),('UNKNOWN','STOPPED'))

    def test_explicit_limits_and_selected_window_are_required(self):
        p=route_problem()
        for l in (limits(max_items=1),limits(max_edges=0),limits(max_revisions=0),
                  limits(max_solve_seconds=float('inf')),limits(ticks_per_second=True)):
            self.assertEqual(solve(p,l,stop=Event()).status,'UNKNOWN')
        self.assertEqual(solve(replace(p,windows=()),limits(),stop=Event()).reason,'SELECTED_START_WINDOW_MISSING')

    def test_small_exhaustive_window_oracle_agrees_with_real_solver(self):
        # A one-hour selected item cannot coexist with a fixed [00:00,01:00)
        # appointment unless its explicitly bounded start reaches 01:00.
        for latest_minute in (0,15,30,45,60,75):
            a=item('a',start=event('2026-10-22','08:00'),end=event('2026-10-22','09:00'))
            b=item('b',start=event('2026-10-22','08:00'),end=event('2026-10-22','09:00'))
            p=problem([a,b],selected=frozenset({'b'}),windows=(StartWindow('b',utc(0),EPOCH+timedelta(minutes=latest_minute)),))
            expected=any(start>=3600 for start in range(latest_minute*60+1))
            r=solve(p,limits(),stop=Event())
            self.assertEqual(r.status,'CONDITIONAL_SOLUTION' if expected else 'CONDITIONAL_UNSAT')
            self.assertTrue(r.zh and r.en)


class RepresentationTests(unittest.TestCase):
    def test_resource_horizon_does_not_turn_truncated_window_into_unsat(self):
        a=item('a',start=event('2026-10-22','08:00'),end=event('2026-10-22','09:00'))
        p=problem([a],selected=frozenset({'a'}),windows=(StartWindow('a',utc(2),utc(2)),))
        r=solve(p,limits(horizon_seconds=7200),stop=Event())
        self.assertEqual((r.status,r.reason),('UNKNOWN','TIME_WINDOW_OUTSIDE_REPRESENTATION_HORIZON'))

    def test_output_ambiguous_wall_time_is_independently_rejected(self):
        a=item('a',start=event('2026-11-01','00:30','America/New_York'),
               end=event('2026-11-01','00:45','America/New_York'))
        at=datetime(2026,11,1,5,30,tzinfo=timezone.utc)
        p=problem([a],selected=frozenset({'a'}),windows=(StartWindow('a',at,at),))
        l=limits(epoch=datetime(2026,11,1,tzinfo=timezone.utc))
        r=solve(p,l,stop=Event())
        self.assertEqual((r.status,r.reason),('UNKNOWN','INDEPENDENT_OUTPUT_REJECTED'))
        self.assertIn('OUTPUT_INSTANT_UNRESOLVED',r.verification.codes)
        self.assertIsNone(r.candidate)

    def test_subsecond_start_window_is_not_rounded_into_needs(self):
        p=route_problem()
        w=p.windows[0]
        p=replace(p,windows=(replace(w,earliest=w.earliest+timedelta(microseconds=1)),))
        r=solve(p,limits(),stop=Event())
        self.assertEqual((r.status,r.reason),('UNKNOWN','TIME_NOT_REPRESENTABLE_IN_NEEDS'))


if __name__=='__main__':
    unittest.main()
