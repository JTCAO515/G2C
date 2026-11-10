"""Derive authoritative itinerary inputs from explicit, bounded declarations."""
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
import re


NUMBERS = dict(zip(('one','two','three','four','five','six','seven','eight','nine','ten'),
                   range(1, 11), strict=True))
NUMBERS.update(zip('一二三四五六七八九十', range(1, 11), strict=True))
NUMBERS['两'] = 2
NUMBER = r'[0-9]{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|[一二两三四五六七八九十]'
PLAN_REQUEST = re.compile(
    r"^\s*(?:(?:(?:请|麻烦)?(?:(?:帮|给|为)(?:我们|我)[^。！？.!?]{0,16}?)?"
    r"(?:规划|(?:安排|设计|做)(?:个|一个|一份)?[^。！？.!?]*(?:行程|日游|天游|旅行|旅游|游玩|攻略))"
    r"|(?:(?:can|could|would) you\s+|please\s+|i(?: would|'d) like you to\s+)?"
    r"(?:help (?:me|us) (?:to )?)?(?:plan|build|create|organize|put together|draft|make)\b"
    r"[^.!?]*\b(?:itinerary|trip|visit|days?\s+in)\b))", re.I,
)
ISO = r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)'
SPAN = re.compile(rf'({ISO})\s*(?:to\b|through\b|到|至|–|—)\s*({ISO})', re.I)
SPAN_TAIL = re.compile(rf'\s*(?:for\s+(?:our party|(?:{NUMBER})\s+people)|[,，]\s*(?:{NUMBER})个人)?\s*', re.I)
TRIP_DATES = re.compile(r'(?:(?:Travel|Trip dates?)\s*(?:from\s*)?|(?:日期|行程日期)\s*[:：]?\s*|'
                        r'(?:Beijing|北京)\s*[,，：:]\s*(?:from\s*|从\s*)?)?'
                        + SPAN.pattern + SPAN_TAIL.pattern, re.I)
DATES_UNDECIDED = re.compile(
    r'\b(?:dates? (?:are|is) undecided|travel dates? (?:are|is) unknown)\b|'
    r'\b(?:suggest|recommend|choose|pick|help me decide)\b[^.?!]{0,32}\bdates?\b|'
    r'日期(?:未定|待定)|(?:推荐|建议|帮我选)[^。！？]{0,12}日期', re.I)
START = re.compile(r'\b(?:starting|beginning|from)\s+(tomorrow|today)\b|从?(明天|今天|后天)(?:开始|起)', re.I)
RELATIVE_REPLY = re.compile(
    rf'(?:Beijing\s*[,，:]\s*)?(?:(?:starting|beginning|from)\s+)?(tomorrow|today)'
    rf'(?:\s*[,，]?\s+for\s+({NUMBER})\s+days?)?'
    rf'|(?:北京\s*[,，：:]\s*)?从?(明天|今天|后天)(?:开始|起)?(?:\s*[,，]?\s*(?:玩|待)?({NUMBER})天)?', re.I,
)
EARLIER_DURATION = re.compile(rf'\b({NUMBER})\s*(?:-day\s+(?:trip|visit|itinerary)|days?\s+(?:in|to|visiting))\b'
                              rf'|北京\s*({NUMBER})天(?:游|行程)|({NUMBER})天的?北京(?:游|行程)', re.I)
ADJACENT_DURATION = re.compile(rf'\s*[,，]?\s*(?:for\s+({NUMBER})\s+days?\b|(?:玩|待)\s*({NUMBER})天)', re.I)
DESTINATION_NEUTRAL = re.compile(r'^(?:please\s+)?(?:plan|make|build|create)\s+(?:a\s+|an\s+)?(?:trip|itinerary)'
                                 r'|^(?:请|帮我|给我)?\s*规划(?:一趟|一次|一个|一份)?(?:旅行|行程)', re.I)
