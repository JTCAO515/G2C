"""Unconfirmed extraction data, separate from manual NEEDS revisions and Memory."""
import base64
from hashlib import sha256
import json
import re

from .domain import InvalidInput, decode, exact, text, validate_fields

MODEL_VERSION='NEEDS-extraction.1'
PREVIEW_VERSION='NEEDS-preview.1'
QUESTIONS={
    ('budget_basis','missing_basis'):('预算金额是总计还是每人？','Is the budget amount total or per person?'),
    ('budget_paid','currency_mismatch'):('已付金额与预算的币种口径尚未明确，请核对。','Confirm the currency basis of the paid amount and budget.'),
    ('temporary_conditions','unclear_lifetime'):('这条条件只用于本次旅行，还是需要另行确认长期保存？','Does this condition apply to this trip, or need separate confirmation for long-term memory?'),
    ('fixed_items','missing_subject'):('这项固定安排适用于本人、全体还是哪位同伴？','Does this fixed arrangement apply to you, the party, or a specific companion?'),
}


def encode(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')


def preview(raw, *, message_id, run_id, source_text):
    value=decode(raw)
    exact(value,('version','fields','unresolved','long_term_requests'))
    if value['version']!=MODEL_VERSION:raise InvalidInput('unsupported NEEDS extraction version')
    validate_fields(value['fields'],complete=True)
    if type(value['unresolved']) is not list or len(value['unresolved'])>8:
        raise InvalidInput('bounded unresolved NEEDS fields required')
    questions=[]
    for item in value['unresolved']:
        exact(item,('field','reason','original_text'))
        text(item['original_text'])
        if item['original_text'] not in source_text:raise InvalidInput('unbound NEEDS clarification source')
        if type(item['field']) is not str or type(item['reason']) is not str:
            raise InvalidInput('invalid NEEDS clarification')
        pair=(item['field'],item['reason'])
        if pair not in QUESTIONS:raise InvalidInput('unsupported NEEDS clarification')
        if pair==('budget_basis','missing_basis') and value['fields'].get('budget_basis',{}).get('state')=='known':
            raise InvalidInput('known budget basis must not be questioned')
        zh,en=QUESTIONS[pair]
        questions.append(dict(field=item['field'],reason=item['reason'],text_zh=zh,text_en=en))
    if type(value['long_term_requests']) is not list or len(value['long_term_requests'])>8:
        raise InvalidInput('bounded long-term requests required')
    for request in value['long_term_requests']:
        text(request)
        if request not in source_text:raise InvalidInput('unbound long-term request')
    original=source_text.encode('utf8')
    result=encode(dict(version=PREVIEW_VERSION,data_origin='synthetic',confirmation='unconfirmed',
        source_kind='unconfirmed_extraction',source=dict(message_id=message_id,run_id=run_id,
            text_utf8_base64=base64.b64encode(original).decode('ascii'),text_sha256=sha256(original).hexdigest()),
        fields=value['fields'],unresolved=value['unresolved'],questions=questions,
        deferred_memory_requests=value['long_term_requests'],
        text_zh='请核对提取值；这些改动尚未保存到本次需求或长期记忆。',
        text_en='Check the extracted values. These changes have not been saved to your trip requirements or long-term memory.'))
    if len(result)>131072:raise InvalidInput('NEEDS preview output bound exceeded')
    return result


def _known(value):return dict(state='known',value=value)
def _missing():return dict(state='missing')
def _empty_event():return {key:_missing() for key in ('date','time','timezone','place')}
def _id(kind,clause):return kind+'-'+sha256(clause.encode('utf8')).hexdigest()[:16]


def synthetic_extract(source):
    """Limited explicit synthetic statements; not a real-model quality claim."""
    fields={};unresolved=[];long_term=[];coverage=[];items=[];conditions=[];companions={}
    def unresolved_field(field,reason,clause):
        unresolved.append(dict(field=field,reason=reason,original_text=clause))
    for clause in re.split(r'[;；。\n]',source):
        clause=clause.strip()
        if not clause:continue
        if re.match(r'(?i)(remember\b|请记住|长期记住)',clause):
            long_term.append(clause);continue
        party=re.fullmatch(r'(?i)(?:we are|party of|party size)\s+(\d+)|(?:本次)?(\d+)人',clause)
        if party:fields['party_size']=_known(int(party[1] or party[2]));continue
        if re.fullmatch(r'(?i)dates undecided|日期未定',clause):
            for key in ('arrival','departure'):
                fields[key]=dict(_empty_event(),date={'state':'unknown'})
            continue
        budget=re.match(r'(?i)(?:budget|预算)\s*(USD|CNY|EUR)\s*(\d+(?:\.\d+)?)(?![0-9.])(.*)',clause)
        if budget:
            currency,amount,basis=budget.groups()
            fields['budget_currency']=_known(currency.upper())
            per=bool(re.search(r'(?i)per person|每人',basis));total=bool(re.search(r'(?i)\btotal\b|总计',basis))
            if per!=total:
                fields['budget_basis']=_known('per_person' if per else 'total')
                fields['budget_per_person' if per else 'budget_total']=_known(amount)
            else:
                fields['budget_basis']={'state':'unknown'}
                unresolved_field('budget_basis','missing_basis',clause)
            continue
        paid=re.fullmatch(r'(?i)(?:paid|已付)\s*(USD|CNY|EUR)\s*(\d+(?:\.\d+)?)',clause)
        if paid:
            if fields.get('budget_currency',{}).get('value')==paid[1].upper():
                fields['budget_paid']=_known(paid[2])
            else:
                fields['budget_paid']=dict(state='uncertain',note=clause)
                unresolved_field('budget_paid','currency_mismatch',clause)
            continue
        if re.match(r'(?i)^(includes\b|excludes\b|含|包含|不含)',clause):
            coverage.append(clause);continue
        event=re.fullmatch(r'(?i)(overseas departure|海外出发|arrival|抵达|departure|离境)\s*(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}))?(?:\s+([A-Za-z_]+/[A-Za-z_]+(?:/[A-Za-z_]+)?))?',clause)
        if event:
            label,day,hour,zone=event.groups()
            name={'overseas departure':'overseas_departure','海外出发':'overseas_departure','arrival':'arrival','抵达':'arrival','departure':'departure','离境':'departure'}[label.lower()]
            value=_empty_event();value['date']=_known(day)
            if hour is not None:value['time']=_known(hour)
            if zone is not None:value['timezone']=_known(zone)
            fields[name]=value;continue
        fixed=re.match(r'(?i)^(booked hotel|已订酒店|fixed appointment|固定预约|fixed transport|固定交通)(?![A-Za-z])(.*)',clause)
        if fixed:
            label,detail=fixed.groups();subject=None
            if re.search(r'(?i)for party|全体',detail):subject='party'
            elif re.search(r'(?i)for self|本人',detail):subject='self'
            elif re.search(r'(?i)for mother|母亲',detail):
                subject='companion:mother';companions['mother']='mother / 母亲'
            if subject is None:
                unresolved_field('fixed_items','missing_subject',clause);continue
            kind='hotel' if label.lower() in ('booked hotel','已订酒店') else 'appointment' if label.lower() in ('fixed appointment','固定预约') else 'transport'
            start=_empty_event()
            at=re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s+([A-Za-z_]+/[A-Za-z_]+(?:/[A-Za-z_]+)?)',detail)
            if at:start.update(date=_known(at[1]),time=_known(at[2]),timezone=_known(at[3]))
            items.append(dict(item_id=_id(kind,clause),kind=kind,description=clause,applies_to=[subject],
                locked=_known(True) if label.lower().startswith('fixed') or label.startswith('固定') else _missing(),
                booking_status=_known('booked') if kind=='hotel' else _missing(),start=start,end=_empty_event()))
            continue
        temporary=re.fullmatch(r'(?i)this trip (mother|I|party) (has a leg injury|avoid spicy)|本次(母亲|本人|全体)(腿伤|不吃辣)',clause)
        if temporary:
            person=(temporary[1] or temporary[3]).lower()
            subject='companion:mother' if person in ('mother','母亲') else 'party' if person in ('party','全体') else 'self'
            if subject=='companion:mother':companions['mother']='mother / 母亲'
            conditions.append(dict(condition_id=_id('temporary',clause),applies_to=[subject],description=clause));continue
        if re.fullmatch(r'(?i)I (?:do not|don\x27t) eat spicy|我不吃辣',clause):
            unresolved_field('temporary_conditions','unclear_lifetime',clause)
    if coverage:fields['budget_includes']=_known(coverage)
    if items:fields['fixed_items']=items
    if conditions:fields['temporary_conditions']=conditions
    if companions:fields['companions']=companions
    return encode(dict(version=MODEL_VERSION,fields=fields,unresolved=unresolved,long_term_requests=long_term))
