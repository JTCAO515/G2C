"""Local #25 selection/preview seam. Data only; no runtime or write authority."""
from dataclasses import dataclass,field,replace
from hashlib import sha256
import json
import re
from cj_trip.domain import packed,Conflict,Trip
from cj_trip.structured import _date
from cj_trip.manual import ManualEdit,ManualCandidate,prepare as prepare_one
from cj_feasibility.trip_time import TripTimeReport
from cj_feasibility.validator import Report
from cj_trip.manual_needs import EditV2,prepare as prepare_two

VERSION='TRIP-scoped-request.1'


@dataclass(frozen=True,repr=False)
class Request:
    raw:bytes
    request_id:str
    trip_id:str
    expected_version:int
    original_hash:str
    text:str
    language:str
    kind:str
    selected:tuple[str,...]
    @classmethod
    def parse(cls,raw):
        from cj_trip.domain import identifier
        if type(raw) is not bytes or not 0<len(raw)<=65536:raise ValueError('bounded canonical request required')
        value=json.loads(raw)
        if (type(value) is not dict or set(value)!={'version','request_id','trip_id','expected_version','original_hash','text','language','selection'}
                or value['version']!=VERSION or packed(value)!=raw):raise ValueError('exact canonical scoped request required')
        identifier(value['request_id']);identifier(value['trip_id'])
        if type(value['expected_version']) is not int or value['expected_version']<1:raise ValueError('positive original version required')
        digest=value['original_hash']
        if type(digest) is not str or re.fullmatch('[0-9a-f]{64}',digest) is None:raise ValueError('original SHA256 required')
        if type(value['text']) is not str or (not 0<len(value['text'])<=2000 or not value['text'].strip()):raise ValueError('bounded original request text required')
        if value['language'] not in ('zh-Hans','en'):raise ValueError('explicit language required')
        selection=value['selection']
        if type(selection) is not dict:raise ValueError('explicit selection required')
        kind=selection.get('kind')
        if type(kind) is not str:raise ValueError('explicit selection kind required')
        key={'dates':'dates','items':'item_ids'}.get(kind)
        if key is None or set(selection)!={'kind',key}:raise ValueError('one explicit selection kind required')
        selected=selection[key]
        if type(selected) is not list or not 1<=len(selected)<=60 or any(type(v) is not str for v in selected):raise ValueError('bounded selection required')
        if len(set(selected))!=len(selected):raise ValueError('duplicate selected value')
        for selected_value in selected:(_date if kind=='dates' else identifier)(selected_value)
        return cls(raw,value['request_id'],value['trip_id'],value['expected_version'],digest,value['text'],value['language'],kind,tuple(selected))


@dataclass(frozen=True,repr=False)
class Resolution:
    request:Request
    original:Trip
    selected_ids:tuple[str,...]
    status:str
    reason_zh:str
    reason_en:str
    can_publish:bool=field(default=False,init=False)


def _document(trip):
    value=json.loads(trip.content)
    if type(value) is not dict:raise ValueError('structured document required')
    if value.get('content_version')=='structured.1':
        from cj_trip.structured import validate_document
    elif value.get('content_version')=='structured.2':
        from cj_trip.structured_v2 import validate_document
    else:raise ValueError('explicit structured Trip required')
    validate_document(value)
    if packed(value)!=trip.content:raise ValueError('canonical original Trip required')
    return value


def resolve(original,request):
    if (original.trip_id!=request.trip_id or original.version!=request.expected_version
            or sha256(original.content).hexdigest()!=request.original_hash):raise Conflict('explicit original Trip changed')
    document=_document(original);items=document['items'];known={item['id'] for item in items}
    def unclear():return Resolution(request,original,(),'CLARIFICATION_REQUIRED',
        '请明确选择实际行程的日期或条目；当前请求不扩大范围。',
        'Select explicit dates or items of this Trip; this request does not expand scope.')
    if request.kind=='items':
        if not set(request.selected)<=known:raise ValueError('selected item is not in this Trip')
        selected=set(request.selected)
    else:
        selected=set()
        for item in items:
            dates=[item['schedule'][edge]['date'] for edge in ('start','end')]
            if any(value['state']!='known' for value in dates):return unclear()
            observed={value['value'] for value in dates}
            if len(observed)!=1:return unclear()
            if observed.intersection(request.selected):
                if not observed<=set(request.selected):return unclear()
                selected.add(item['id'])
        if not selected:return unclear()
        observed_dates={item['schedule'][edge]['date']['value'] for item in items for edge in ('start','end')}
        if not set(request.selected)<=observed_dates:return unclear()
    # Finite ordinal comparison only; never parse a free-text date or use a clock.
    if re.search(r'明天|今天|昨天|后天|\b(?:tomorrow|today|yesterday)\b',request.text,re.I):return unclear()
    ordinals=[int(number) for number in re.findall(r'\bday\s+([1-9][0-9]?)\b',request.text,re.I)]
    words={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'first':1,'second':2,'third':3}
    for chinese,english in re.findall(r'第([一二三四五六七八九十])天|\b(first|second|third)\s+day\b',request.text,re.I):
        ordinals.append(words[(chinese or english).lower()])
    ordinals.extend(int(number) for number in re.findall(r'第([1-9][0-9]?)天',request.text))
    for ordinal in re.findall(r'第([^\s，。]+?)天',request.text):
        if ordinal not in words and re.fullmatch('[1-9][0-9]?',ordinal) is None:return unclear()
    if re.search(r'\b[0-9]+(?:st|nd|rd|th)\s+day\b|\bday\s+(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|twenty)\b',request.text,re.I):return unclear()
    if any(re.fullmatch('[1-9][0-9]?',n) is None for n in re.findall(r'\bday\s+([0-9]+)\b',request.text,re.I)):return unclear()
    if ordinals:
        starts=[item['schedule']['start']['date'] for item in items]
        if any(value['state']!='known' for value in starts):return unclear()
        days=sorted({value['value'] for value in starts})
        if len(set(ordinals))!=1 or ordinals[0]>len(days):return unclear()
        day=days[ordinals[0]-1]
        if any(item['schedule'][edge]['date']!={'state':'known','value':day}
               for item in items if item['id'] in selected for edge in ('start','end')):return unclear()
        if request.kind=='dates' and set(request.selected)!={day}:return unclear()
    return Resolution(request,original,tuple(item['id'] for item in items if item['id'] in selected),'READY',
        '仅当前明确选区；实际消息、来源与提交仍需原运行校验。',
        'Only the explicit selection; runtime message, sources and commit still require original checks.')