WITHDRAWAL = re.compile(
    r'\b(?:never mind|forget it|scratch that|cancel\b|call (?:it|(?:the|this|that) (?:trip|plan|request)) off)\b|'
    r'\b(?:keep|leave)\s+(?:it|(?:the |this |my )?(?:trip|plan|itinerary))\s+(?:as\s+)?(?:a\s+)?draft\b|'
    r'\b(?:put [^.!?]{0,24} on hold|hold off|pause (?:it|this|the plan|planning))\b|先暂停|暂缓规划|先放一放|'
    r'\b(?:wait for my (?:approval|confirmation)|(?:only after|once) I (?:approve|confirm))\b|'
    r'算了|不用规划了|取消吧|取消(?:这次|这份|这个)?(?:规划|行程|计划)|等我(?:确认|同意|批准)',
    re.I,
)
DRAFT_REQUEST = re.compile(r'^(?:please\s+|(?:can|could|would) you\s+)?(?:help (?:me|us) (?:to )?)?draft\b|(?:只要|先给|先看|看看)[^。！？]{0,12}(?:草稿|预览)', re.I)
SAVE_LANGUAGE = re.compile(r'\b(?:sav(?:e|es|ed|ing)|stor(?:e|es|ed|ing)|persist(?:s|ed|ing)?|'
                           r'publish(?:es|ed|ing)?|writ(?:e|es|ing)\b[^.!?]{0,24}\bdown)\b'
                           r'|保存|存入|存下|存到|记录|写入|发布', re.I)
NONPERSISTENT_SAVE = re.compile(r'\bsav(?:e|ing)\s+(?:time|money)\b', re.I)
SAVE_ASSENT = re.compile(
    r'(?:please\s+)?(?:save|store)\s+(?:it|this|(?:this|the|my)\s+(?:trip|plan|itinerary))'
    r'(?:\s+(?:to|in)\s+(?:my account|my trips|the trips tab))?'
    r'|(?:请\s*)?(?:把(?:这份|这个|我的)?行程)?保存(?:这份行程|这个行程|行程|到行程页)?',
    re.I,
)
SAVE_JOIN = re.compile(r'\s+(?:and|then)\s+|[，,]?\s*(?:并|然后)', re.I)
PARTY = re.compile(rf'\bfor\s+({NUMBER})\s+(?:people|persons?)\b|({NUMBER})\s*(?:个人|人)', re.I)
DESTINATION = re.compile(r'\b(?:itinerary|trip|days?)\s+(?:in|to)\s+Beijing\b|'
                         r'\bBeijing\s+(?:itinerary|trip|visit)\b|'
                         r'(?:去|到|在)北京|北京(?:\s*[，,：:]|[一二两三四五六七八九十\d]+天|游|行程)', re.I)
PRIMARY_DESTINATION = re.compile(r'\b(?:itinerary|trip|days?)\s+(?:in|to)\s+([A-Za-z]+)\b', re.I)
NAMED_BEIJING = re.compile(r'\bBeijing\s+(?:itinerary|trip|visit)\b', re.I)
ZH_DIRECT = re.compile(rf'(?:规划|安排|设计|做)\s*(?:一下|一个|一份)?\s*(?:(?:{NUMBER})天的?)?(?:去|到|在)?北京')
ZH_RELATIVE = re.compile(r'(?:规划|安排|设计|做)\s*从?(?:明天|今天|后天)(?:开始|起)的?北京')
ZH_RELATIVE_TAIL = re.compile(rf'\s*的?北京\s*(?:{NUMBER})天(?:游|行程|旅行)\s*(?:[,，]\s*(?:{NUMBER})个人)?\s*')
POLITE_PLAN_QUESTION = re.compile(r'^(?:can|could|would) you\s+', re.I)
OPEN_PLAN = re.compile(
    r"(?:(?:can|could|would) you\s+|please\s+|i(?: would|'d) like you to\s+)?"
    rf'(?:help (?:me|us) (?:to )?)?(?:plan|build|create|organize|put together|draft|make)\s+'
    rf'(?:(?:a\s+|an\s+)?(?:(?:{NUMBER})-day\s+)?(?:Beijing\s+)?(?:trip|itinerary|visit)'
    rf'(?:\s+(?:in|to)\s+Beijing)?|(?:{NUMBER})\s+days?\s+in\s+Beijing)'
    rf'(?:\s+for\s+(?:our party|(?:{NUMBER})\s+(?:people|days?)))?'
    rf'|(?:请|麻烦)?(?:(?:帮|给|为)(?:我们|我))?\s*(?:(?:为|给)(?:{NUMBER})个人)?\s*(?:规划|安排|设计|做)\s*'
    rf'(?:一下|一个|一份|一趟|一次)?\s*(?:(?:{NUMBER})天的?)?(?:(?:去|到|在)?北京)?\s*'
    rf'(?:(?:{NUMBER})天)?(?:旅行|行程|日游|游|旅游|攻略)'
    rf'|(?:请|麻烦)?(?:帮我|给我|帮我们)?\s*规划(?:一趟|一次|一个|一份)?(?:旅行|行程)', re.I)

