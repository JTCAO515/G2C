"""Opt-in structured.1 grammar only; no time inference, feasibility or write authority."""
from datetime import date,time,timedelta
import re
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError

from .domain import identifier,validate_source_records

VERSION='structured.1'
MAX_ITEMS=60
MAX_TITLE=120
MAX_TEXT=500


def _text(value,maximum):
    if type(value) is not str or not value.strip() or len(value)>maximum:
        raise ValueError('bounded explicit text required')
    value.encode('utf-8')


def observation(value,known):
    if type(value) is not dict or 'state' not in value:
        raise ValueError('explicit observation required')
    state=value['state']
    if state=='known':
        if set(value)!={'state','value'}:raise ValueError('known observation fields')
        known(value['value'])
    elif state in ('missing','unknown'):
        if set(value)!={'state'}:raise ValueError('unknown observation cannot carry value')
    elif state=='uncertain':
        if set(value)!={'state','note'}:raise ValueError('uncertain observation fields')
        _text(value['note'],500)
    else:raise ValueError('unsupported observation state')


def _date(value):
    _text(value,10)
    if date.fromisoformat(value).isoformat()!=value:raise ValueError('ISO date required')


def _time(value):
    _text(value,8)
    if re.fullmatch(r'[0-9]{2}:[0-9]{2}:[0-9]{2}',value) is None:
        raise ValueError('explicit local HH:MM:SS required')
    time.fromisoformat(value)


def _zone(value):
    _text(value,128)
    if value in ('localtime','Factory'):raise ValueError('device/default timezone not allowed')
    try:ZoneInfo(value)
    except (ZoneInfoNotFoundError,ValueError):raise ValueError('explicit IANA timezone required') from None


def _offset(value):
    _text(value,6)
    if re.fullmatch(r'[+-][0-9]{2}:[0-9]{2}',value) is None:
        raise ValueError('explicit UTC offset required')
    hours,minutes=map(int,value[1:].split(':'))
    if hours>23 or minutes>59:raise ValueError('invalid UTC offset')


def event(value):
    if type(value) is not dict or set(value)!={'date','time','timezone','utc_offset'}:
        raise ValueError('explicit event fields required')
    for key,check in (('date',_date),('time',_time),('timezone',_zone),('utc_offset',_offset)):
        observation(value[key],check)


def _fixed(value):
    if type(value) is not bool:raise ValueError('explicit boolean fixed value required')


def validate_document(document):
    """Validate shape; even all known fields cannot attest actual feasibility."""
    if (type(document) is not dict or set(document)!={'content_version','title','items','sources'}
            or document['content_version']!=VERSION):raise ValueError('structured.1 document required')
    _text(document['title'],MAX_TITLE)
    if type(document['items']) is not list or not 1<=len(document['items'])<=MAX_ITEMS:
        raise ValueError('bounded structured items required')
    sources=validate_source_records(document['sources'])
    seen,used=set(),set()
    for item in document['items']:
        if type(item) is not dict or set(item)!={'id','text','verification','evidence','schedule','fixed','source_category','source_refs'}:
            raise ValueError('structured item fields required')
        identifier(item['id'])
        if item['id'] in seen:raise ValueError('duplicate global item ID')
        seen.add(item['id']);_text(item['text'],MAX_TEXT)
        if item['verification'] not in ('pending','verified'):
            raise ValueError('explicit fact state required')
        evidence=item['evidence']
        if type(evidence) is not list or len(evidence)>40:raise ValueError('bounded evidence list required')
        for reference in evidence:_text(reference,4096)
        if item['verification']=='verified' and not evidence:raise ValueError('verified requires evidence')
        schedule=item['schedule']
        if type(schedule) is not dict or set(schedule)!={'start','end'}:raise ValueError('explicit start/end required')
        event(schedule['start']);event(schedule['end']);observation(item['fixed'],_fixed)
        category,refs=item['source_category'],item['source_refs']
        if type(refs) is not list or len(refs)>1:raise ValueError('bounded source references required')
        if category=='unknown':
            if refs:raise ValueError('unknown cannot borrow source')
        elif category=='user_provided' and not refs:
            # Manual-intent bytes in the guarded publisher provide provenance;
            # this grammar check itself grants no collection or write permission.
            pass
        elif category in ('user_provided','queried','estimated'):
            if len(refs)!=1 or type(refs[0]) is not str or refs[0] not in sources:
                raise ValueError('recorded source required')
            source=sources[refs[0]]
            expected={'user_provided':'message','queried':'place','estimated':'route_estimate'}[category]
            if source['kind']!=expected or source['text']!=item['text']:
                raise ValueError('source display mismatch')
            if item['verification']!='pending' or evidence:
                raise ValueError('source association is not factual verification')
            used.add(refs[0])
        else:raise ValueError('unsupported source category')
    if used!=set(sources):raise ValueError('unreferenced source')
