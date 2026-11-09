"""Trusted Lio origin metadata and user-facing answer prompt."""
from dataclasses import dataclass
import json
import re

from .demo_dialogue import LIO_VERSION


PERSONA = (
    'You are Lio, a lion-dance mascot and travel assistant for visitors to China. '
    'Be friendly and concise. Answer in the requested language. Speak in everyday '
    'language without referring to system internals, internal identifiers, records, '
    'or the format of your instructions. When information is unverified, explain '
    'what the traveler can check. Never invent prices, opening hours, or transport '
    'facts. Never claim a trip has been saved or a booking made based on your reply.'
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
    url: str
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


def display_answer(text, locale):
    if _INTERNAL_ANSWER.search(text):
        return None
    return _UNKNOWN_LABEL.sub('尚未核实' if locale == 'zh' else 'not yet verified', text)


def locale_for(database, binding):
    with database.connect(binding.scope) as connection:
        row = connection.execute(
            'SELECT demo_dialogue_locale FROM cj_message_receipt WHERE scope=%s AND '
            'conversation_id=%s AND generation=%s AND message_id=%s AND run_id=%s AND '
            'demo_dialogue_protocol=%s',
            (binding.scope, binding.conversation_id, binding.generation, binding.message_id,
             binding.run_id, LIO_VERSION)).fetchone()
    return row[0] if row is not None else None
