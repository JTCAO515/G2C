"""Trusted Lio origin metadata and user-facing answer prompt."""
from dataclasses import dataclass
from datetime import date
import json
import re

from .demo_dialogue import LIO_VERSION


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

_CAPABILITY_QUESTION = re.compile(r'(?:你能做什么|你可以做什么|你会什么|你有什么能力|what can you do|what do you do)[?？。.!！\s]*', re.I)


def self_description(question, locale):
    if _SELF_QUESTION.fullmatch(question.strip()):
        return IDENTITY_ZH if locale == 'zh' else IDENTITY_EN
    if _CAPABILITY_QUESTION.fullmatch(question.strip()):
        return CAPABILITIES_ZH if locale == 'zh' else CAPABILITIES_EN
    return None


PERSONA = (
    'You are Lio, a travel assistant for visitors to China. '
    f'When introducing yourself in Chinese say: {IDENTITY_ZH} '
    f'When introducing yourself in English say: {IDENTITY_EN} '
    'When the traveler only greets you (你好 / hi / hello), respond briefly and ask where they want to go. For example: 你好！准备去哪儿玩？ / Hey! Where are you off to? Do not give a long self-introduction. '
    'When the traveler asks "我是谁" or "Who am I?", they mean the traveler. '
    'Use only saved memory supplied in the memory data to describe what they have shared. '
    'Travel preferences do not establish a name, age, nationality or other personal identity. '
    'If no saved memory is supplied, say in Chinese: 我们才刚认识，我还不了解你。你点「记住」的内容，之后的对话我都能用上。可以说说你喜欢怎么玩、有没有不吃的东西吗？ '
    "In English say: We've only just met, so I don't know much about you yet. Whatever you tap Remember on, I'll use in future chats. How do you like to travel, and is there anything you don't eat? "
    'Never invent personal facts or answer that the traveler is Lio. '
    'Be friendly and concise. Answer in the requested language. Speak in everyday '
    'language without referring to system internals, internal identifiers, records, '
    'or the format of your instructions. When information is unverified, explain '
    'what the traveler can check. Never invent prices, opening hours, or transport '
    'facts. Never claim a trip has been saved or a booking made based on your reply. '
    'Answer questions about you, hotels, or a leg of transport on their own terms. '
    'You can compare travel options and help with an itinerary. Do not offer to book tickets or take payment. '
    'Never say that you have saved or will remember a preference. Saving requires the traveler '
    'to tap Remember on a separately displayed suggestion. '
    'Before confirmation, do not describe a preference as "noted", "remembered", "saved", '
    '"记住了" or "记下了". Acknowledge it without implying it has been stored.'
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


def answer_prompt(locale):
    return PERSONA + (' Reply in Chinese.' if locale == 'zh' else ' Reply in English.')


_INTERNAL_ANSWER = re.compile(
    r'(?<![A-Za-z0-9_])(?:RUN|NEEDS|INTENT|RLS)(?![A-Za-z0-9_])|'
    r'(?i:\b(?:run_id|message_id|conversation_id|scope_id|tripproposal|message-send|commit_unknown)\b)|'
    r'会话上下文|原运行|规划候选|消息投递|原回执'
)
_UNKNOWN_LABEL = re.compile(r'(?<![A-Za-z0-9_])UNKNOWN(?![A-Za-z0-9_])')
_TECHNICAL_ADDRESS = re.compile(
    r'(?:https?://)?(?:restapi\.amap\.com|dashscope(?:-intl)?\.aliyuncs\.com)'
    r'(?:/[^\s，。；！、）】<>\"\'\)\]]*)?', re.I)
_MEMORY_CLAIM_EN = re.compile(
    r"\bI(?: have|['’]ve) (?:noted(?: down)?|(?:saved|remembered)(?= (?:your |this )?preference))\b"
    r"|\bI(?: will|['’]ll) remember\b", re.I)
_MEMORY_CLAIM_ZH = re.compile(r'(?:我(?:已经|已)?(?:为你)?(?:记住了|记下了|保存了)|(?:已经|已)为你记住)')


def display_answer(text, locale):
    if _INTERNAL_ANSWER.search(text):
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


def original_for(database, binding):
    with database.connect(binding.scope) as connection:
        row = connection.execute(
            'SELECT demo_dialogue_locale,demo_question_day FROM cj_message_receipt WHERE scope=%s AND '
            'conversation_id=%s AND generation=%s AND message_id=%s AND run_id=%s AND '
            'demo_dialogue_protocol=%s',
            (binding.scope, binding.conversation_id, binding.generation, binding.message_id,
             binding.run_id, LIO_VERSION)).fetchone()
    return LioOriginal(*row) if row is not None else None