EN_CONFIRMED_DATE_SCOPE = re.compile(
    r'(?:trip dates?|travel dates?|(?:those|these|the|that)\s+(?:dates?|days?|departure(?: date| day)?|start(?: date| day)?))'
    r'\s+(?:(?:are|is|were)\s+(?:only\s+)?for|apply(?:\s+only)?\s+to|belong(?:s)?\s+to)'
    r'\s+(?:Beijing|北京)(?:\s+only)?',re.I)
ZH_CONFIRMED_DATE_SCOPE = re.compile(
    r'(?:日期|这些日期|那些日期|这几天|明天|今天|后天|出发日)'
    r'(?:(?:只用于|仅用于|只适用于|仅限|适用于|属于)北京|是北京的(?:出发日|出发日期|旅行日期|行程|旅行|计划))')
EN_DATE_SCOPE = re.compile(
    r'\b(?:trip dates?|travel dates?|(?:those|these|the|that)\s+(?:dates?|days?|departure(?: date| day)?|start(?: date| day)?))'
    r'\b[^.!?]{0,96}?(?:\b(?:(?:are|is|were|was)\s+(?:not\s+)?(?:only\s+)?for|'
    r'belong(?:s)?\s+to|apply(?:\s+only)?\s+to)\s+|[:：]\s*)(?P<target>[^.!?]+)', re.I)
ZH_DATE_SCOPE = re.compile(
    r'(?:日期|那些天|这些天|这几天|明天|今天|后天|出发日)[^。？！]{0,40}?'
    r'(?:(?:只用于|仅用于|只适用于|仅限|适用于|属于)(?P<direct>[^。？！]+)'
    r'|是(?P<described>[^。？！]+?)的(?:出发日|出发日期|旅行日期|行程|旅行|计划))')

TRIP_PARTY_GAP = rf'\s*(?:for\s+(?:{NUMBER})\s+people\s+)?'
OTHER_DESTINATION = re.compile(r'\bfrom\s+Beijing\s+to\b|从北京(?:去|到)', re.I)
CITY_REPLY = re.compile(r'^(?:Beijing|北京)(?=$|[,，：:]|\s+(?:\d{4}-|from\b|从|明天|今天))', re.I)
FIXED = re.compile(r'已经定好|固定安排|已锁定|已预订|已订|已买票|已经买票|已预约|已经预约|不可更改|不能改|'
                   r'\b(?:is fixed|already set|already booked|have (?:actually )?booked|'
                   r'has booked|is booked|must keep|cannot be changed|(?:we|i) have tickets? (?:to|for))\b', re.I)
NEGATED = re.compile(
    r"\b(?:not|never|cancel|without|if|whether|maybe|might|suppose|assuming|in case|hypothetically)\b"
    r"|n['’]t\b|还没|没有|未订|不再|不要|取消|如果|可能|不确定|假如|假设|要是|倘若", re.I)
OTHER = re.compile(r'孩子|女儿|儿子|母亲|父亲|同伴|家人|\b(?:daughter|son|mother|father|friend|guest)\b', re.I)
CLOCK = r'(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?'
RANGE = re.compile(rf'{CLOCK}\s*(?:[-–—到至]|\bto\b)\s*{CLOCK}', re.I)
CLAUSE_BREAK = re.compile(r'[!。！；;\n]+|(?<=[?？])\s*|\.(?=\s+[A-Z])|，(?=\s*(?:第[一二三四五六七八九十\d]+天|酒店集合))')
FIXED_REPLY = re.compile(r'^(?:全体|大家|本人|我参加|第[一二三四五六七八九十\d]+天|'
                         r'(?:for (?:everyone|our party|both of us)|on (?:the first day|\d{4}-))\b)', re.I)
