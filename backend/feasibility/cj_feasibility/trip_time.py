"""FEASIBILITY-TRIP@1.0 pure time adapter; no fabricated NEEDS snapshots or writes."""
from dataclasses import dataclass
from hashlib import sha256
import json

from cj_trip.domain import packed
from cj_trip.structured import validate_document
from .time_checks import instant
from .validator import Check,Evidence

VERSION='FEASIBILITY-TRIP@1.0'


@dataclass(frozen=True)
class TripTimeReport:
    status: str
    checks: tuple[Check,...]
    content_sha256: str
    version: str=VERSION


def evaluate(content:bytes):
    """Result checks explicit declarations only, never authority or real feasibility."""
    document=json.loads(content)
    validate_document(document)
    if packed(document)!=content:raise ValueError('canonical original Trip bytes required')
    checks=[];intervals=[]
    def evidence(path,value):return Evidence(path,packed(value),None,None,None)
    for index,item in enumerate(document['items']):
        path=f'items.{index}.schedule';schedule=item['schedule']
        start,sm,_=instant(schedule['start'],path+'.start',utc_offset=schedule['start']['utc_offset'])
        end,em,_=instant(schedule['end'],path+'.end',utc_offset=schedule['end']['utc_offset'])
        values=(evidence(path+'.start',schedule['start']),evidence(path+'.end',schedule['end']))
        if start is None or end is None:
            checks.append(Check('ITEM_TIME_UNKNOWN','UNKNOWN',values,sm+em,
                '日期、时间、时区或偏移不足，不能确定区间。','Incomplete or ambiguous explicit event instants.'))
        else:
            reversed=end<start
            checks.append(Check('ITEM_TIME_REVERSED' if reversed else 'ITEM_TIME_ORDER',
                'CONFLICT' if reversed else 'PASS',values,(),
                '明确结束时刻早于开始。' if reversed else '明确起止时刻顺序通过。',
                'Explicit end precedes start.' if reversed else 'Explicit start/end order passed.'))
            if not reversed:intervals.append((index,start,end))
    for n,(index,start,end) in enumerate(intervals):
        for other,os,oe in intervals[n+1:]:
            if start<end and os<oe and max(start,os)<min(end,oe):
                checks.append(Check('OVERLAP_MEANING_UNKNOWN','UNKNOWN',
                    (evidence(f'items.{index}.schedule',document['items'][index]['schedule']),
                     evidence(f'items.{other}.schedule',document['items'][other]['schedule'])),
                    ('authorized_NEEDS_occupancy',),
                    '明确区间相交，但参与人和独占含义尚无当前来源。',
                    'Intervals intersect; current participant/exclusivity evidence is missing.'))
    checks.append(Check('OVERALL_EVIDENCE_INCOMPLETE','UNKNOWN',(),('authorized_NEEDS','route','budget'),
        '时间结构不代表整体行程可行。','Temporal structure does not prove overall trip feasibility.'))
    return TripTimeReport('CONFLICT' if any(c.status=='CONFLICT' for c in checks) else 'UNKNOWN',
                          tuple(checks),sha256(content).hexdigest())
