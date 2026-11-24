"""Trusted Lio origin metadata and user-facing answer prompt."""
from dataclasses import dataclass
from .domain import Unavailable
from datetime import date
from hashlib import sha256
import json
import re
from typing import NamedTuple

from .demo_dialogue import LIO_VERSION, LIO_VERSION_V3, LIO_VERSION_V4
from .domain import Unavailable


IDENTITY_ZH = '我是 Lio，帮来中国旅行的人出主意。从“三天怎么玩”到“今天下雨了还能去哪”，都可以问我。你这次打算去哪儿？'
IDENTITY_EN = 'I\'m Lio. I help people travelling in China figure things out, from "how should I spend three days here?" to "it\'s raining, where can I go now?" Where are you planning to go?'
CAPABILITIES_ZH = """我能帮你：

- **排行程**：告诉我城市、天数和喜好，我排出每天去哪、怎么走，排好的行程会保存到你的行程里。
- **查实用信息**：天气、交通方式、几个地方之间怎么走。拿不准的我会直说，并告诉你去哪确认。
- **随时改计划**：下雨了、累了、想换个地方，跟我说一声，我只改受影响的部分，你定好的安排不动。
- **记住你的习惯**：比如不吃辣、喜欢早起。你点「记住」之后，下次规划就会用上。

订票和付款我做不了，需要你在官方渠道自己完成。想先从哪件事开始？"""
CAPABILITIES_EN = """Here's how I can help:

- **Plan your days:** tell me the city, how long you're staying and what you like, and I'll map out where to go and how to get around. Your plan is saved to your trip.
- **Practical info:** weather, ways to get around, how to get from one place to another. If I'm not sure about something, I'll say so and tell you where to check.
- **Change plans on the fly:** rain, tired feet, a new idea — just tell me. I'll only change the part that's affected and keep what you've locked in.
- **Learn your style:** say you don't eat spicy food or like early starts. Tap Remember and I'll use it next time I plan.

I can't book or pay for anything — you'll need to do that through official channels. Where would you like to start?"""

_SELF_QUESTION = re.compile(r'(?:你是谁|你是什么|介绍一下你自己|who are you|what are you)[?？。.!！\s]*', re.I)

# Colloquial variants (你能做啥, 你可以帮我干嘛, 你有啥功能) are the same
# capability question; a narrow list sent them into planning intake (#994).
CAPABILITY_PATTERN = (r'(?:(?:那|请问|所以)\s*)?(?:'
    r'你(?:都|还)?(?:能|会|可以)(?:帮我|为我|给我)?(?:做|干|帮|处理)?(?:些)?(?:什么|啥|哪些|嘛|啥子)(?:事|事情|忙)?|'
    r'你有(?:什么|啥|哪些)(?:能力|功能|本事|用)|'
    r'what (?:can|could) you (?:do|help(?: me)? with)|what do you do|how can you help(?: me)?|what are you able to do'
    r')(?:呢|呀|啊|吗)?')
_CAPABILITY_QUESTION = re.compile(CAPABILITY_PATTERN + r'[?？。.!！\s]*', re.I)
_HAN_TEXT = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]')
_LATIN_TEXT = re.compile(r'[A-Za-z]')
_ENGLISH_QUESTION_OPENING = re.compile(
    r'^\W*(?:how|what|where|when|which|who|why|can|could|should|would|do|does|is|are|please)\b', re.I)
_CHINESE_QUESTION_WORD = re.compile(r'请问|怎么|怎样|如何|哪里|哪儿|多少|多久|能否|是否|可以|吗|呢')


def answer_locale(question, default):
    """Choose the answer language from the current question's wording."""
    han = _HAN_TEXT.search(question)
    latin = _LATIN_TEXT.search(question)
    if han is None:
        return 'en' if latin is not None else default
    if latin is None:
        return 'zh'
    if _ENGLISH_QUESTION_OPENING.match(question):
        return 'en'
    if han.start() < latin.start() or _CHINESE_QUESTION_WORD.search(question):
        return 'zh'
    return default


def self_description(question, locale):
    if _SELF_QUESTION.fullmatch(question.strip()):
        return IDENTITY_ZH if locale == 'zh' else IDENTITY_EN
    if _CAPABILITY_QUESTION.fullmatch(question.strip()):
        return CAPABILITIES_ZH if locale == 'zh' else CAPABILITIES_EN
    return None


