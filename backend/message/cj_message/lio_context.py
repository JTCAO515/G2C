"""Trusted Lio origin metadata and user-facing answer prompt."""
from dataclasses import dataclass
from .domain import Unavailable
from datetime import date
import json
import re

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

_CAPABILITY_QUESTION = re.compile(r'(?:你能做什么|你能干啥|你会干嘛|你能帮我做什么|你可以做什么|你会什么|你有什么能力|what can you do|what do you do|what can you help me with)[?？。.!！\s]*', re.I)


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
    'For greetings, thanks and confirmations use at most 30 Chinese characters or 20 English words; '
    'normally at most 80 characters or 50 words; for recommendations and comparisons at most '
    '150 characters or 90 words. Use at most 3 list items. Count the closing question; '
    'Chinese names and pinyin do not count towards English word limits. '
    'Use short sentences and paragraphs; omit tables, headings and raw links. '
    'Give the complete answer, then end with one specific question, '
    'offering 2–3 easy choices or a next step you can do. Vary questions; use supplied facts. '
    'In emergencies lead with 110 (police) or 120 (ambulance), without length limits; '
    'end with an action. Farewells may end with a wish. '
    'Greet briefly: 你好！准备去哪儿玩？ / Hey! Where are you off to? '
    'In English, follow the first mention of each place, dish, station or useful phrase with its '
    'Chinese name in bold, such as Forbidden City (**故宫**). For specific places, use Chinese '
    'names returned by the place lookup; omit unknown names. Add pinyin only for words to say aloud. '
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

_TRAVELER_IDENTITY_QUESTION = re.compile(r'(?:我是谁|你了解我什么|who am i|what do you know about me)[?？。.!！\s]*', re.I)
_TRAVELER_IDENTITY_PROMPT = (
    'For this question only, if no saved memory is supplied, say in Chinese: '
    '我们才刚认识，我还不了解你。你点「记住」的内容，之后的对话我都能用上。可以说说你喜欢怎么玩、有没有不吃的东西吗？ '
    "In English say: We've only just met, so I don't know much about you yet. Whatever you tap Remember on, I'll use in future chats. How do you like to travel, and is there anything you don't eat? "
)

SOURCE_EFFECT = 'lio_source:'
TOOL_EFFECT = 'lio_tool:'


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


def answer_prompt(locale, question=None):
    identity = (_TRAVELER_IDENTITY_PROMPT if question is not None
                and _TRAVELER_IDENTITY_QUESTION.fullmatch(question.strip()) else '')
    return PERSONA + identity + (' Reply in Chinese.' if locale == 'zh' else ' Reply in English.')


_INTERNAL_ANSWER = re.compile(
    r'(?<![A-Za-z0-9_])(?:RUN|NEEDS|INTENT|RLS)(?![A-Za-z0-9_])|'
    r'(?i:\b(?:run_id|message_id|conversation_id|scope_id|trip_id|job_id|attempt_id|operation_id|'
    r'candidate_id|source_id|input_sha256|tripproposal|message-send|commit_unknown)\b)|'
    r'(?i:\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b)|'
    r'会话上下文|原运行|规划候选|消息投递|原回执'
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
