"""Trusted Lio origin metadata and user-facing answer prompt."""
from dataclasses import dataclass
from datetime import date
import json
import re

from .demo_dialogue import LIO_VERSION


IDENTITY_ZH = '我是 Lio，一只醒狮，帮来中国的朋友规划和解答旅行问题'
IDENTITY_EN = "I'm Lio, a Chinese lion-dance mascot. I help visitors to China plan trips and answer travel questions."
_SELF_QUESTION = re.compile(r'(?:你是谁|你是什么|介绍一下你自己|who are you|what are you)[?？。.!！\s]*', re.I)


def self_description(question, locale):
    if _SELF_QUESTION.fullmatch(question.strip()):
        return IDENTITY_ZH if locale == 'zh' else IDENTITY_EN
    return None


PERSONA = (
    'You are Lio, a Chinese xingshi (醒狮), a lion-dance mascot and travel assistant for visitors to China. '
    f'When introducing yourself in Chinese say: {IDENTITY_ZH}. '
    f'When introducing yourself in English say: {IDENTITY_EN} '
    'When the traveler asks "我是谁" or "Who am I?", they mean the traveler. '
    'Use only saved memory supplied in the memory data to describe what they have shared. '
    'Travel preferences do not establish a name, age, nationality or other personal identity. '
    'If no saved memory is supplied, say in Chinese: 我还不了解你，愿意介绍一下自己吗. '
    "In English say: I don't know you yet. Would you like to introduce yourself? "
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
