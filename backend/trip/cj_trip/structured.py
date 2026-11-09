"""Opt-in structured.1 grammar only; no time inference, feasibility or write authority."""
from datetime import date,time
import re
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError

from .domain import identifier,validate_source_records

VERSION='structured.1'
MAX_ITEMS=60
MAX_TITLE=120
MAX_TEXT=500


class FieldRejected(ValueError):
    """Structural rejection identified by a field path and static rule."""
    stage='schema'

    def __init__(self,field,rule):
        super().__init__(rule)
        self.field,self.rule=field,rule


class SourceRejected(FieldRejected):
    stage='source'


def _check(field,rule,validate,*args):
    try:
        return validate(*args)
    except FieldRejected as error:
        path=field+'.'+error.field if error.field else field
        raise type(error)(path,error.rule) from None
    except ValueError:
        raise FieldRejected(field,rule) from None


def _fields(value,expected,path,rule):
    if type(value) is not dict:raise FieldRejected(path,rule)
    missing=expected-value.keys()
    if missing:
        field=min(missing)
        raise FieldRejected(path+'.'+field if path else field,'required field missing')
    if value.keys()!=expected:raise FieldRejected(path,rule)


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


def _event(value,check_time):
    _fields(value,{'date','time','timezone','utc_offset'},'','exact event fields required')
    for key,check in (('date',_date),('time',check_time),('timezone',_zone),('utc_offset',_offset)):
        _check(key,'explicit observation with valid '+key,observation,value[key],check)


def event(value):
    _event(value,_time)


def _fixed(value):
    if type(value) is not bool:raise ValueError('explicit boolean fixed value required')


def validate_document(document):
    """Validate shape; even all known fields cannot attest actual feasibility."""
    return _document(document, VERSION, event)


def _document(document, version, check_event):
    if (type(document) is not dict or set(document)!={'content_version','title','items','sources'}
            or document['content_version']!=version):raise FieldRejected('document',version+' document required')
    _check('title','bounded explicit title',_text,document['title'],MAX_TITLE)
    if type(document['items']) is not list or not 1<=len(document['items'])<=MAX_ITEMS:
        raise FieldRejected('items','bounded structured items required')
    sources=_check('sources','valid source records',validate_source_records,document['sources'])
    seen,used=set(),set()
    for index,item in enumerate(document['items']):
        path=f'items[{index}]'
        _fields(item,{'id','text','verification','evidence','schedule','fixed','source_category','source_refs'},
                path,'exact structured item fields required')
        _check(path+'.id','valid item identifier',identifier,item['id'])
        if item['id'] in seen:raise FieldRejected(path+'.id','duplicate global item ID')
        seen.add(item['id'])
        _check(path+'.text','bounded explicit item text',_text,item['text'],MAX_TEXT)
        if item['verification'] not in ('pending','verified'):
            raise FieldRejected(path+'.verification','explicit fact state required')
        evidence=item['evidence']
        if type(evidence) is not list or len(evidence)>40:raise FieldRejected(path+'.evidence','bounded evidence list required')
        for reference in evidence:_check(path+'.evidence','bounded explicit evidence text',_text,reference,4096)
        if item['verification']=='verified' and not evidence:raise SourceRejected(path+'.evidence','verified requires evidence')
        schedule=item['schedule']
        _fields(schedule,{'start','end'},path+'.schedule','exact start/end required')
        for edge in ('start','end'):
            _check(path+'.schedule.'+edge,'explicit event fields required',check_event,schedule[edge])
        _check(path+'.fixed','explicit boolean observation',observation,item['fixed'],_fixed)
        category,refs=item['source_category'],item['source_refs']
        if type(refs) is not list or len(refs)>1:raise FieldRejected(path+'.source_refs','bounded source references required')
        if category=='unknown':
            if refs:raise SourceRejected(path+'.source_refs','unknown cannot borrow source')
        elif category=='user_provided' and not refs:
            # Manual-intent bytes in the guarded publisher provide provenance;
            # this grammar check itself grants no collection or write permission.
            pass
        elif category in ('user_provided','queried','estimated'):
            if len(refs)!=1 or type(refs[0]) is not str or refs[0] not in sources:
                raise SourceRejected(path+'.source_refs','recorded source required')
            source=sources[refs[0]]
            expected={'user_provided':'message','queried':'place','estimated':'route_estimate'}[category]
            if source['kind']!=expected or source['text']!=item['text']:
                raise SourceRejected(path+'.source_refs','source display mismatch')
            if item['verification']!='pending' or evidence:
                raise SourceRejected(path+'.verification','source association is not factual verification')
            used.add(refs[0])
        else:raise FieldRejected(path+'.source_category','unsupported source category')
    if used!=set(sources):raise SourceRejected('sources','unreferenced source')