@dataclass(frozen=True,repr=False)
class Preview:
    scope:Resolution
    status:str
    candidate:ManualCandidate|None
    time_report:TripTimeReport|None
    affected_ids:tuple[str,...]
    reason_zh:str
    reason_en:str
    constraint_report:Report|None=None
    can_publish:bool=field(default=False,init=False)


def preview(scope,raw_edit,*,source=None,previous_fields=None):
    if scope.status!='READY':raise ValueError('clarify the explicit selection first')
    version=json.loads(scope.original.content)['content_version']
    edit=(ManualEdit if version=='structured.1' else EditV2).parse(raw_edit)
    if edit.request_id!=scope.request.request_id:raise ValueError('retain the original scoped request ID')
    affected=tuple(dict.fromkeys(item_id for item_id,field,value in edit.changes))
    if edit.order is not None:
        old_order=[item['id'] for item in json.loads(scope.original.content)['items']]
        affected=tuple(dict.fromkeys((*affected,*(item_id for index,item_id in enumerate(edit.order) if index>=len(old_order) or old_order[index]!=item_id))))
    if edit.title is not None or not set(affected)<=set(scope.selected_ids):
        return Preview(scope,'EXPANSION_REQUIRED',None,None,affected,
            '此候选超出已选范围；需展示原因并由用户重新明确选择。',
            'This exceeds the selected scope; show the reason and obtain a new explicit selection.')
    if any(field=='fixed' for item_id,field,value in edit.changes):raise ValueError('assistant cannot change fixed intent; use the explicit manual editor')
    constraints=None
    if source is None:
        candidate=(prepare_one if version=='structured.1' else prepare_two)(scope.original,edit)
    else:
        if version!='structured.2' or previous_fields is None:raise ValueError('original structured2 source association required')
        from cj_trip.manual_needs import NeedsEdit
        from cj_trip.needs_edit_store import checked
        snapshot,_=source.records()
        request=NeedsEdit.parse(packed(dict(version='TRIP-needs-edit.1',needs_reference=dict(id=snapshot.needs_id,
            expected_version=snapshot.version),edit=json.loads(raw_edit))))
        candidate,needs_candidate,constraints=checked(scope.original,request,source,previous_fields)
    # The manual validator supplies protection/CAS, not evidence that a model's
    # new wording was supplied by the user. Keep it unconfirmed/unknown.
    after=json.loads(candidate.content);old={item['id']:item for item in json.loads(scope.original.content)['items']}
    for item in after['items']:
        if item['text']!=old[item['id']]['text']:item['source_category']='unknown'
    diff=json.loads(candidate.diff);diff['after']=after
    candidate=replace(candidate,content=packed(after),diff=packed(diff))
    # Reuse the existing same-package exact unselected/position guard.
    from .core import retain_unselected
    before=json.loads(scope.original.content);after=json.loads(candidate.content)
    retain_unselected(before['items'],after['items'],scope.selected_ids,frozenset())
    if version=='structured.1':from cj_feasibility.trip_time import evaluate
    else:from cj_feasibility.trip_time_v2 import evaluate
    report=evaluate(candidate.content) if source is None else None
    if report is not None and report.status=='CONFLICT':raise Conflict('explicit Trip time conflict')
    return Preview(scope,'PROVISIONAL',candidate,report,affected,
        '局部草稿仅供核对；当前记忆、消息和唯一确认事务尚未接入。',
        'Local preview only; current memory, message and sole confirmation transaction are not connected.',constraints)
