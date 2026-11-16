"""Native4 plan-understanding data boundary, not a NEEDS/source grant.

Callers supply real originals with each MID's persistent question_day. This
first parser checks data and source spans; full field/fixed-window compilation,
genuine4/profile/Memory holds and the sole publisher remain mandatory.
"""
from datetime import date,timedelta
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from pydantic import ValidationError

from cj_message.lio_plan_input_schema import PlanUnderstanding
from cj_needs.domain import InvalidInput,decode,validate_fields
from .lio_flat_intake import _observations
from .lio_national_intake import _current_date_source,_current_date_anchors,_WEEK_SOURCE,ZONE_LITERAL,fields_for,fixed_sources_complete
from .lio_sourced_intake import _booking_source
from .lio_planning_grounding import PlanningTurn
from .lio_planning_grounding import CLOCK,NUMBER,NEGATED,DATE_REFUSAL,DATES_UNDECIDED,_clock,_number
from .lio_positive_trip import supports as positive_trip_support
from .local_lio_rich_calendar_source import read_rich_original
from .lio_calendar_ordinals import fixed_ordinals
from .local_lio_calendar import date_completion

_PRECISE_CLOCK=re.compile(r'(?<![0-9])'+CLOCK+r'(?![0-9])',re.I)
_CLOCK_DENIAL=re.compile(r'(?:not(?:\s+at|\s+before|\s+after)?|不是|并非|不早于|不晚于|大约|大概|around|about)\s*$',re.I)
_CLOCK_OFFSET=re.compile(r'(?:\bUTC|\bGMT|\bCST|offset|时区|偏移)\s*[+−-]\s*$|[\(\[（]\s*[+−-]\s*$',re.I)
_OFFSET_LITERAL=re.compile(r'(?<![0-9])[+−-](?:0[0-9]|1[0-4]):?[0-5][0-9](?![0-9])')
_CHINA_TIME=re.compile(r'中国时间|北京时间|\bChina time\b|\bBeijing time\b',re.I)
_CLAUSE_BREAK=re.compile(r'[，,。!?！？；;\n]|\.(?=\s+[A-Z]|$)|\b(?:and|then|but)\b|然后|而是',re.I)
_SENTENCE_BREAK=re.compile(r'[。!！？?；;\n]|\.(?=\s+[A-Z]|$)')
_EVENTS={'arrival':re.compile(r'到达|抵达|落地|\b(?:arriv\w*|land(?:s|ing|ed)?)\b',re.I),
         'departure':re.compile(r'出发|离开|起飞|返程|\b(?:leav\w*|depart\w*|take ?off|takes ?off)\b',re.I)}
_ENDPOINT_DENIAL=re.compile(r'不会|不(?:从|在|到|抵达|到达|出发|离开)|不再|并非|不是|'
    r'\b(?:not|never|won[’\x27]t|wouldn[’\x27]t|don[’\x27]t)\b',re.I)
_PARTY_COUNT=re.compile(r'(?<![0-9])([0-9]{1,6}|'+NUMBER+r')\s*(?:个?人|people\b|persons?\b|travel(?:l)?ers?\b)',re.I)
_SOLO=re.compile(r'只有我|仅我|独自|\b(?:alone|solo|just me|only me)\b',re.I)
_NONFACT=re.compile(r'[?？]|大约|大概|左右|\b(?:around|about|approximately)\b',re.I)
_START_BEFORE=re.compile(r'(?:从|开始日期(?:是|为)?|出发日期(?:是|为)?)\s*[:：]?\s*$|'
    r'\b(?:starting|beginning|from|start (?:my |the )?trip(?: on)?)\s*$',re.I)
_START_AFTER=re.compile(r'^\s*(?:出发|开始|起(?:程)?|去[^。！？!?]{0,20}(?:玩|旅行|旅游))',re.I)
_PARTY_STATEMENT=re.compile(r'(?:(?:一共|总共|我们(?:一共|共)?|只有我|仅我|我|出行人数[:：]?)\s*)?'+_PARTY_COUNT.pattern+r'(?:出行|同行)?|'
    r'(?:(?:there (?:are|will be)|we are|our (?:party|group)(?: size)?(?: is| of)?|party size[:：]?|for)\s+)?'+_PARTY_COUNT.pattern+r'|'
    r'(?:只有我|仅我|我(?:独自|一个人)(?:出行)?|(?:I am (?:travel(?:l)?ing )?)?(?:alone|solo)|just me|only me)',re.I)