PERSONA = (
    'You are Lio, a travel assistant for visitors to China. '
    'For a foreign-passport visitor, assume neither a Chinese ID card, Chinese phone number, '
    'configured WeChat Pay or Alipay, nor Chinese fluency. '
    'Give the useful, supported answer first. Date changing facts. '
    'If uncertain, first answer what you can, then explain the gap once in the first person, '
    'say where to check, and keep helping. '
    'Never invent prices, opening hours, or transport facts. '
    'The app handles saving: describe your suggestion and let the trip card confirm a saved plan or change. '
    'Saving requires the traveler to tap Remember on a separately displayed suggestion. '
    'Do not offer to book tickets or take payment. Help with timing and options instead. '
    'Be friendly and concise. Answer in the requested language. '
    'For greetings, thanks and confirmations use at most 40 Chinese characters or 25 English words. '
    'Chinese names and pinyin do not count towards English word limits. '
    'Use short sentences; never use tables, # headings or raw links. '
    'Do not start with a greeting, a self-introduction or a restatement of the question. '
    'End with at most one specific question, only when there is a useful next step to choose, '
    'offering 2–3 easy choices; never repeat one. Vary questions; use supplied facts. '
    'In emergencies lead with 110 (police) or 120 (ambulance), without length limits; '
    'end with an action. Farewells may end with a wish. '
    'Greet briefly, only when the traveler only greets you: 你好！准备去哪儿玩？ / Hey! Where are you off to? '
    'In English, follow the first mention of each place, dish, station or useful phrase with its '
    'Chinese name in bold, such as Forbidden City (**故宫**). For specific places, use Chinese '
    'names returned by the place lookup or of famous landmarks; omit unknown names. '
    'Add pinyin only for words to say aloud. '
    'In Chinese address the traveler as 你. '
    'Talk about the trip in everyday language; keep internal identifiers, coordinates, providers '
    'and interfaces out of the answer. If asked about sources, say '
    '我综合了地图、天气等多方面的信息 / I combine maps, weather and other trusted information, '
    'then return to the travel question. '
    'When the traveler asks "我是谁" or "Who am I?", they mean the traveler. '
    'Use only saved memory supplied in the memory data to describe what they have shared. '
    'Travel preferences do not establish a name, age, nationality or other personal identity. '
    'Never invent personal facts or answer that the traveler is Lio. '
    'Do not introduce yourself or discuss knowing the traveler in an unrelated travel answer. '
    'Use saved-itinerary scenes only for orientation, not traveler facts or actual location. '
    'Never fill missing planning fields from them. During a trip lead with an action. '
    'Keep scene labels out of replies. '
)

# Detail for answers and day plans only. Intake prompts reuse PERSONA under a
# bounded request size, so this text is appended only where a reply is written.
ANSWER_DETAIL = (
    ' Concise means no filler, not thin: answer like a well-travelled local friend, with the specific '
    'names, steps, times, routes and practical tips a visitor needs to act. Size the answer to the question. '
    'Practical questions such as transport, payment, internet, visas, food and etiquette: usually '
    '120–300 Chinese characters or 80–180 English words, with 3–6 numbered steps or bullet points '
    'when there is a procedure. Recommendations and comparisons: up to 500 characters or 300 words. '
    'A day-by-day plan: one short section per day with morning, afternoon and evening, up to 1000 '
    'characters or 600 words in total; for more than three days keep each day to two bullet lines. '
    'Use bold short headings, numbered steps and bullet lists when they make the answer easier to scan. '
    'Where it helps, name the metro line or station, the rough walking or ride time, and one or two '
    'practical tips such as passport reservations, a cash backup or busy hours. '
    'Well-established reference figures are not invented: give them as approximate ranges, such as about '
    '3–7 yuan for a metro ride or about 4.5–6 hours by high-speed train from Beijing to Shanghai, and say '
    'where to confirm. Live prices, ticket availability and whether a place is open today stay without '
    'numbers; say where to check.'
)

_TRAVELER_IDENTITY_QUESTION = re.compile(r'(?:我是谁|你了解我什么|who am i|what do you know about me)[?？。.!！\s]*', re.I)
_TRAVELER_IDENTITY_PROMPT = (
    'For this question only, if no saved memory is supplied, say in Chinese: '
    '我们才刚认识，我还不了解你。你点「记住」的内容，之后的对话我都能用上。可以说说你喜欢怎么玩、有没有不吃的东西吗？ '
    "In English say: We've only just met, so I don't know much about you yet. Whatever you tap Remember on, I'll use in future chats. How do you like to travel, and is there anything you don't eat? "
)

