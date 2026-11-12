"""Read-only, source-language Memory labels; original text stays authoritative."""
import re


_HAN = re.compile(r'[\u3400-\u9fff]')
_LATIN = re.compile(r'[A-Za-z]')
_ENDING = '。.!！?？;；:：,，'
_INTERNAL = re.compile(
    r'(?<![A-Za-z0-9_])(?:RUN|NEEDS|INTENT|RLS|UNKNOWN)(?![A-Za-z0-9_])|'
    r'(?i:\b(?:run_id|message_id|conversation_id|scope_id|trip_id|job_id|attempt_id|'
    r'operation_id|candidate_id|source_id|input_sha256|commit_unknown)\b)|'
    r'(?i:\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b)|'
    r'(?i:\b[0-9a-f]{32,}\b)|会话上下文|原运行|规划候选|消息投递|原回执'
)
_REMINDER = re.compile(r'^(?:请(?:帮我)?记住[，、：:\s]*|(?:please )?remember(?: that)?[,:\s]+)', re.I)
_ZH_INTRO = re.compile(r'^我(?:平时|通常|一般|一直)?(?:更)?(?:喜欢|偏爱|偏好|习惯)')
_EN_INTRO = re.compile(r'^I (?:(?:usually|always|generally) )?(?:prefer|like|enjoy) ', re.I)
_ZH_BUDGET = re.compile(r'^旅行预算(?:通常|一般)?(?:为|是)?')
_EN_BUDGET = re.compile(r'^I (?:(?:usually|always|generally) )?budget ', re.I)
_TRAVEL_SLOTS = frozenset({'travel.pace', 'travel.budget', 'travel.interests'})
_TRAVEL_QUALIFIER = re.compile(r' (?:when I travel|when travelling|when traveling)$', re.I)


def _script(text):
    han, latin = bool(_HAN.search(text)), bool(_LATIN.search(text))
    return 'characters' if han and not latin else 'words' if latin and not han else None


def valid_title(original, title):
    """Semantic companion to the public schema; empty/null means unavailable."""
    if title is None or title == '':
        return True
    script = _script(original)
    if (script is None or _script(title) != script or title != title.strip()
            or any(c in title for c in '\r\n\t*_`[]') or title[-1] in _ENDING
            or _INTERNAL.search(title)):
        return False
    return len(title) <= 10 if script == 'characters' else len(title.split()) <= 5


def derive_title(command):
    """Source-language phrase reduction, preserving negation; no truncation."""
    if command.kind == 'inference' or any(c in command.text for c in '\r\n\t'):
        return None
    text = _REMINDER.sub('', command.text.strip()).rstrip(_ENDING).strip()
    script = _script(command.text)
    if script == 'characters':
        if command.slot in _TRAVEL_SLOTS:
            text = re.sub(r'^我(?:旅行时|旅游时)', '我', text)
        text = _ZH_INTRO.sub('', text)
        if command.slot == 'travel.budget':
            text = _ZH_BUDGET.sub('', text)
    elif script == 'words':
        if command.slot in _TRAVEL_SLOTS:
            text = _TRAVEL_QUALIFIER.sub('', text)
        text = _EN_INTRO.sub('', text)
        if command.slot == 'travel.budget':
            text = _EN_BUDGET.sub('', text)
        text = re.sub(r'^I (?=(?:do not|don\W?t|avoid)\b)', '', text, flags=re.I)
        if text:
            text = text[0].upper() + text[1:]
    text = text.strip()
    return text if text and valid_title(command.text, text) else None