FIXED_PARTY_REPLY = re.compile(r'全体(?:参加)?|大家(?:参加)?|本人|我参加|for (?:everyone|our party|both of us)', re.I)
EN_FIXED_EVENT = (
    r'(?:(?:the|my|our|a|an)\s+)?'
    r'(?:(?:hotel|airport|train|flight|museum|restaurant|park|entry)\s+){0,3}'
    r'(?:meetup|meeting|appointment|reservation|booking|transfer|visit|tickets?|flight|train|departure|check-in|museum)')
EN_FIXED_DAY = r'(?:on\s+)?(?:the\s+first\s+day|@date)'
EN_FIXED_TIME = r'(?:from\s+)?@time'
EN_FIXED_LOCK = r'(?:is fixed|is booked|already booked|is already booked|is already set|cannot be changed)'
EN_FIXED_DECLARATION = re.compile(
    rf'{EN_FIXED_EVENT}\s+(?:(?:{EN_FIXED_TIME}\s+{EN_FIXED_DAY}|{EN_FIXED_DAY}\s+{EN_FIXED_TIME})\s+)?{EN_FIXED_LOCK}'
    rf'|(?:we|i)\s+(?:have tickets? (?:for|to)|have (?:already |actually )?booked)\s+{EN_FIXED_EVENT}'
    rf'\s+(?:{EN_FIXED_DAY}\s+{EN_FIXED_TIME}|{EN_FIXED_TIME}\s+{EN_FIXED_DAY})',re.I)
EN_FIXED_DETAILS = re.compile(
    rf'(?:for (?:everyone|our party|both of us)\s*[,，]\s*)?'
    rf'(?:{EN_FIXED_DAY}\s+{EN_FIXED_TIME}|{EN_FIXED_TIME}\s+{EN_FIXED_DAY})',re.I)
ZH_FIXED_DAY = r'(?:第[一二三四五六七八九十\d]+天|@date)'
ZH_FIXED_DECLARATION = re.compile(
    rf'(?:{ZH_FIXED_DAY}\s*@time\s*的?)?\s*'
    r'(?:酒店集合|机场集合|车站集合|集合|预约|门票|酒店预订|会面|会议|航班|火车|接送)'
    r'(?:已经定好|已定好|是固定安排|固定安排|已锁定|已经预订|已预订|已订|已买票|已经买票|已预约|已经预约|不可更改|不能改)')
ZH_FIXED_DETAILS = re.compile(rf'(?:(?:全体|大家|本人|我参加)\s*[,，]\s*)?{ZH_FIXED_DAY}\s*@time')



def _clauses(text):
    return tuple(clause.strip().rstrip('.') for clause in CLAUSE_BREAK.split(text) if clause.strip())


def _number(value):
    return int(value) if value.isascii() and value.isdigit() else NUMBERS[value.lower()]


def _planning_without_assent(clause):
    for separator in SAVE_JOIN.finditer(clause):
        plan = clause[:separator.start()]
        if (PLAN_REQUEST.match(plan) and not NEGATED.search(plan)
                and not SAVE_LANGUAGE.search(NONPERSISTENT_SAVE.sub('', plan))
                and SAVE_ASSENT.fullmatch(clause[separator.end():])):
            return plan
    return None


def planning_withdrawn(text):
    clauses = _clauses(text)
    if any(DRAFT_REQUEST.search(clause) for clause in clauses) and not any(
            SAVE_ASSENT.fullmatch(clause) or _planning_without_assent(clause) is not None for clause in clauses):
        return True
    for clause in clauses:
        if WITHDRAWAL.search(clause):
            return True
        if not SAVE_LANGUAGE.search(NONPERSISTENT_SAVE.sub('', clause)):
            continue
        if not SAVE_ASSENT.fullmatch(clause) and _planning_without_assent(clause) is None:
            return True
    return False


def _relative_span(word, duration, today):
    offset = {'tomorrow':1,'明天':1,'后天':2,'today':0,'今天':0}[word.lower()]
    first = today + timedelta(days=offset)
    return first, first + timedelta(days=duration-1)


