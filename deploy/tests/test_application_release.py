"""Idle deployment clock bounds only; no cloud/configuration action."""
from datetime import datetime,timedelta,timezone

import pytest

from deploy.hk.application_release import require_release_window


def stamp(value):return value.isoformat(timespec='microseconds')


@pytest.mark.parametrize('hour',[0,3,8,9,11,14,17,21,23])
def test_idle_release_has_no_fixed_hour_but_keeps_its_exact_lease(hour):
    start=datetime(2026,11,13,hour,tzinfo=timezone.utc);end=start+timedelta(minutes=30)
    require_release_window(stamp(start),stamp(end),start)
    require_release_window(stamp(start),stamp(end),end-timedelta(microseconds=1))
    for now in (start-timedelta(microseconds=1),end):
        with pytest.raises(ValueError):require_release_window(stamp(start),stamp(end),now)


def test_expired_naive_reversed_or_unbounded_lease_is_refused():
    start=datetime(2026,11,13,tzinfo=timezone.utc)
    for end in (start,start-timedelta(seconds=1),start+timedelta(seconds=7201)):
        with pytest.raises(ValueError):require_release_window(stamp(start),stamp(end),start)
    with pytest.raises(ValueError):require_release_window(stamp(start),stamp(start+timedelta(hours=1)),start.replace(tzinfo=None))