_TRAVELER_SUBJECT=re.compile(r'(?:I(?: will| am)?|we(?: will| are)?|(?:my|our|the) (?:flight|train)(?: will)?|'
    r'(?:我|我们|(?:我的|我们的|本次)?(?:航班|飞机|列车|高铁))?(?:将|会|在|于)?)',re.I)
_QUOTED=re.compile(r'"[^"\n]*"|“[^”\n]*”|「[^」\n]*」|『[^』\n]*』|(?<!\w)\x27[^\x27\n]*\x27(?!\w)|‘[^’\n]*’')
_MODES={'flight':re.compile(r'航班|飞机|\bflight\b',re.I),
        'train':re.compile(r'高铁|火车|列车|\btrain\b',re.I)}
_FULL_FIRST=re.compile(r'(?:请|我想|我希望|我们希望)?(?:把)?第(?:一|1)天(?:就|也|要)?(?:安排|排)(?:满|充实)|'
    r'(?:please )?(?:fill|pack)(?: up)? (?:my |our |the )?first day(?: fully)?|'
    r'(?:please )?make (?:my |our |the )?first day full',re.I)
_LIGHT_FIRST=re.compile(r'第(?:一|1)天(?:不要|别)(?:安排|排)满|(?:不要|别)(?:把)?第(?:一|1)天(?:安排|排)满|'
    r'(?:不要|别)(?:安排|排)满第(?:一|1)天|(?:please )?(?:do not|don[’\x27]t) (?:fill|pack)(?: up)? (?:my |our |the )?first day|'
    r'(?:please )?keep (?:my |our |the )?first day light',re.I)
_META_SOURCE=re.compile(r'^\s*(?:(?:(?:can|could|would) you\s+)?(?:please\s+)?'
    r'(?:translate|rephrase|paraphrase|repeat|quote|explain)\b|'
    r'(?:请帮我|请|帮我)?(?:把|将)?(?:下面|以下|上面|这)[^，,。！？;]{0,40}(?:翻译|复述|引用|改写|解释)|'
    r'(?:请帮我|请|帮我)?(?:翻译|复述|引用|改写))',re.I)


def _quoted_source(text,start,end):
    return any(match.start()<end and start<match.end()for match in _QUOTED.finditer(text))


def _source_clause_bounds(text,start,end):
    before=[match for match in _CLAUSE_BREAK.finditer(text)if match.end()<=start]
    after=_CLAUSE_BREAK.search(text,end)
    last=(after.end()if after[0]in ('?','？')else after.start())if after else len(text)
    return (before[-1].end()if before else 0),last


def _source_clause(text,start,end):
    first,last=_source_clause_bounds(text,start,end)
    return text[first:last]


def _original_clauses(text):
    boundaries=tuple(_CLAUSE_BREAK.finditer(text))
    for start,end in zip((0,*(match.end()for match in boundaries)),
                         (*(match.start()for match in boundaries),len(text)),strict=True):
        raw=text[start:end];clause=raw.strip().rstrip('.。!！')
        if clause:
            position=start+raw.index(clause)
            yield position,position+len(clause),clause


def _source_sentence(text,start,end):
    before=[match for match in _SENTENCE_BREAK.finditer(text)if match.end()<=start]
    after=_SENTENCE_BREAK.search(text,end)
    return text[before[-1].end()if before else 0:after.end()if after else len(text)]


def _source_asserted(text,start,end):
    sentence=_source_sentence(text,start,end)
    return not (_quoted_source(text,start,end)or _META_SOURCE.search(sentence)or NEGATED.search(sentence)or _NONFACT.search(sentence))


