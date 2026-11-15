import pytest

from cj_feasibility.rich_edges import activity_windows
from cj_feasibility.rich_solver import DAY


def test_known_arrival_plus_two_hours_and_flight_minus_three_hours():
    rules=activity_windows(3,arrival_clock=10*3600,departure_clock=20*3600,departure_mode='flight')
    assert rules.windows[0][0].start==12*3600
    assert rules.windows[-1][0].end==2*DAY+17*3600
    assert not rules.first_unknown_recipe and not rules.last_unknown_morning


def test_rail_minus_ninety_minutes_without_changing_the_known_departure():
    rules=activity_windows(2,arrival_clock=0,departure_clock=15*3600,departure_mode='train')
    assert rules.windows[-1][0].end==DAY+13*3600+30*60


def test_unknown_clocks_have_the_exact_light_first_and_morning_last_policy():
    rules=activity_windows(3)
    assert rules.windows[0][0].start==12*3600 and rules.first_unknown_recipe
    assert rules.windows[-1][0].end==2*DAY+12*3600 and rules.last_unknown_morning
    assert rules.override_explanations==()


def test_undated_uses_the_same_ordinals_without_inventing_a_date():
    rules=activity_windows(4)
    assert len(rules.windows)==4 and rules.windows[2][0].start==2*DAY
    assert rules.windows[-1][0].end==3*DAY+12*3600


def test_explicit_full_first_day_is_disclosed_and_does_not_move_before_known_arrival():
    rules=activity_windows(2,first_day_full=True)
    assert rules.windows[0][0].start==0 and not rules.first_unknown_recipe
    assert rules.override_explanations==('first_day_full_requested',)
    known=activity_windows(2,arrival_clock=15*3600,first_day_full=True)
    assert known.windows[0][0].start==15*3600


def test_one_day_combination_reports_no_common_window_instead_of_inventing_precedence():
    assert activity_windows(1).status=='CONFLICT'
    assert activity_windows(1,arrival_clock=15*3600,departure_clock=16*3600,departure_mode='flight').status=='CONFLICT'


def test_late_arrival_and_early_departure_buffers_roll_across_ordinals_not_clipped():
    late=activity_windows(3,arrival_clock=23*3600)
    assert late.windows[0]==() and late.windows[1][0].start==DAY+3600
    early=activity_windows(3,departure_clock=30*60,departure_mode='flight')
    assert early.windows[-1]==() and early.windows[1][0].end==DAY+21*3600+30*60


def test_missing_departure_mode_does_not_guess_a_flight_or_claim_a_proven_buffer():
    rules=activity_windows(3,departure_clock=15*3600)
    assert rules.unknowns==('departure_buffer_mode_unknown',)
    assert rules.windows[-1][0].end<=2*DAY+15*3600


@pytest.mark.parametrize('kwargs',[dict(arrival_clock=True),dict(departure_clock=DAY),
    dict(departure_mode='boat'),dict(first_day_full='yes')])
def test_source_boundary_values_are_explicit(kwargs):
    with pytest.raises(ValueError):activity_windows(3,**kwargs)