SOURCE_EFFECT = 'lio_source:'
TOOL_EFFECT = 'lio_tool:'
UNSAVED_PLAN_ANSWER = 'lio_unsaved_plan_answer.1'
UNSETTLED_VISIBLE_ANSWER = 'lio_unsettled_visible_answer.1'


@dataclass(frozen=True)
class LioToolProgress:
    key: str
    activity: str | None

    def effect(self):
        return TOOL_EFFECT + json.dumps(dict(key=self.key, activity=self.activity),
                                        separators=(',', ':'))


@dataclass(frozen=True)
class LioCitation:
    key: str
    title: str
    url: str | None
    observed_at: str | None

    def effect(self):
        value = dict(key=self.key, title=self.title, url=self.url, observed_at=self.observed_at)
        return SOURCE_EFFECT + json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def answer_prompt(locale, question=None, *, detailed=False):
    identity = (_TRAVELER_IDENTITY_PROMPT if question is not None
                and _TRAVELER_IDENTITY_QUESTION.fullmatch(question.strip()) else '')
    return (PERSONA + identity + (ANSWER_DETAIL if detailed else '')
            + (' Reply in Chinese.' if locale == 'zh' else ' Reply in English.'))


DISCUSSION_VISIT_VERBS = {
    'visit': ('参观', 'Visit'), 'explore': ('游览', 'Explore'),
    'walk': ('漫步', 'Walk around'), 'eat': ('去用餐', 'Eat at'),
    'shop': ('去逛', 'Shop at'), 'relax': ('去休息', 'Relax at'),
}
DISCUSSION_VISIT_PERIODS = {
    None: ('', ''), 'morning': ('上午', 'Morning: '),
    'afternoon': ('下午', 'Afternoon: '), 'evening': ('晚上', 'Evening: '),
}
DISCUSSION_MAX_PREVIEW_DAYS = 366


class DiscussionPreviewInput(NamedTuple):
    messages: list[dict]
    system: str
    provider: object
    day_count: int


def discussion_preview_format(day_count):
    if type(day_count) is not int or not 1 <= day_count <= DISCUSSION_MAX_PREVIEW_DAYS:
        raise ValueError('bounded discussion day count required')
    activity=dict(type='object',additionalProperties=False,required=['place_name','verb','period'],properties={
        'place_name': {'type': 'string', 'minLength': 1, 'maxLength': 240,
            'description': 'Name of the visit location, with its branch or section whenever known.'},
        'verb':dict(type='string',enum=list(DISCUSSION_VISIT_VERBS)),
        'period':dict(enum=list(DISCUSSION_VISIT_PERIODS)),
    })
    day=dict(type='object',additionalProperties=False,required=['day_index','activities'],properties={
        'day_index':dict(type='integer',minimum=1,maximum=day_count),
        'activities':dict(type='array',minItems=1,maxItems=8,items=activity),
    })
    fields={
        'answer':dict(type='string',minLength=1,maxLength=12000),
        'days':dict(anyOf=[dict(type='array',minItems=day_count,maxItems=day_count,items=day),dict(type='null')]),
        'follow_up':dict(type=['string','null'],maxLength=280),
    }
    return dict(type='json_schema',json_schema=dict(name='LIO_discussion_preview_1',strict=True,
        schema=dict(type='object',additionalProperties=False,required=list(fields),properties=fields)))


def discussion_preview_format_sha256(day_count):
    encoded=json.dumps(discussion_preview_format(day_count),sort_keys=True,separators=(',',':')).encode()
    return sha256(encoded).hexdigest()


_INTERNAL_ANSWER = re.compile(
    r'(?<![A-Za-z0-9_])(?:RUN|NEEDS|INTENT|RLS)(?![A-Za-z0-9_])|'
    r'(?i:(?<![A-Za-z0-9_])(?:run_id|message_id|conversation_id|scope_id|trip_id|job_id|attempt_id|operation_id|'
    r'candidate_id|source_id|input_sha256|tripproposal|message-send|commit_unknown)(?![A-Za-z0-9_]))|'
    r'(?i:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})|'
    r'规划候选|消息投递|原回执'
)
_COORDINATE_PAIR = re.compile(
    r'(?<![A-Za-z0-9_.])([+-]?\d{1,3}\.\d+)\s*[,，/]\s*'
    r'([+-]?\d{1,3}\.\d+)(?!\w|\.\d)')
