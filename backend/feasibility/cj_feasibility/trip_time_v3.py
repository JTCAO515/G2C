"""Calendar-aware declared time checks; never substitutes for source authority."""
from datetime import time
from hashlib import sha256
import json

from cj_trip.domain import packed
from cj_trip.structured_v3 import validate_document
from .time_checks import instant, known, overlaps
from .trip_time import TripTimeReport
from .validator import Check, Evidence

VERSION = 'FEASIBILITY-TRIP@3.0'


def evaluate(content):
    if type(content) is not bytes or not 0 < len(content) <= 1_000_000:
        raise ValueError('bounded immutable calendar Trip bytes required')
    document = json.loads(content)
    validate_document(document)
    if packed(document) != content:
        raise ValueError('canonical original calendar Trip required')
    dated = document['calendar']['state'] == 'dated'
    checks, intervals = [], []

    def evidence(path, value):
        return Evidence(path, packed(value), None, None, None)

    for index, item in enumerate(document['items']):
        path = f'items.{index}.schedule'
        start, end = item['schedule']['start'], item['schedule']['end']
        values = (evidence(path + '.start', start), evidence(path + '.end', end))
        if dated:
            projected = {}
            for edge, event in (('start', start), ('end', end)):
                day = document['days'][event['day_index']-1]
                projected[edge] = dict(date=dict(state='known', value=day['date']),
                    time=event['time'], timezone=event['timezone'], utc_offset=event['utc_offset'])
            first, sm, _ = instant(projected['start'], path + '.start', utc_offset=start['utc_offset'])
            last, em, _ = instant(projected['end'], path + '.end', utc_offset=end['utc_offset'])
            values += (evidence('calendar', document['calendar']), evidence('days', document['days']))
            missing = sm + em
        else:
            clocks = (known(start['time']), known(end['time']))
            zones = (known(start['timezone']), known(end['timezone']))
            missing = tuple(path + '.' + part for part, val in (
                ('start.time', clocks[0]), ('end.time', clocks[1]), ('start.timezone', zones[0]),
                ('end.timezone', zones[1])) if val is None)
            if not missing and zones[0] == zones[1]:
                first = (start['day_index'], time.fromisoformat(clocks[0]))
                last = (end['day_index'], time.fromisoformat(clocks[1]))
            else:
                first = last = None
                if not missing:
                    missing = ('same_zone_or_explicit_calendar_instants',)
        if first is None or last is None:
            checks.append(Check('ITEM_TIME_UNKNOWN', 'UNKNOWN', values, missing,
                '原时间信息不足，不能确认顺序。', 'Original time observations cannot establish order.'))
        else:
            reversed_time = last < first
            code = ('ITEM_TIME_REVERSED' if reversed_time else 'ITEM_TIME_ORDER') if dated else (
                'ITEM_RELATIVE_REVERSED' if reversed_time else 'ITEM_RELATIVE_ORDER')
            checks.append(Check(code, 'CONFLICT' if reversed_time else 'PASS', values, (),
                '检查明确日历时刻顺序。' if dated else '仅检查明确天序和本地墙上时间的计划顺序。',
                'Explicit calendar instant order.' if dated else 'Declared ordinal/local-clock plan order only.'))
            if not reversed_time:
                intervals.append((index, first, last))
    for position, (index, start, end) in enumerate(intervals):
        for other, os, oe in intervals[position+1:]:
            if overlaps(start, end, os, oe):
                checks.append(Check('OVERLAP_MEANING_UNKNOWN', 'UNKNOWN',
                    (evidence(f'items.{index}.schedule', document['items'][index]['schedule']),
                     evidence(f'items.{other}.schedule', document['items'][other]['schedule'])),
                    ('authorized_NEEDS_occupancy',), '区间相交的参与者及独占含义未确认。',
                    'Participant/exclusivity meaning of overlapping intervals is unconfirmed.'))
    for result in document['date_checks']:
        state = result['state']
        checks.append(Check('DATE_' + result['kind'].upper(),
            'PASS' if state == 'clear' else 'CONFLICT' if state == 'conflict' else 'UNKNOWN',
            (evidence('date_checks', result),), () if state in ('clear', 'conflict') else (result['reason'],),
            '日期依赖检查保留来源结果或未确认。', 'Date-dependent result retained, or explicitly unconfirmed.'))
    checks.append(Check('OVERALL_EVIDENCE_INCOMPLETE', 'UNKNOWN', (),
        ('authorized_NEEDS', 'route', 'budget'), '时间结构不代表整体行程可行。',
        'Temporal structure does not prove overall trip feasibility.'))
    return TripTimeReport('CONFLICT' if any(c.status == 'CONFLICT' for c in checks) else 'UNKNOWN',
                         tuple(checks), sha256(content).hexdigest(), VERSION)
