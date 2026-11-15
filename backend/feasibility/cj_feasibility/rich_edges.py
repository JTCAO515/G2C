"""Deterministic §3.6 bounds for proposed activities, with no calendar guesses.

The host supplies source-checked local clocks and explicit user overrides. This
does not authorize dropping/moving original fixed facts or waive source checks.
"""
from dataclasses import dataclass

from .rich_solver import DAY, Window


def _clock(value):
    if value is not None and (type(value) is not int or not 0 <= value < DAY):
        raise ValueError('explicit local clock seconds or unknown required')


@dataclass(frozen=True)
class EdgeWindows:
    windows: tuple[tuple[Window, ...], ...]
    first_unknown_recipe: bool
    last_unknown_morning: bool
    override_explanations: tuple[str, ...]
    unknowns: tuple[str, ...]
    status: str


def activity_windows(day_count, *, arrival_clock=None, departure_clock=None,
                     departure_mode=None, first_day_full=False):
    if type(day_count) is not int or not 1 <= day_count <= 366:
        raise ValueError('explicit supported day count required')
    _clock(arrival_clock); _clock(departure_clock)
    if departure_mode not in (None,'flight','train') or type(first_day_full) is not bool:
        raise ValueError('explicit transport mode and protected override required')
    horizon=day_count*DAY-1;last_offset=(day_count-1)*DAY
    # An explicit full-first-day request waives the policy's padding/light day,
    # never the known physical arrival itself. The summary must disclose it.
    lower=(0 if first_day_full else 12*3600) if arrival_clock is None else arrival_clock+(0 if first_day_full else 2*3600)
    unknown=[]
    if departure_clock is None:
        upper=last_offset+12*3600
    elif departure_mode is None:
        upper=min(last_offset+departure_clock,last_offset+12*3600)
        unknown.append('departure_buffer_mode_unknown')
    else:
        upper=last_offset+departure_clock-(3*3600 if departure_mode=='flight' else 90*60)
    result=[]
    for day in range(day_count):
        start=max(day*DAY,lower);end=min((day+1)*DAY-1,upper,horizon)
        result.append((Window(start,end),) if start<=end else ())
    status='CONFLICT' if lower>=upper else 'CONDITIONAL_WINDOW'
    if status=='CONFLICT' and unknown:status='UNKNOWN'
    return EdgeWindows(tuple(result),arrival_clock is None and not first_day_full,
                       departure_clock is None,('first_day_full_requested',) if first_day_full else (),
                       tuple(unknown),status)
