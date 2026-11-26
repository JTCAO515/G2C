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
    # Every pattern must appear in the answer; each missing one adds its own line.
    essentials: tuple  # ((pattern, {'zh': line, 'en': line}), ...)


_I = re.I
REQUIREMENTS = (
    Requirement('emergency', re.compile(
        r'晕倒|昏倒|昏迷|没(?:有)?呼吸|心脏病|心梗|中风|大出血|抽搐|急救|救护车|噎住|溺水|中毒|'
        r'\b(?:collaps\w*|unconscious|passed out|not breathing|heart attack|stroke|seizure|choking|'
        r'bleeding (?:a lot|heavily|badly)|ambulance|first aid|overdose|poison\w*|drown\w*)\b', _I),
        ((re.compile(r'120'), {'zh': '紧急情况请立即拨打 120 叫救护车；需要警察请拨 110。',
                                'en': 'In an emergency call 120 for an ambulance now; for the police call 110.'}),)),
    Requirement('lost_documents', re.compile(
        r'护照[^。？！?!]{0,6}(?:丢|掉|不见|被偷|被盗|遗失)|(?:丢|掉|弄丢|遗失)[^。？！?!]{0,4}(?:护照|证件|签证)|证件[^。？！?!]{0,4}(?:丢|不见|被偷)|'
        r'\b(?:lost|lose|losing|missing|stolen)\b[^.?!]{0,20}\bpassport\b|\bpassport\b[^.?!]{0,20}\b(?:lost|missing|stolen|gone)\b', _I),
        ((re.compile(r'110|报警|报案|派出所|公安|\bpolice\b', _I),
          {'zh': '护照丢失请先到附近派出所报案并开具报失证明，或拨打 110。',
           'en': 'Report the lost passport at the nearest police station and get a loss report, or call 110.'}),
         (re.compile(r'使馆|领馆|使领馆|领事|\bembassy\b|\bconsulate\b|\bconsular\b', _I),
          {'zh': '再联系你本国驻华使馆或领馆，办理补发护照或临时旅行证件。',
           'en': "Then contact your country's embassy or consulate in China for a replacement passport or emergency travel document."}))),
    Requirement('medical', re.compile(
        r'看病|看医生|就医|医院|诊所|发烧|发热|腹泻|拉肚子|呕吐|生病|不舒服|受伤|摔伤|牙疼|'
        r'\b(?:see a doctor|doctor|hospital|clinic|sick|ill|fever|diarrh\w*|vomit\w*|injur\w*|hurt|toothache)\b', _I),
        ((re.compile(r'医院|诊所|急诊|门诊|\bhospital\b|\bclinic\b|\bemergency room\b|\bER\b', _I),
          {'zh': '需要看病时，可去大医院的国际医疗部或急诊，记得带护照；情况紧急请拨打 120。',
           'en': 'To see a doctor, go to the international clinic or emergency department of a major hospital and bring your passport; in an emergency call 120.'}),)),
    Requirement('dietary', re.compile(
        r'过敏|忌口|清真|素食|吃素|不吃(?:猪肉|牛肉|肉|辣|海鲜|花生|鸡蛋|乳制品)|麸质|乳糖不耐|'
        r'\b(?:allerg\w*|halal|kosher|vegetarian|vegan|gluten|lactose|nut-free|no pork|don[’\x27]t eat)\b', _I),
        ((re.compile(r'告诉|告知|说明|出示|跟(?:店员|服务员)说|写给|\btell\b|\bshow\b|\blet (?:the )?(?:staff|waiter|server)s? know\b|\bask\b', _I),
          {'zh': '点餐时把忌口明确告诉店员，也可以写下来出示给店员看；严重过敏请随身带好药品。',
           'en': 'When ordering, tell the staff clearly about your restriction or show it to them in writing; if an allergy is severe, carry your medication.'}),)),
)


def safety_lines_enabled():
    """Server switch; off unless explicitly set to 1."""
    value = os.environ.get('CJ_LIO_SAFETY_LINES', '0')
    if value not in ('0', '1'):
        raise ValueError('explicit safety lines switch value required')
    return value == '1'


def matched(question):
    return tuple(requirement.key for requirement in REQUIREMENTS if requirement.question.search(question))


def supplement(question, answer, locale):
    """The fixed lines to append for missing essentials, or '' when nothing is missing."""
    if locale not in ('zh', 'en'):
        return ''
    lines = []
    for requirement in REQUIREMENTS:
        if not requirement.question.search(question):
            continue
        for pattern, line in requirement.essentials:
            text = line[locale]
            if not pattern.search(answer) and not pattern.search('\n'.join(lines)) and text not in lines:
                lines.append(text)
    return ('\n\n' + '\n'.join(lines)) if lines else ''