def _party_source(value,references,turns):
    for reference in references:
        original=turns[reference.source_index].text
        if original.count(reference.quote)!=1:raise InvalidInput('unique original party clause required')
        offset=original.index(reference.quote)
        clause=_source_clause(original,offset,offset+len(reference.quote)).strip().rstrip('.。!！')
        counts={_number(match[1])for match in _PARTY_COUNT.finditer(reference.quote)}
        if _SOLO.search(reference.quote):counts.add(1)
        positive=(_PARTY_STATEMENT.fullmatch(clause)is not None or any(
            positive_trip_support('party_type',clause,match[0])for match in _PARTY_COUNT.finditer(reference.quote)))
        if not positive or not _source_asserted(original,offset,offset+len(reference.quote))or counts!={value}:
            raise InvalidInput('party count differs from its affirmative original source')


def _required_start_anchors(turn):
    text=turn.text
    selection=re.sub(r'^(please\s+)?start my trip\b','start the trip',text.strip(),flags=re.I)
    matches=[match for match,_ in _current_date_anchors(text,turn.question_day)]
    matches.extend(_WEEK_SOURCE.finditer(text))
    return tuple(match for match in matches if date_completion(selection)or
        _START_BEFORE.search(text[:match.start()])or _START_AFTER.match(text[match.end():]))


def _date_resets(text):
    result=[]
    for start,end,clause in _original_clauses(text):
        if (DATE_REFUSAL.fullmatch(clause)or DATES_UNDECIDED.fullmatch(clause))and not _quoted_source(text,start,end):
            result.append((start,end,clause))
    return tuple(result)


def _clock_at(field,original,match,offset=0):
    if match[2]is None and match[3]is None:return None
    start,end=offset+match.start(),offset+match.end()
    if _CLOCK_OFFSET.search(original[max(0,start-24):start]):return None
    if _CLOCK_DENIAL.search(original[max(0,start-24):start]):
        raise InvalidInput('denied or approximate clock is not precise')
    clause=_source_clause(original,start,end)
    event='arrival'if field=='arrival.time'else'departure'
    opposite='departure'if event=='arrival'else'arrival'
    declared=_EVENTS[event].search(clause)
    subject=None if declared is None else re.sub(re.escape(match[0]),'',clause[:declared.start()],count=1).strip()
    if (not _source_asserted(original,start,end)or declared is None or _TRAVELER_SUBJECT.fullmatch(subject)is None or
            _EVENTS[opposite].search(clause)):
        raise InvalidInput('clock requires its affirmative original arrival/departure event')
    return _clock(*match.groups())


def _clock_source(field,value,references,turns):
    for reference in references:
        original=turns[reference.source_index].text
        if original.count(reference.quote)!=1:raise InvalidInput('unique original clock clause required')
        offset=original.index(reference.quote);clocks=set()
        for match in _PRECISE_CLOCK.finditer(reference.quote):
            parsed=_clock_at(field,original,match,offset)
            if parsed is not None:clocks.add(parsed)
        if clocks!={value}:raise InvalidInput('clock differs from its exact original source')


def _place_source(field,value,references,turns):
    """Only an affirmative original endpoint span can seed a provider query."""
    event='arrival'if field=='arrival.place'else'departure'
    opposite='departure'if event=='arrival'else'arrival'
    for reference in references:
        original=turns[reference.source_index].text
        if original.count(reference.quote)!=1 or value not in reference.quote:
            raise InvalidInput('place differs from its literal original source')
        offset=original.index(reference.quote)
        clause=_source_clause(original,offset,offset+len(reference.quote))
        if (not _source_asserted(original,offset,offset+len(reference.quote))or _ENDPOINT_DENIAL.search(clause)or
                _EVENTS[opposite].search(clause)and not _EVENTS[event].search(clause)):
            raise InvalidInput('place requires its affirmative original trip endpoint')