_LABELLED_COORDINATES = re.compile(
    r'(?:\b(?:lat(?:itude)?|lon(?:gitude)?|lng)\b|纬度|经度|[东西]经|[南北]纬)["\']?\s*[:=：]?\s*'
    r'[+-]?\d{1,3}(?:\.\d+)?\s*[°度]?(?:\s*[,，;；]\s*|\s+)["\']?'
    r'(?:\b(?:lat(?:itude)?|lon(?:gitude)?|lng)\b|纬度|经度|[东西]经|[南北]纬)["\']?\s*[:=：]?\s*'
    r'[+-]?\d{1,3}(?:\.\d+)?', re.I)
_UNKNOWN_LABEL = re.compile(r'(?<![A-Za-z0-9_])UNKNOWN(?![A-Za-z0-9_])')
_TECHNICAL_ADDRESS = re.compile(
    r'(?:https?://)?(?:restapi\.amap\.com|dashscope(?:-intl)?\.aliyuncs\.com|api-beta\.go2china\.space)'
    r'(?::[0-9]{1,5})?(?:[/?#][^\s，。；！、）】<>\"\'\)\]]*)?', re.I)
_MEMORY_CLAIM_EN = re.compile(
    r"\bI(?: have|['’]ve) (?:noted(?: down)?|(?:saved|remembered)(?= (?:your |this )?preference))\b"
    r"|\bI(?: will|['’]ll) remember\b", re.I)
_MEMORY_CLAIM_ZH = re.compile(r'(?:我(?:已经|已)?(?:为你)?(?:记住了|记下了|保存了)|(?:已经|已)为你记住)')


def display_answer(text, locale):
    if (_INTERNAL_ANSWER.search(text) or _LABELLED_COORDINATES.search(text)
            or any((abs(float(x)) <= 90 and abs(float(y)) <= 180)
                   or (abs(float(x)) <= 180 and abs(float(y)) <= 90)
                   for x, y in _COORDINATE_PAIR.findall(text))):
        return None
    chinese = locale == 'zh'
    text = _TECHNICAL_ADDRESS.sub('服务方' if chinese else 'the service provider', text)
    text = _UNKNOWN_LABEL.sub('暂未确认' if chinese else 'not yet verified', text)
    text = _MEMORY_CLAIM_ZH.sub('我了解了', text)
    text = _MEMORY_CLAIM_EN.sub('I understand', text)
    return text.replace('查询', '查看').replace('核实', '确认')


@dataclass(frozen=True)
class LioOriginal:
    locale: str
    question_day: date | None
    protocol: str = LIO_VERSION


def _origin_row(database,binding):
    with database.connect(binding.scope) as connection:
        row = connection.execute(
            'SELECT demo_dialogue_locale,demo_question_day,lio_wire_protocol FROM cj_message_receipt WHERE scope=%s AND '
            'conversation_id=%s AND generation=%s AND message_id=%s AND run_id=%s AND '
            'demo_dialogue_protocol=%s',
            (binding.scope, binding.conversation_id, binding.generation, binding.message_id,
             binding.run_id, LIO_VERSION)).fetchone()
    return row


def original_for(database, binding):
    row=_origin_row(database,binding)
    if row is None:
        return None
    if row[2] is not None:
        raise Unavailable('newer Lio original requires its selected calendar worker')
    return LioOriginal(row[0], row[1])


def calendar_original_for(database, binding):
    row=_origin_row(database,binding)
    if row is None:
        return None
    if row[2] not in (None, LIO_VERSION_V3):
        raise Unavailable('original Lio capability unavailable')
    return LioOriginal(row[0], row[1], LIO_VERSION if row[2] is None else row[2])


def exploration_original_for(database,binding):
    row=_origin_row(database,binding)
    if row is None:return None
    if row[2]!=LIO_VERSION_V4:
        raise Unavailable('exploration worker requires an actual Lio4 original')
    return LioOriginal(row[0],row[1],LIO_VERSION_V4)


def selected_lio_original_for(database,binding):
    """Only the explicitly upgraded national factory installs this selector."""
    row=_origin_row(database,binding)
    if row is None:return None
    if row[2] not in (None,LIO_VERSION_V3,LIO_VERSION_V4):
        raise Unavailable('original Lio capability unavailable')
    return LioOriginal(row[0],row[1],LIO_VERSION if row[2] is None else row[2])