def _date_declaration(clause):
    if not clause.endswith(('?', '？')):
        return clause
    if POLITE_PLAN_QUESTION.match(clause) and PLAN_REQUEST.match(clause):
        return clause[:-1].rstrip()
    return None


def _date_scope_disputed(turn, city):
    if city is None:
        return False
    destinations = {'北京', 'beijing'} if city.casefold() in ('北京', 'beijing') else {city.casefold()}
    for clause in _clauses(turn):
        english = EN_DATE_SCOPE.search(clause)
        chinese = ZH_DATE_SCOPE.search(clause)
        if english is None and chinese is None:
            continue
        if NEGATED.search(clause):
            return True
        target = english['target'] if english is not None else chinese['direct'] or chinese['described']
        target = re.sub(r'^only\s+|\s+only$', '', target.strip(), flags=re.I)
        if target.rstrip('。？！?!').strip().casefold() not in destinations:
            return True
    return False


def _declared_duration(turns, city=None):
    durations = set()
    for turn in turns:
        if _date_scope_disputed(turn, city):
            durations.clear()
            continue
        for original in _clauses(turn):
            clause = _date_declaration(original)
            if clause is None or not PLAN_REQUEST.match(clause) or NEGATED.search(clause):
                continue
            primary = PRIMARY_DESTINATION.search(clause)
            for match in EARLIER_DURATION.finditer(clause):
                if primary is None or match.start() <= primary.start():
                    durations.add(_number(match[1] or match[2] or match[3]))
            if primary is not None:
                after_destination = ADJACENT_DURATION.match(clause, primary.end())
                if after_destination is not None:
                    durations.add(_number(after_destination[1] or after_destination[2]))
    return durations.pop() if len(durations) == 1 else None


def _known(value):
    return dict(state='known', value=value) if value is not None else dict(state='missing')


def stated_city(turns, city):
    if city.casefold() not in ('beijing', '北京'):
        return any(city in clause and PLAN_REQUEST.match(clause) and not NEGATED.search(clause)
                   for turn in turns for clause in _clauses(turn))
    for turn in turns:
        for clause in _clauses(turn):
            if (city not in clause or not PLAN_REQUEST.match(clause) or not DESTINATION.search(clause)
                    or NEGATED.search(clause) or OTHER_DESTINATION.search(clause)):
                continue
            primary = PRIMARY_DESTINATION.search(clause)
            if city == '北京' and not (ZH_DIRECT.search(clause) or ZH_RELATIVE.search(clause)):
                continue
            if primary is None or primary[1].casefold() == 'beijing':
                return True
    return len(turns) > 1 and any(city in clause and CITY_REPLY.match(clause) and not NEGATED.search(clause)
                                 for clause in _clauses(turns[-1]))


@dataclass(frozen=True)
class PlanningTurn:
    text: str
    question_day: date


def _compatible_turns(turns, city):
    if city is None:
        return turns
    retained = []
    waiting_for_city = False
    for turn in turns:
        compatible = []
        for clause in _clauses(turn.text):
            clause = _planning_without_assent(clause) or clause
            named = stated_city((clause,), city)
            if PLAN_REQUEST.match(clause) and not named and not DESTINATION_NEUTRAL.fullmatch(clause):
                retained.clear()
                compatible.clear()
                waiting_for_city = True
                continue
            if named or (city in clause and CITY_REPLY.match(clause) and not NEGATED.search(clause)):
                waiting_for_city = False
            if not waiting_for_city:
                compatible.append(clause)
        if compatible:
            retained.append(PlanningTurn('\n'.join(compatible), turn.question_day))
    return tuple(retained)


def _timing_follows_destination(clause, position, *, absolute):
    primary = PRIMARY_DESTINATION.search(clause)
    destination = primary or NAMED_BEIJING.search(clause) or ZH_DIRECT.search(clause)
    if destination is None or destination.end() > position:
        return False
    gap = clause[destination.end():position]
    expected = TRIP_PARTY_GAP + (r'(?:from|从|在)\s*' if absolute
                                else rf'(?:for\s+(?:{NUMBER})\s+days?\s+)?')
    return re.fullmatch(expected, gap, re.I) is not None


