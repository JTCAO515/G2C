"""First-plan generation profiles only; canonical Trip versions are unchanged."""
from copy import deepcopy
from enum import Enum


class Pace(Enum):
    RELAXED = 'relaxed'
    MODERATE = 'moderate'
    PACKED = 'packed'


SIGHT_COUNTS = {Pace.RELAXED: 2, Pace.MODERATE: 3, Pace.PACKED: 4}
PROFILES = {(ordinal, pace): f'TRIP-lio-{"day" if ordinal else "dated"}-{pace.value}-first.1'
            for ordinal in (False, True) for pace in Pace}
GENERATION_PROFILES = tuple(PROFILES.values())


def response_format(profile):
    from .grouped_plan import DATED_FIRST, ORDINAL_FIRST, response_format as grouped_format
    ordinal, pace = next(key for key, value in PROFILES.items() if value == profile)
    result = deepcopy(grouped_format(ORDINAL_FIRST if ordinal else DATED_FIRST))
    result['json_schema']['name'] = profile.replace('-', '_').replace('.', '_')
    fields = result['json_schema']['schema']['properties']
    fields['version']['const'] = profile
    day = fields['days']['items']
    rows = day['prefixItems'][1]
    sights, meals = deepcopy(rows), deepcopy(rows)
    sights.update(minItems=SIGHT_COUNTS[pace], maxItems=SIGHT_COUNTS[pace])
    meals.update(minItems=2, maxItems=2)
    day.update(minItems=3, maxItems=3, prefixItems=[day['prefixItems'][0], sights, meals])
    return result
