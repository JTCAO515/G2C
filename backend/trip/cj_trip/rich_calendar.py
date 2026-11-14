"""Local calendar observations, not venue opening or legal eligibility evidence."""
from dataclasses import dataclass
from datetime import date, timedelta

import chinese_calendar as calendar


@dataclass(frozen=True)
class CalendarDay:
    day: date
    kind: str
    name: str | None = None
    long_break: bool = False


def classify(day: date) -> CalendarDay:
    if type(day) is not date:
        raise ValueError('an explicit local calendar date is required')
    try:
        holiday, name = calendar.get_holiday_detail(day)
    except NotImplementedError:
        return CalendarDay(day, 'unknown')
    if day in calendar.workdays:
        return CalendarDay(day, 'makeup_workday', name)
    if name and holiday:
        # Count this actual contiguous named break, not every weekend in a year.
        days = 1
        for direction in (-1, 1):
            cursor = day
            for _ in range(31):
                cursor += timedelta(days=direction)
                if calendar.holidays.get(cursor) != name:
                    break
                days += 1
        return CalendarDay(day, 'holiday_break', name, days >= 3)
    return CalendarDay(day, 'weekend' if holiday else 'workday')


def statutory_exception(day: CalendarDay) -> bool | None:
    """Named break data does not distinguish every statutory/lieu day.

    A named break therefore cannot clear a venue's weekly closure. Ordinary
    weekends and makeup workdays do not trigger the statutory exception.
    """
    return None if day.kind in ('unknown', 'holiday_break') else False