def _day_span(turns, city):
    if len(turns) > 1:
        latest = turns[-1]
        reply = RELATIVE_REPLY.fullmatch(latest.text.strip().rstrip('.。！!'))
        if reply is not None:
            count = reply[2] or reply[4]
            duration = _number(count) if count else _declared_duration(tuple(turn.text for turn in turns[:-1]), city)
            if not duration:
                return None, None
            return _relative_span(reply[1] or reply[3], duration, latest.question_day)
    for turn in reversed(turns):
        if DATES_UNDECIDED.search(turn.text) or _date_scope_disputed(turn.text, city):
            return None, None
        spans = set()
        for original in _clauses(turn.text):
            clause = _date_declaration(original)
            if clause is None or NEGATED.search(clause) or FIXED.search(clause):
                continue
            date_reply = TRIP_DATES.fullmatch(clause)
            if not (PLAN_REQUEST.match(clause) or date_reply):
                continue
            try:
                explicit = tuple(SPAN.finditer(clause))
                for match in explicit:
                    scoped = date_reply is not None or (
                        _timing_follows_destination(clause, match.start(), absolute=True)
                        and SPAN_TAIL.fullmatch(clause[match.end():]) is not None)
                    if scoped:
                        spans.add((date.fromisoformat(match[1]), date.fromisoformat(match[2])))
                if explicit:
                    continue
                start = START.search(clause)
                if start is None:
                    continue
                tail = clause[start.end():]
                if ZH_RELATIVE.search(clause):
                    if not ZH_RELATIVE_TAIL.fullmatch(tail):
                        continue
                    duration = _declared_duration((clause,))
                elif _timing_follows_destination(clause, start.start(), absolute=False):
                    suffix = ADJACENT_DURATION.match(clause, start.end())
                    if not SPAN_TAIL.fullmatch(clause[suffix.end():] if suffix else tail):
                        continue
                    duration = _number(suffix[1] or suffix[2]) if suffix else _declared_duration((clause,))
                else:
                    continue
                if duration:
                    spans.add(_relative_span(start[1] or start[2], duration, turn.question_day))
            except ValueError:
                return None, None
        if spans:
            if len(spans) == 1:
                first, last = spans.pop()
                if first <= last:
                    return first, last
            return None, None
    return None, None


def _fixed_authority_clause(clause):
    normalized = ' '.join(RANGE.sub(' @time ', re.sub(ISO, ' @date ', clause)).split())
    return any(pattern.fullmatch(normalized) for pattern in (
        FIXED_PARTY_REPLY, EN_FIXED_DECLARATION, EN_FIXED_DETAILS, ZH_FIXED_DECLARATION, ZH_FIXED_DETAILS,
    ))


def _timed_plan_authorized(clause, city, today):
    if _day_span((PlanningTurn(clause, today),), city)[0] is None:
        return False
    span = SPAN.search(clause)
    if span is not None:
        prefix = re.sub(r'(?:\bfrom|从|在)\s*$', '', clause[:span.start()], flags=re.I).rstrip(' ,，')
        return OPEN_PLAN.fullmatch(prefix) is not None
    start = START.search(clause)
    if start is None:
        return False
    if ZH_RELATIVE.search(clause):
        remaining = clause[:start.start()] + clause[start.end():].lstrip('的 ')
        return OPEN_PLAN.fullmatch(remaining) is not None
    return OPEN_PLAN.fullmatch(clause[:start.start()].rstrip(' ,，')) is not None


