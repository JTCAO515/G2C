"""The first-time memory consent prompt of an answer (#1999, M-1; LIO-answer-rich.1 `rich.memory.prompt`).

When a traveler says something about themselves that Lio could remember (a taste, a pace, a budget, who they
travel with, an interest, a language) and the account has never chosen whether Lio may remember, the answer
carries a marker and the App may ask once. Code decides, from a fixed, reviewed table of cues: no model call,
nothing about the preference is stored, only the marker `lio_memory_prompt:consent`. It prepares no suggestion
and reads no memory, so it is not what LIO-MEMORY-CONSENT-V1.md calls preparation. It is sent only while
CJ_LIO_MEMORY_CONSENT_REQUIRED is on, only to an account whose consent reads `recorded: false` (never to one
that withdrew), and never for health or religion (M-2: `lio_memory_preferences.sensitive`).
"""
import re

from .lio_memory_preferences import sensitive

PROMPT_EFFECT = 'lio_memory_prompt:consent'
_ZH_SELF = re.compile(r'我(?:平时|通常|一般|一直|比较|更|总是|很|特别)?(?:喜欢|偏爱|偏好|习惯|爱吃|不喜欢|不爱|不吃|讨厌|只吃)')
_ZH_CUE = re.compile(r'预算|每晚[0-9]|每天[0-9]+[元块]|慢节奏|快节奏|轻松(?:一点|点)?|节奏(?:慢|快)|(?:带|和)(?:着)?(?:孩子|小孩|宝宝|朋友|家人|爸妈|父母|老婆|老公|对象)|一个人(?:去|旅行|玩)|只会(?:说)?(?:英语|英文|中文|日语)|不会(?:说)?中文')
_EN_SELF = re.compile(r"\bI(?:'m| am)? (?:usually |always |really |mostly |generally )?(?:like|love|prefer|enjoy|hate|avoid|don't like|do not like|don't eat|do not eat|only eat)\b", re.I)
_EN_CUE = re.compile(r"\bmy budget\b|\bbudget (?:of|is|around)\b|\bslow(?:er)? pace\b|\brelaxed (?:pace|trip)\b|\bI(?:'m| am) travel(?:l)?ing (?:with|alone|solo)\b|\btravel(?:l)?ing with (?:my|a|two|three|kids|children|friends)\b|\bI only speak\b|\bI don't speak (?:any )?chinese\b", re.I)
MAX_QUESTION = 2000


def matches(question):
    """True when the question states something about the traveler's own preferences, by the fixed cue table."""
    if type(question) is not str or not question.strip() or len(question) > MAX_QUESTION or sensitive(question):
        return False
    return any(pattern.search(question) for pattern in (_ZH_SELF, _ZH_CUE, _EN_SELF, _EN_CUE))


def never_chosen(consent, scope):
    """True only while the account has no consent record at all (not granted, not withdrawn). A read that fails is no."""
    try:
        return consent is not None and consent.current(scope)['recorded'] is False
    except Exception:
        return False


def effect(question, consent, scope):
    """The effect to write for a finished answer, or None. Reads one row of the account's own consent records."""
    from .lio_memory_consent import consent_required
    if not consent_required() or not matches(question) or not never_chosen(consent, scope):
        return None
    return PROMPT_EFFECT