def _edge_option_at(field,value,original,start,end):
    first,last=_source_clause_bounds(original,start,end)
    clause=original[first:last].strip().rstrip('.。!！')
    if field=='first_day_full':
        pattern=_FULL_FIRST if value is True else _LIGHT_FIRST
        if type(value)is not bool or _quoted_source(original,start,end)or pattern.fullmatch(clause)is None:
            raise InvalidInput('explicit full-first-day request required')
        # Explicit light commands carry their own negation. Mask those commands
        # only for sentence assertion selection, retaining the other conditions,
        # meta request and original positions. Their order is validated below.
        context=original
        for begin,finish,command in _original_clauses(original):
            if _LIGHT_FIRST.fullmatch(command)and not _quoted_source(original,begin,finish):
                context=context[:begin]+' '*(finish-begin)+context[finish:]
        if not _source_asserted(context,start,end):raise InvalidInput('unconditional first-day option required')
    else:
        if not _source_asserted(original,start,end):raise InvalidInput('affirmative original edge option required')
        if type(value)is not str or value not in _MODES:raise InvalidInput('explicit flight or train departure required')
        event=_EVENTS['departure'].search(clause)
        subject=None if event is None else _PRECISE_CLOCK.sub('',clause[:event.start()]).strip()
        if (event is None or _TRAVELER_SUBJECT.fullmatch(subject)is None or _EVENTS['arrival'].search(clause)or
                _MODES[value].search(clause)is None or any(pattern.search(clause)for mode,pattern in _MODES.items()if mode!=value)):
            raise InvalidInput('departure mode differs from its original traveler event')


def _edge_option_source(field,value,references,turns):
    for index,quote in references:
        original=turns[index].text
        matches=tuple(re.finditer(re.escape(quote),original))
        if not matches:raise InvalidInput('original edge-option clause required')
        # A repeated identical quote must support the same value at every
        # occurrence. It cannot select just the convenient clause; latest order
        # is separately checked using the actual original positions below.
        for match in matches:_edge_option_at(field,value,original,*match.span())


def _latest_edge_options(value,turns):
    """Later explicit options win; a model omission cannot restore an old one."""
    for field,options in (('departure.mode',('flight','train')),('first_day_full',(True,False))):
        latest=None
        for index,turn in enumerate(turns):
            for position,end,quote in _original_clauses(turn.text):
                for option in options:
                    try:_edge_option_at(field,option,turn.text,position,end)
                    except InvalidInput:continue
                    latest=(index,position,end,option)
        if latest is None:continue
        index,start,end,option=latest
        def covers(reference):
            if reference.source_index!=index:return False
            return any(start<=match.start()and match.end()<=end
                for match in re.finditer(re.escape(reference.quote),turns[index].text))
        if not any(row.field==field and row.state=='known'and type(row.value)is type(option)and row.value==option and
                   any(covers(reference)for reference in row.sources)for row in value.observations):
            raise InvalidInput('latest original edge option was omitted or replaced')


def _latest_event_clocks(value,turns):
    for field in ('arrival.time','departure.time'):
        latest=None
        for index,turn in enumerate(turns):
            for match in _PRECISE_CLOCK.finditer(turn.text):
                try:clock=_clock_at(field,turn.text,match)
                except InvalidInput:continue
                if clock is not None:
                    end=match.end()
                    while end>match.start()and turn.text[end-1]in '. \t':end-=1
                    latest=(index,match.start(),end,clock)
        if latest is None:continue
        index,start,end,clock=latest
        if not any(row.field==field and row.state=='known'and row.value==clock and any(
                reference.source_index==index and any(found.start()<=start and end<=found.end()
                    for found in re.finditer(re.escape(reference.quote),turns[index].text))for reference in row.sources)
                for row in value.observations):
            raise InvalidInput('latest original arrival/departure clock was omitted or replaced')


@dataclass(frozen=True)
class PlanFieldProjection:
    """Data projection only; never a source lease or permission to save."""
    fields:dict
    sources:dict
    start_date:dict
    edge_options:dict


@dataclass(frozen=True)
class _PlanningFieldsData:
    """Shared compiler input data, with no legacy protocol or authority label."""
    extraction:dict
    sources:dict
    start_date:dict
    duration_days:int