def planning_authority_complete(turns, city, *, has_fixed):
    """A grounded date does not authorize an unexplained instruction in the same turn."""
    # Historical details may be dropped when the city changes. The latest
    # original must still be evaluated in full, even before its new destination.
    latest = turns[-1]
    latest_text = '\n'.join(_planning_without_assent(clause) or clause for clause in _clauses(latest.text))
    for turn in (*_compatible_turns(turns[:-1], city), PlanningTurn(latest_text, latest.question_day)):
        for original in _clauses(turn.text):
            clause = _date_declaration(original)
            if clause is None:
                return False
            if (clause.casefold() in ('北京', 'beijing') or OPEN_PLAN.fullmatch(clause)
                    or SAVE_ASSENT.fullmatch(clause) or RELATIVE_REPLY.fullmatch(clause)
                    or TRIP_DATES.fullmatch(clause)):
                continue
            if city.casefold() in ('北京', 'beijing') and (EN_CONFIRMED_DATE_SCOPE.fullmatch(clause)
                    or ZH_CONFIRMED_DATE_SCOPE.fullmatch(clause)):
                continue
            if has_fixed and _fixed_authority_clause(clause):
                continue
            if PLAN_REQUEST.match(clause) and _timed_plan_authorized(clause, city, turn.question_day):
                continue
            return False
    return True


def _clock(hour, minute, meridiem):
    h, m = int(hour), int(minute or '0')
    if meridiem is not None:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if meridiem[0].lower() == 'p' else 0)
    if not 0 <= h < 24 or not 0 <= m < 60:
        return None
    return f'{h:02d}:{m:02d}'


def _event(day, *, time=None, zone=None, place=None):
    return dict(date=_known(day.isoformat() if day else None), time=_known(time),
                timezone=_known(zone), place=_known(place))


def _fixed_item(clause, first, zone, party, *, reply=''):
    details = f'{clause}\n{reply}' if reply else clause
    if NEGATED.search(details) or OTHER.search(details) or zone is None:
        return None
    ranges = {match.groups() for match in RANGE.finditer(re.sub(ISO, ' ', details))}
    try:
        dates = {date.fromisoformat(value) for value in re.findall(ISO, details)}
    except ValueError:
        return None
    if first and re.search(r'第一天|\b(?:the )?first day\b', details, re.I):
        dates.add(first)
    if len(ranges) != 1 or len(dates) != 1:
        return None
    day = dates.pop()
    start_h, start_m, start_meridiem, end_h, end_m, end_meridiem = ranges.pop()
    start = _clock(start_h, start_m, start_meridiem or end_meridiem)
    end = _clock(end_h, end_m, end_meridiem or start_meridiem)
    if not start or not end or end <= start:
        return None
    if re.search(r'全体|大家|\b(?:for our party|for everyone|for both of us|we have tickets?)\b', details, re.I):
        subject = 'party'
    elif re.search(r'本人|我参加|\b(?:for myself|for me only|only me)\b', details, re.I):
        subject = 'self'
    elif party is not None and not re.search(r'我的|他的|她的|\b(?:my|your|their|his|her)\b', clause, re.I):
        subject = 'party'
    else:
        return None
    return dict(item_id='fixed-'+sha256(clause.encode()).hexdigest()[:20], kind='appointment',
                description=clause, applies_to=[subject], locked=_known(True),
                booking_status=dict(state='unknown'), start=_event(day, time=start, zone=zone),
                end=_event(day, time=end, zone=zone))


def grounded_fields(turns, city):
    turns = _compatible_turns(turns, city)
    clauses = tuple(clause for turn in turns for clause in _clauses(turn.text))
    first, last = _day_span(turns, city)
    parties = {_number(match[1] or match[2]) for clause in clauses
               if PLAN_REQUEST.match(clause) and not NEGATED.search(clause)
               for match in PARTY.finditer(clause)}
    party = parties.pop() if len(parties) == 1 else None
    zone = 'Asia/Shanghai' if city and city.casefold() in ('北京', 'beijing') else None
    fixed_clauses = tuple(dict.fromkeys(clause for clause in clauses if FIXED.search(clause)))
    fixed_items = [_fixed_item(clause, first, zone, party) for clause in fixed_clauses]
    if len(turns) > 1 and fixed_items.count(None) == 1:
        reply = turns[-1].text.strip()
        if FIXED_REPLY.match(reply) and not FIXED.search(reply):
            index = fixed_items.index(None)
            fixed_items[index] = _fixed_item(fixed_clauses[index], first, zone, party, reply=reply)
    result = dict(arrival=_event(first, zone=zone, place=city), departure=_event(last, zone=zone))
    if party:
        result['party_size'] = _known(party)
    if fixed_items and all(item is not None for item in fixed_items):
        result['fixed_items'] = fixed_items
    return result, None in fixed_items
