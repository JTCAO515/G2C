"""Compile explicit fixed-item day ordinals; no calendar dates are invented."""
import re

from cj_needs.domain import InvalidInput

from .lio_planning_grounding import NUMBERS


_DAY = re.compile(r'第([一二两三四五六七八九十]|[1-9][0-9]?)天(?![后之])|'
                  r'\bday\s+([1-9][0-9]?)\b|\b(first|second|third)\s+day\b', re.I)
_ENGLISH_ORDINAL = {'first': 1, 'second': 2, 'third': 3}
_RANGE = re.compile(r'\s*(?:到|至|[–—-]|to|through)\s*', re.I)


def fixed_ordinals(quote, day_count):
    matches = list(_DAY.finditer(quote))
    values = []
    for match in matches:
        raw = match[1] or match[2] or match[3]
        values.append(int(raw) if raw.isascii() and raw.isdecimal()
                      else _ENGLISH_ORDINAL[raw.casefold()] if match[3] else NUMBERS[raw])
    if (len(values) not in (1, 2) or any(index > day_count for index in values)
            or len(values) == 2 and (values[0] >= values[1]
                or _RANGE.fullmatch(quote[matches[0].end():matches[1].start()]) is None)):
        raise InvalidInput('fixed arrangement needs an unambiguous original day range')
    return values[0], values[-1]