def _require_start_sources(value,turns):
    # Explicit original starts cannot disappear or become unknown merely because
    # the model omitted/downgraded its observation. This selects evidence only;
    # the retained date validator still checks the exact original numeric value.
    required_date_index=-1;required_anchors=();start_order=(-1,-1);reset_order=(-1,-1)
    for index,turn in enumerate(turns):
        anchors=_required_start_anchors(turn)
        if anchors:
            required_date_index=index;required_anchors=(max(anchors,key=lambda anchor:anchor.start()),)
            start_order=(index,required_anchors[0].start())
        resets=_date_resets(turn.text)
        if resets:reset_order=(index,resets[-1][0])
    def covers(reference):
        if reference.source_index!=required_date_index:return False
        text=turns[reference.source_index].text
        return any(found.start()<=anchor.start()and anchor.end()<=found.end()
            for found in re.finditer(re.escape(reference.quote),text)for anchor in required_anchors)
    starts=[row for row in value.observations if row.field in ('start_date','arrival.date')]
    if reset_order>start_order:
        if (any(row.state=='known'for row in starts)or not any(row.state=='unknown'and
                any(ref.source_index==reset_order[0]and _date_resets(ref.quote)for ref in row.sources)for row in starts)):
            raise InvalidInput('latest original undecided date must replace the earlier start')
    elif required_date_index>=0 and not any(row.state=='known'and any(covers(ref)for ref in row.sources)for row in starts):
        raise InvalidInput('latest explicit original trip date was omitted by planning understanding')


def prepare_plan_fields(value,turns):
    """City-free data for complete graph preflight, never a source capability.

    Reject omitted explicit dates or fixed declarations before spending on city
    resolution. Full destination, fixed values and window checks still run
    after the actual city result; no timezone or missing calendar is defaulted.
    """
    from .lio_national_intake import fixed_declarations_complete
    _require_start_sources(value,turns)
    projection=project_plan_fields(value)
    if not fixed_declarations_complete(projection.fields,turns,rich_phrases=True):
        raise InvalidInput('complete original fixed declarations required before lookup')
    return projection


def compile_plan_fields(value,turns,*,day_count,city_reference,message_id,run_id):
    """Compile stated fields through the retained literal/window guards.

    day_count/city_reference must come from the protected profile and actual
    registered city result. Their code-default provenance belongs to source4,
    never a fabricated original quote or an old data8 source capability.
    """
    _require_start_sources(value,turns)
    projection=project_plan_fields(value)
    for row in value.observations:
        if row.field not in ('arrival.time','departure.time')or row.state!='known':continue
        for reference in row.sources:
            original=turns[reference.source_index].text;offset=original.index(reference.quote)
            # A following comma does not detach an explicit timezone note.
            # Multiple unresolved zones stay a clarification rather than a
            # model-selected conversion or silently dropped foreign qualifier.
            clause=_source_sentence(original,offset,offset+len(reference.quote))
            zones=[match[0]for match in ZONE_LITERAL.finditer(clause)]
            offsets=[match[0].replace('−','-')for match in _OFFSET_LITERAL.finditer(clause)]
            china=(city_reference.timezone=='Asia/Shanghai'and _CHINA_TIME.search(clause))
            for zone in zones:
                if zone==city_reference.timezone:continue
                if china and zone.upper()in ('UTC+08:00','GMT+08:00','UTC+0800','GMT+0800'):continue
                raise InvalidInput('explicit original clock timezone requires clarification')
            if offsets and not (china and all(value in ('+08:00','+0800')for value in offsets)):
                raise InvalidInput('explicit original clock offset requires clarification')
    for edge in ('arrival','departure'):
        event=projection.fields.get(edge,{})
        if event.get('time',{}).get('state')=='known'and event.get('timezone',{}).get('state')in ('unknown','uncertain'):
            raise InvalidInput('explicitly unresolved local clock timezone requires clarification')
    data=_PlanningFieldsData(dict(version='NEEDS-extraction.1',fields=projection.fields,
        unresolved=[],long_term_requests=[]),projection.sources,projection.start_date,day_count)
    fields,_=fields_for(data,city_reference,message_id=message_id,run_id=run_id,
                        source_text='\n'.join(turn.text for turn in turns))
    beginning=fields['arrival']['date']
    if beginning['state']=='known':
        first=date.fromisoformat(beginning['value'])
        for item in fields['fixed_items']:
            if not any(item[edge]['date']['state']=='missing'for edge in ('start','end')):continue
            try:ordinals=fixed_ordinals(item['description'],day_count)
            except InvalidInput:continue # explicit absolute dates are checked by the retained final guard
            for edge,ordinal in zip(('start','end'),ordinals,strict=True):
                if item[edge]['date']['state']=='missing':
                    item[edge]['date']=dict(state='known',value=(first+timedelta(days=ordinal-1)).isoformat())
    if not fixed_sources_complete(data,fields,turns,city_reference,ordinal_days=day_count,rich_phrases=True):
        raise InvalidInput('complete original fixed values and ordinal windows required')
    return PlanFieldProjection(fields,projection.sources,projection.start_date,projection.edge_options)


