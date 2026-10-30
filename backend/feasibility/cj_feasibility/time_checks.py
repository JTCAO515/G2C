"""Shared explicit-time implementation; no source/auth/occupancy inference."""
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo


def known(value):
    return value['value'] if isinstance(value, dict) and value.get('state') == 'known' else None


def instant(event, path, *, utc_offset=None):
    missing = tuple(f'{path}.{key}' for key in ('date', 'time', 'timezone')
                    if known(event[key]) is None)
    if missing:
        return None, missing, 'incomplete'
    wall = datetime.fromisoformat(known(event['date']) + 'T' + known(event['time']))
    zone = ZoneInfo(known(event['timezone']))
    instants = set()
    for fold in (0, 1):
        aware = wall.replace(tzinfo=zone, fold=fold)
        try:
            utc = aware.astimezone(timezone.utc)
            if utc.astimezone(zone).replace(tzinfo=None) == wall:
                instants.add(utc)
        except OverflowError:
            return None, (f'{path}.representable_instant',), 'out_of_range'
    if len(instants) != 1:
        # A supplied offset may disambiguate a fold, but never supplies a zone,
        # date or missing time. Only explicit caller observations are considered.
        if len(instants)>1 and known(utc_offset) is not None:
            raw=known(utc_offset);hours,minutes=map(int,raw[1:].split(':'))
            expected=timedelta(minutes=(hours*60+minutes)*(1 if raw[0]=='+' else -1))
            matches={value for value in instants if value.astimezone(zone).utcoffset()==expected}
            if len(matches)==1:return matches.pop(), (), 'unique'
        return None, (f'{path}.unambiguous_instant',), 'ambiguous' if instants else 'nonexistent'
    result=instants.pop()
    if known(utc_offset) is not None:
        raw=known(utc_offset);hours,minutes=map(int,raw[1:].split(':'))
        expected=timedelta(minutes=(hours*60+minutes)*(1 if raw[0]=='+' else -1))
        if result.astimezone(zone).utcoffset()!=expected:
            return None,(f'{path}.consistent_utc_offset',),'offset_mismatch'
    return result, (), 'unique'




def overlaps(start, end, other_start, other_end):
    """Positive half-open intervals; touching boundaries and zero length do not overlap."""
    return start < end and other_start < other_end and start < other_end and other_start < end
