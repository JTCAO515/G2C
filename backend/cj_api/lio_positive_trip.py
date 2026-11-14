"""Finite positive trip syntax; never infer a fact from a keyword occurrence."""
import re

from .lio_planning_grounding import NUMBERS

_NUMBER=r'(?:[0-9]{1,3}|[一二两三四五六七八九十]|one|two|three|four|five|six|seven|eight|nine|ten)'
_WEEKDAY=r'(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
_DATE=(r'(?:[0-9]{2}(?:[0-9]{2})?[./-][0-9]{1,2}[./-][0-9]{1,2}|'
       r'(?:[0-9]{2}(?:[0-9]{2})?年)?[0-9]{1,2}月[0-9]{1,2}[日号]?|'
       r'大后天|后天|明天|今天|(?:下+|本|这)(?:周|星期|礼拜)[一二三四五六天日]|'
       r'next\s+'+_WEEKDAY+r'|tomorrow|today|'
       r'in\s+'+_NUMBER+r'\s+days?|'+_NUMBER+r'天(?:之|以)?后)')
_KNOWN_CITIES={'北京','上海','成都','杭州','西安','beijing','shanghai','chengdu','hangzhou',"xi'an"}


def known_city_term(query):return query.casefold() in _KNOWN_CITIES


def supports(key,clause,quote,*,registered_city_terms=()):
    if key not in ('city','duration_days','party_type'):return False
    # Only the source-owned catalogue is eligible. Model-proposed strings must
    # never become grammar tokens: a proposed city "not" could swallow negation.
    cities=tuple(sorted(_KNOWN_CITIES|set(registered_city_terms),key=len,reverse=True))
    city_pattern='|'.join(re.escape(city) for city in sorted(cities,key=len,reverse=True)) or r'(?!)'
    token=re.compile(
        r'(?P<request>规划|计划|安排|设计|我想去|我们想去|想去|要去|去|'
        r'(?:(?:can|could) you\s+|please\s+)?(?:plan|organize|create)\b|(?:I|we) (?:want|would like) to (?:visit|go to)\b)'
        r'|(?P<date>'+_DATE+r')'
        r'|(?P<duration>'+_NUMBER+r'\s*(?:天|日)|'+_NUMBER+r'\s+days?)'
        r'|(?P<party>'+_NUMBER+r'\s*(?:个人|人)|'+_NUMBER+r'\s+(?:people|persons?|adults?))'
        r'|(?P<city>'+city_pattern+r')'
        r'|(?P<link>请|帮我|麻烦|一份|一个|玩|豪华游|豪华|旅行|旅游|行程|游|出发|开始|一起|出行|从|'
        r'\b(?:in|to|for|from|starting|start|luxury|trip|itinerary|travel|with|departing)\b)',re.I)
    position=0;found={'city':[],'duration':[],'party':[]};requested=False
    while position<len(clause):
        separator=re.match(r'[\s、，,。;；.!！]+',clause[position:])
        if separator:position+=separator.end();continue
        if clause[position:] in ('?','？') and requested:break
        match=token.match(clause,position)
        if match is None:return False
        if match.lastgroup=='request':requested=True
        if match.lastgroup in found:found[match.lastgroup].append(match[0])
        position=match.end()
    if len(set(city.casefold() for city in found['city']))>1:return False
    if found['city'] and not requested and found['city'][0].casefold() not in {city.casefold()for city in cities}:return False
    if key=='city':return len(found['city'])==1 and found['city'][0].casefold()==quote.casefold()
    if key=='duration_days':
        counts=[]
        for word in found['duration']:
            number=re.match(_NUMBER,word,re.I)[0]
            counts.append(int(number) if number.isascii() and number.isdecimal() else NUMBERS[number.casefold()])
        return bool(counts) and len(set(counts))==1 and quote.casefold() in {word.casefold() for word in found['duration']}
    return len(found['party'])==1 and found['party'][0].casefold()==quote.casefold()