def project_plan_fields(value):
    """Preserve missing/unknown data and all supplied fixed rows, without defaults.

    value is the result of parse_plan_understanding. The caller still has to
    compile fixed/day bindings and verify all windows in the genuine source4
    context before NEEDS/publication. This function does not infer a calendar,
    destination timezone, group size or reservation from the profile.
    """
    fields={'party_size':dict(state='missing')};sources={};start=dict(state='missing')
    edge_options={key:dict(state='missing')for key in ('departure.mode','first_day_full')}
    for observation in value.observations:
        state=(dict(state='known',value=observation.value)if observation.state=='known'else
               dict(state='uncertain',note=observation.note)if observation.state=='uncertain'else dict(state='unknown'))
        sources[observation.field]=[ref.model_dump()for ref in observation.sources]
        if observation.field in edge_options:edge_options[observation.field]=state
        elif observation.field=='start_date':start=state
        elif '.'in observation.field:
            event,part=observation.field.split('.')
            fields.setdefault(event,{key:dict(state='missing')for key in ('date','time','timezone','place')})[part]=state
        else:fields[observation.field]=state
    if value.companions:
        fields['companions']={person.companion_id:person.name for person in value.companions}
        sources['companions']=[ref.model_dump()for person in value.companions for ref in person.sources]
    if value.temporary_conditions:
        fields['temporary_conditions']=[dict(condition_id=row.condition_id,applies_to=list(row.applies_to),
            description=row.description)for row in value.temporary_conditions]
        sources['temporary_conditions']=[ref.model_dump()for row in value.temporary_conditions for ref in row.sources]
    fixed=[];primaries=[]
    for index,item in enumerate(value.fixed_items):
        data=item.model_dump()
        values={edge+'_'+part:data[edge+'_'+part]
                for edge in ('start','end')for part in ('date','time','timezone','place')}
        values.update(locked=item.locked,booking_status=None if item.booking_evidence is None else item.booking_evidence.status)
        observed=_observations(values,item.unknown_fields,item.uncertain_fields)
        primary=dict(source_index=item.source_index,quote=item.quote);primaries.append(primary)
        sources['fixed_items.'+str(index)]=[primary,*[ref.model_dump()for ref in item.detail_refs]]
        fixed.append(dict(item_id='fixed-'+sha256(item.quote.encode()).hexdigest()[:20],kind=item.kind,
            description=item.quote,applies_to=list(item.applies_to),locked=observed['locked'],
            booking_status=observed['booking_status'],
            start={part:observed['start_'+part]for part in ('date','time','timezone','place')},
            end={part:observed['end_'+part]for part in ('date','time','timezone','place')}))
    fields['fixed_items']=fixed
    if primaries:sources['fixed_items']=primaries
    validate_fields(fields,complete=True)
    return PlanFieldProjection(fields,sources,start,edge_options)


def original_plan_turns(database,worker,binding,view):
    """Read before model dispatch under the actual M frame, never a new M query."""
    def read():
        values=[]
        for original in view.originals:
            source=worker.message_context.active_source_original(binding,original.message_id)
            actual=read_rich_original(database,binding,source)
            worker.message_context.active_original(binding)
            values.append(PlanningTurn(json.loads(actual.stored.raw)['text'],actual.question_day))
        return tuple(values)
    _,turns=worker._step(binding,read)
    return turns


