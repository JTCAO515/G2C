from dataclasses import replace
from threading import Event

import pytest

from cj_feasibility.rich_solver import DAY, Limits, Placement, Problem, Transfer, Visit, Window, solve, verify


def run(problem):return solve(problem,Limits(max_seconds=2),stop=Event())


def test_order_is_solved_inside_explicit_opening_windows_and_fixed_start_is_unchanged():
    p=Problem(1,(Visit('late',1,1800,(Window(14*3600,16*3600),)),
                 Visit('fixed',1,1800,(Window(9*3600,10*3600),),9*3600)),
              (Transfer('fixed','late',1200),Transfer('late','fixed',1200)))
    result=run(p)
    assert result.status=='CONDITIONAL_SCHEDULE' and verify(p,result.placements)
    assert [x.item_id for x in result.placements]==['fixed','late']
    assert result.placements[0].start==9*3600 and result.unknown_transfers==()
    assert result.real_feasibility=='UNKNOWN'


def test_frozen_pairs_adjust_only_times_and_do_not_reuse_a_route_after_reorder():
    visits=(Visit('a',1,1800,(Window(9*3600,11*3600),)),Visit('b',1,1800,(Window(9*3600,11*3600),)))
    p=Problem(1,visits,(Transfer('a','b',600),),('a','b'))
    result=run(p);assert result.status=='CONDITIONAL_SCHEDULE'
    assert result.placements[1].start>=result.placements[0].end+600
    assert not verify(p,tuple(reversed(result.placements)))
    reverse=run(replace(p,frozen_order=('b','a')))
    assert reverse.unknown_transfers==(('b','a'),)


def test_unknown_transfer_stays_explicit_instead_of_becoming_a_verified_zero():
    p=Problem(1,(Visit('a',1,10,(Window(0,100),)),Visit('b',1,10,(Window(0,100),))),(),('a','b'))
    result=run(p);assert result.status=='CONDITIONAL_SCHEDULE'
    assert result.unknown_transfers==(('a','b'),) and result.real_feasibility=='UNKNOWN'
    observed=run(replace(p,transfers=(Transfer('a','b',0),)))
    assert observed.unknown_transfers==()


def test_fixed_conflict_is_not_repaired_by_dropping_an_item_or_loosening_a_window():
    p=Problem(1,(Visit('a',1,200,(Window(100,300),),100),Visit('b',1,200,(Window(100,300),),100)),())
    result=run(p);assert result.status=='CONFLICT' and not result.placements
    empty=replace(p,visits=(replace(p.visits[0],windows=()),))
    assert run(empty).status=='CONFLICT'


def test_ordinal_days_need_no_fake_date_or_booking_and_empty_days_are_preserved():
    p=Problem(3,(Visit('a',1,60,(Window(100,200),)),Visit('b',3,60,(Window(2*DAY+100,2*DAY+200),))),())
    result=run(p);assert result.status=='CONDITIONAL_SCHEDULE'
    assert [x.day_index for x in result.placements]==[1,3] and p.day_count==3


def test_cross_midnight_occupancy_is_checked_globally():
    p=Problem(2,(Visit('late',1,7200,(Window(23*3600,DAY+3600),),23*3600),
                 Visit('early',2,3600,(Window(DAY,DAY+3600),),DAY)),())
    assert run(p).status=='CONFLICT'
    after=replace(p,visits=(p.visits[0],replace(p.visits[1],windows=(Window(DAY+3600,DAY+7200),),fixed_start=DAY+3600)))
    assert run(after).status=='CONDITIONAL_SCHEDULE'


def test_zero_duration_endpoints_have_a_real_selected_circuit_order():
    p=Problem(1,(Visit('a',1,0,(Window(100,100),),100),Visit('b',1,0,(Window(100,100),),100)),())
    result=run(p);assert result.status=='CONDITIONAL_SCHEDULE' and verify(p,result.placements)
    assert {x.item_id for x in result.placements}=={'a','b'}


def test_independent_checker_rejects_missing_changed_fixed_and_wrong_travel_outputs():
    p=Problem(1,(Visit('a',1,10,(Window(100,200),),100),Visit('b',1,10,(Window(100,200),))),
              (Transfer('a','b',20),),('a','b'))
    good=(Placement('a',1,100,110),Placement('b',1,130,140));assert verify(p,good)
    for wrong in (good[:1],(replace(good[0],start=101,end=111),good[1]),
                  (good[0],replace(good[1],start=115,end=125)),
                  (replace(good[0],day_index=True),good[1])):
        assert not verify(p,wrong)


def test_cancel_resource_and_horizon_bounds_are_unknown_not_unsat():
    p=Problem(1,(Visit('a',1,60,(Window(100,200),)),),())
    stop=Event();stop.set();assert solve(p,Limits(),stop=stop).status=='UNKNOWN'
    assert solve(p,Limits(max_items=1),stop=Event()).status=='CONDITIONAL_SCHEDULE'
    assert run(replace(p,visits=(replace(p.visits[0],windows=(Window(0,2*DAY),)),))).status=='UNKNOWN'


@pytest.mark.parametrize('make',[lambda:Window(True,100),lambda:Window(100,10),
    lambda:Visit('a',True,1,()),lambda:Transfer('a','a',1),lambda:Transfer('a','b',True),
    lambda:Limits(max_seconds=float('inf')),lambda:Limits(max_conflicts=True)])
def test_boundary_values_are_validated_once_on_construction(make):
    with pytest.raises(ValueError):make()
