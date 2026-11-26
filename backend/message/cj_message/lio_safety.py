"""Safety must-include lines for Lio answers (W2-6, #1733).

For four kinds of question (emergency first aid, lost documents, seeing a doctor,
dietary restrictions) an answer must contain a few essentials. With
CJ_LIO_SAFETY_LINES=1, after the model's answer has streamed, code checks the
visible text and appends one fixed line for every essential that is missing.
Nothing in the model text is removed or rewritten, and an answer that already
covers the essentials gets no extra line.

The lines are fixed, reviewed text: emergency numbers 120 and 110, reporting a
lost passport to the police and contacting the traveler's embassy or consulate,
where to see a doctor, and telling staff about a dietary restriction. They give
no diagnosis, no medicine and no personal eligibility.
"""
from dataclasses import dataclass
import os
import re


@dataclass(frozen=True)
class Requirement:
    key: str
    question: re.Pattern
    # Every pattern must appear in the answer (not negated); each missing one adds its own line.
    essentials: tuple  # ((pattern, {'zh': line, 'en': line}), ...)
    # A question that also matches this is about something else (e.g. allergy medicine, not food).
    unless: re.Pattern | None = None


_I = re.I
REQUIREMENTS = (
    Requirement('emergency', re.compile(
        r'晕倒|昏倒|晕过去|昏过去|晕厥|昏迷|不省人事|没(?:有)?呼吸|'
        r'(?:人|他|她|朋友|同伴|孩子|小孩|老人|家人|妈妈|爸爸|老公|老婆|丈夫|妻子)[^。？！?!]{0,4}没(?:有)?反应|叫不醒|心脏病|心梗|胸口疼|胸痛|胸闷|中风|大出血|抽搐|'
        r'急救|救护车|噎住|溺水|中毒|被车撞|车祸|烫伤|烧伤|中暑|'
        r'\b(?:collaps\w*|faint(?:ed|ing|s)|unconscious|unresponsive|blacked out|not breathing|heart attack|seizure|choking|'
        r'chest pain|hit by a (?:car|bus|motorbike|scooter)|car accident|heat ?stroke|badly burn(?:ed|t)|'
        r'bleeding (?:a lot|heavily|badly)|ambulance|first aid|overdose|poison(?:ed|ing)|drown\w*)\b|'
        r'\bfeel(?:ing)? faint\b|\bpassed out\b(?! (?:from|with) laugh)|\b(?:having|had|has) a stroke\b', _I),
        ((re.compile(r'(?<![0-9])120(?![0-9]|\s*(?:元|块|分钟|公里|米|yuan|RMB|CNY|minutes?|km|m\b))', _I),
          {'zh': '紧急情况请立即拨打 120 叫救护车；需要警察请拨 110。',
           'en': 'In an emergency call 120 for an ambulance now; for the police call 110.'}),)),
    Requirement('lost_documents', re.compile(
        r'护照[^。？！?!]{0,6}(?:丢|掉|不见|被偷|被盗|被抢|遗失|找不到|没了)|'
        r'护照[^。？！?!]{0,4}(?:忘在|落在)[^。？！?!]{0,4}(?:出租车|车上|网约车|飞机|火车|高铁|地铁|公交|路上|餐厅|饭店|店里|景区)|'
        r'(?:丢|掉|弄丢|遗失|找不到)[^。？！?!]{0,4}(?:护照|证件|签证)|证件[^。？！?!]{0,4}(?:丢|不见|被偷|找不到)|'
        r'\b(?:lost|lose|losing|missing|stolen|misplac\w*)\b[^.?!]{0,20}\bpassport\b|'
        r'\bleft (?:my|our|his|her) passport (?:in|on|at) (?:a |the )?(?:taxi|cab|car|didi|train|plane|flight|bus|metro|subway|restaurant|bar|shop|store)\b|'
        r'\b(?:someone|somebody|they|he|she) (?:took|stole|has taken)\b[^.?!]{0,10}\bpassport\b|'
        r'\b(?:can[’\x27]?t|cannot|couldn[’\x27]?t) find\b[^.?!]{0,10}\bpassport\b|'
        r'\bpassport\b[^.?!]{0,20}\b(?:lost|missing|stolen|gone|taken)\b', _I),
        ((re.compile(r'110|报警|报案|派出所|公安|\bpolice\b', _I),
          {'zh': '护照丢失请先到附近派出所报案并开具报失证明，或拨打 110。',
           'en': 'Report the lost passport at the nearest police station and get a loss report, or call 110.'}),
         (re.compile(r'使馆|领馆|使领馆|领事|\bembassy\b|\bconsulate\b|\bconsular\b', _I),
          {'zh': '再联系你本国驻华使馆或领馆，办理补发护照或临时旅行证件。',
           'en': "Then contact your country's embassy or consulate in China for a replacement passport or emergency travel document."}))),
    Requirement('medical', re.compile(
        r'看病|看医生|就医|医院|诊所|发烧|发热|腹泻|拉肚子|呕吐|生病|不舒服|受伤|摔伤|牙疼|'
        r'\b(?:see a doctor|doctor|hospital|clinic|(?<!hay )fever|diarrh\w*|vomit\w*|injur\w*|toothache)\b|'
        r'\b(?:I[’\x27]m|I am|feel(?:ing)?|got|getting|fell|became) (?:really |very )?(?:sick|ill|unwell)\b(?! of)|'
        r'\bhurt (?:my|myself|his|her)\b', _I),
        ((re.compile(r'医院|诊所|急诊|门诊|\bhospital\b|\bclinic\b|\bemergency room\b|\bER\b', _I),
          {'zh': '需要看病时，可去大医院的国际医疗部或急诊，记得带护照；情况紧急请拨打 120。',
           'en': 'To see a doctor, go to the international clinic or emergency department of a major hospital and bring your passport; in an emergency call 120.'}),)),
    Requirement('dietary', re.compile(
        r'(?:对|吃)[^。？！?!]{0,8}过敏|食物过敏|(?:花生|坚果|海鲜|鸡蛋|牛奶|乳制品|麸质|小麦)过敏|过敏(?:的)?(?:食物|菜)|'
        r'忌口|清真|素食|吃素|不吃(?:猪肉|牛肉|肉|辣|海鲜|花生|鸡蛋|乳制品)|麸质|乳糖不耐|'
        r'\ballergic to\b|\bfood allerg\w*|\b(?:nut|peanut|shellfish|seafood|egg|dairy|gluten) allerg\w*|'
        r'\b(?:halal|kosher|vegetarian|vegan|gluten[- ]free|lactose|nut-free|no pork)\b|\bdon[’\x27]t eat\b', _I),
        ((re.compile(r'告诉|告知|跟(?:店员|服务员|厨师|老板)说|出示|写下来|写给|\btell\b|\binform\b|'
                     r'\bshow (?:the |them )?(?:staff|waiter|server|card|note)|\blet (?:the )?(?:staff|waiter|server)s? know\b', _I),
          {'zh': '点餐时把忌口明确告诉店员，也可以写下来出示给店员看；严重过敏请随身带好药品。',
           'en': 'When ordering, tell the staff clearly about your restriction or show it to them in writing; if an allergy is severe, carry your medication.'}),),
        unless=re.compile(r'药|鼻炎|皮肤|花粉|皮疹|\b(?:medicine|medication|pills?|hay fever|rash|pollen)\b', _I)),
)
# "别报警" or "don't call the police" does not count as advising it.
_NEGATION = re.compile(r'(?:别|不要|不用|无需|不必|没必要)\s*$|\b(?:don[’\x27]t|do not|no need to|never)\s+(?:\w+\s+){0,2}$', _I)


def _present(pattern, text):
    return any(_NEGATION.search(text[max(0, match.start() - 20):match.start()]) is None
               for match in pattern.finditer(text))


def safety_lines_enabled():
    """Server switch; off unless explicitly set to 1."""
    value = os.environ.get('CJ_LIO_SAFETY_LINES', '0')
    if value not in ('0', '1'):
        raise ValueError('explicit safety lines switch value required')
    return value == '1'


def matched(question):
    return tuple(requirement.key for requirement in REQUIREMENTS if requirement.question.search(question)
                 and not (requirement.unless is not None and requirement.unless.search(question)))


def supplement(question, answer, locale):
    """The fixed lines to append for missing essentials, or '' when nothing is missing."""
    if locale not in ('zh', 'en'):
        return ''
    lines = []
    for requirement in REQUIREMENTS:
        if not requirement.question.search(question):
            continue
        if requirement.unless is not None and requirement.unless.search(question):
            continue
        for pattern, line in requirement.essentials:
            text = line[locale]
            if not _present(pattern, answer) and not _present(pattern, '\n'.join(lines)) and text not in lines:
                lines.append(text)
    return ('\n\n' + '\n'.join(lines)) if lines else ''