def parse_plan_understanding(raw,turns):
    try:value=PlanUnderstanding.model_validate(decode(raw.encode()if type(raw)is str else raw))
    except ValidationError as error:raise InvalidInput('complete typed plan understanding required')from error
    if value.current_source_index!=len(turns)-1:
        raise InvalidInput('plan understanding must bind the latest original')

    def check(reference):
        if reference.source_index>=len(turns)or reference.quote not in turns[reference.source_index].text:
            raise InvalidInput('planning quote is not in its original traveler message')

    seen=set()
    for observation in value.observations:
        if observation.field in seen:raise InvalidInput('one explicit planning observation per field required')
        seen.add(observation.field)
        for reference in observation.sources:check(reference)
        if observation.state=='known':
            if observation.value is None or observation.note is not None:
                raise InvalidInput('known observation requires a value without uncertainty')
            if observation.field=='party_size':
                if type(observation.value)is not int or not 1<=observation.value<=100000:
                    raise InvalidInput('explicit bounded party count required')
                _party_source(observation.value,observation.sources,turns)
            elif observation.field in ('departure.mode','first_day_full'):
                _edge_option_source(observation.field,observation.value,
                    tuple((ref.source_index,ref.quote)for ref in observation.sources),turns)
            elif observation.field=='budget_includes':
                if type(observation.value)is not list or not all(type(v)is str and v.strip()for v in observation.value):
                    raise InvalidInput('explicit budget inclusion list required')
            elif type(observation.value)is not str or not observation.value.strip():
                raise InvalidInput('explicit planning text value required')
            if observation.field=='start_date'or observation.field.endswith('.date'):
                if type(observation.value)is not str:raise InvalidInput('explicit ISO date required')
                try:date.fromisoformat(observation.value)
                except ValueError as error:raise InvalidInput('explicit ISO date required')from error
                _current_date_source(observation.value,[ref.model_dump()for ref in observation.sources],turns,
                                     departure=observation.field=='departure.date')
            elif observation.field.endswith('.time'):
                _clock_source(observation.field,observation.value,observation.sources,turns)
            elif observation.field.endswith('.place'):
                _place_source(observation.field,observation.value,observation.sources,turns)
        else:
            if observation.value is not None:raise InvalidInput('unknown planning value cannot also be known')
            if observation.state=='uncertain':
                if not observation.note or not any(observation.note in ref.quote for ref in observation.sources):
                    raise InvalidInput('original planning uncertainty note required')
            elif observation.note is not None:raise InvalidInput('unknown observation has no model uncertainty note')

    companions=set()
    for companion in value.companions:
        if companion.companion_id in companions:raise InvalidInput('distinct declared companions required')
        companions.add(companion.companion_id)
        for reference in companion.sources:check(reference)
        if not companion.name.strip()or not any(companion.name in ref.quote for ref in companion.sources):
            raise InvalidInput('companion name must be an original span')
    originals=[];fixed_keys=set()
    for item in value.fixed_items:
        check(item)
        for reference in item.detail_refs:check(reference)
        key=(item.source_index,item.quote,item.label)
        if key in fixed_keys:raise InvalidInput('distinct original fixed arrangements required')
        fixed_keys.add(key)
        if item.label not in item.quote:raise InvalidInput('fixed label must be an original primary span')
        if len(set(item.applies_to))!=len(item.applies_to):raise InvalidInput('distinct fixed participants required')
        if any(subject.startswith('companion:')and subject[10:]not in companions for subject in item.applies_to):
            raise InvalidInput('fixed companion must be declared by an original name')
        originals.append(item.model_dump())
    for item,original in zip(value.fixed_items,originals,strict=True):
        if item.booking_evidence is not None:
            check(item.booking_evidence)
            _booking_source(original,item.booking_evidence.model_dump(),originals,turns)
    conditions=set()
    for condition in value.temporary_conditions:
        if condition.condition_id in conditions:raise InvalidInput('distinct temporary conditions required')
        conditions.add(condition.condition_id)
        if len(set(condition.applies_to))!=len(condition.applies_to):
            raise InvalidInput('distinct temporary-condition participants required')
        for reference in condition.sources:check(reference)
        if not any(condition.description in ref.quote for ref in condition.sources):
            raise InvalidInput('temporary condition must be an original span')
        if any(subject.startswith('companion:')and subject[10:]not in companions for subject in condition.applies_to):
            raise InvalidInput('temporary-condition companion must be declared')
    _latest_edge_options(value,turns)
    _latest_event_clocks(value,turns)
    return value
