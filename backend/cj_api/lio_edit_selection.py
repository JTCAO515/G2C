"""Resolve an explicit Lio replacement against the current structured itinerary."""
from dataclasses import dataclass
from datetime import date, time
from hashlib import sha256
import json
import re

from cj_manual_edit.scoped import Preview, Request, preview, resolve
from cj_trip.domain import Conflict, packed


_CHINESE_EDIT = re.compile(r'^(?:请|能不能|可以)?\s*把\s*(?P<target>.+?)\s*(?:换成|改成|替换成)\s*(?P<replacement>.+)$')
_ENGLISH_EDIT = re.compile(
    r'^(?:please\s+|(?:could|can|would) you\s+)?(?:change|replace|swap)\s+(?P<target>.+?)'
    r'\s+(?:to|with|for)\s+(?P<replacement>.+)$', re.I,
)
_ENGLISH_SEPARATOR = re.compile(r'\s+(?:to|with|for)(?=\s)', re.I)
_KEEP_OTHER_STOPS = re.compile(
    r'(?:[，,]\s*)?保留(?:其他|其余)安排$|'
    r'(?:,\s*(?:and\s+)?|\s+and\s+)keep\s+(?:the\s+)?'
    r'(?:other (?:plans|stops|arrangements)|rest)(?:\s+(?:unchanged|the same))?$', re.I)
_STOP_LABEL = re.compile(r"[^\W_]+(?:[ '’&·()（）-]+[^\W_]+)*[)）]?")
_STOP_QUOTES = {'"': '"', '“': '”', '「': '」'}
# Unquoted names may come from any destination. Multi-place, conditional or
# deferred commands still require clarification; quoting makes a label literal.
_QUALIFIED_LABEL = re.compile(
    r"\b(?:and|or|only|if|unless|provided|subject|approval|confirm|wait|yet|please|not|do)\b"
    r"|[，,；;、/&]|不过|如果|但是|但|或者|或|以及|和|与|先别|先不|缓一缓|问问我|经我同意|再执行", re.I)
_CHINESE_SLOT = re.compile(r'(?:第([一二三四五六七八九十]|[1-9][0-9]?)天|(最后一天))\s*(上午|下午|晚上)')
_ENGLISH_SLOT = re.compile(r'(?:the\s+)?(?:day\s+([1-9][0-9]?)|(first|second|third|last|final)(?:\s+day)?)'
                           r'(?:\s+in\s+the)?\s+(morning|afternoon|evening)', re.I)
_ENGLISH_PERIOD_FIRST = re.compile(r'(?:the\s+)?(morning|afternoon|evening)\s+of\s+'
                                   r'(?:day\s+([1-9][0-9]?)|(?:the\s+)?(first|second|third|last|final)\s+day)', re.I)
_DATED_SLOT = re.compile(r'([0-9]{4}-[0-9]{2}-[0-9]{2})\s*(上午|下午|晚上|morning|afternoon|evening)', re.I)
_ENGLISH_DATED_SLOT = re.compile(r'(?:the\s+)?(morning|afternoon|evening)\s+(?:of|on)\s+'
                                 r'([0-9]{4}-[0-9]{2}-[0-9]{2})', re.I)
_ORDINALS = {**dict(zip('一二三四五六七八九十', range(1, 11), strict=True)),
             'first': 1, 'second': 2, 'third': 3, 'last': -1, 'final': -1, '最后一天': -1}
_PERIODS = {
    '上午': (time(0), time(12)), 'morning': (time(0), time(12)),
    '下午': (time(12), time(18)), 'afternoon': (time(12), time(18)),
    '晚上': (time(18), time.max), 'evening': (time(18), time.max),
}


@dataclass(frozen=True)
class LioEditSelection:
    status: str
    candidate: Preview | None = None


def match_edit(text):
    utterance = text.strip()
    return _CHINESE_EDIT.fullmatch(utterance) or _ENGLISH_EDIT.fullmatch(utterance)


def _edit_parts(match):
    if match.re is _CHINESE_EDIT:
        yield match['target'].strip(), match['replacement']
        return
    # A separator can be part of an itinerary title or a quoted replacement.
    tail = match.string[match.start('target'):]
    for separator in _ENGLISH_SEPARATOR.finditer(tail):
        yield tail[:separator.start()].strip(), tail[separator.end():]


def _replacement_label(raw):
    label = raw.strip().rstrip('。.!！?？').rstrip()
    label = _KEEP_OTHER_STOPS.sub('', label).rstrip()
    quoted = len(label) > 2 and _STOP_QUOTES.get(label[0]) == label[-1]
    if quoted:
        label = label[1:-1].strip()
    if len(label) > 80 or _STOP_LABEL.fullmatch(label) is None:
        return None
    return label if quoted or _QUALIFIED_LABEL.search(label) is None else None


def _ordinal(value):
    return int(value) if value.isascii() and value.isdigit() else _ORDINALS[value.lower()]


def _slot(target):
    chinese = _CHINESE_SLOT.fullmatch(target)
    if chinese:
        return _ordinal(chinese[1] or chinese[2]), _PERIODS[chinese[3]]
    english = _ENGLISH_SLOT.fullmatch(target)
    if english:
        return _ordinal(english[1] or english[2]), _PERIODS[english[3].lower()]
    reversed_english = _ENGLISH_PERIOD_FIRST.fullmatch(target)
    if reversed_english:
        return _ordinal(reversed_english[2] or reversed_english[3]), _PERIODS[reversed_english[1].lower()]
    return None


def _known(observation):
    return observation['value'] if observation['state'] == 'known' else None


def _dated_slot(target):
    dated = _DATED_SLOT.fullmatch(target)
    if dated:
        return dated[1], _PERIODS[dated[2].lower()]
    english = _ENGLISH_DATED_SLOT.fullmatch(target)
    if english:
        return english[2], _PERIODS[english[1].lower()]
    return None


def _select(items, target, starts_on, ends_on):
    relative = _slot(target)
    dated = _dated_slot(target) if relative is None else None
    if relative is None and dated is None:
        return [item for item in items if item['text'].casefold() == target.casefold()]

    dates = [_known(item['schedule']['start']['date']) for item in items]
    if None in dates:
        return []
    if relative is not None:
        ordinal, (lower, upper) = relative
        displayed_dates = sorted(set(dates))
        if ordinal == -1:
            if ends_on is None or displayed_dates[-1:] != [ends_on.isoformat()]:
                return []
            day = ends_on.isoformat()
        elif starts_on is None or ordinal > len(displayed_dates):
            return []
        else:
            day = displayed_dates[ordinal - 1]
            # A relative edit must agree with both the calendar and the card.
            if (date.fromisoformat(day) - starts_on).days != ordinal - 1:
                return []
    else:
        day, (lower, upper) = dated
        if day not in dates:
            return []
    selected = []
    for item, item_date in zip(items, dates, strict=True):
        start = item['schedule']['start']
        end = item['schedule']['end']
        end_date = _known(end['date'])
        if end_date is None or (item_date != end_date and item_date <= day <= end_date):
            return []
        if item_date != day:
            continue
        start_clock, end_clock = _known(start['time']), _known(end['time'])
        if start_clock is None or end_clock is None:
            return []
        begins, ends = time.fromisoformat(start_clock), time.fromisoformat(end_clock)
        if lower <= begins < ends <= upper:
            selected.append(item)
        elif begins < upper and lower < ends:
            return []
    return selected


def select_lio_edit(trip, text, locale, request_id, *, starts_on, ends_on=None):
    """Return an exact provisional change. This does not authorize publication."""
    match = match_edit(text)
    if match is None:
        return None
    if trip is None:
        return LioEditSelection('clarify')
    document = json.loads(trip.content)
    interpretations = []
    for target, raw_replacement in _edit_parts(match):
        replacement = _replacement_label(raw_replacement)
        if target and replacement is not None:
            selected = _select(document['items'], target, starts_on, ends_on)
            interpretations.extend((item, replacement) for item in selected)
    if len(interpretations) != 1:
        return LioEditSelection('clarify')
    (item, replacement), = interpretations
    if item['text'] == replacement:
        return LioEditSelection('clarify')
    if item['fixed'] != {'state': 'known', 'value': False}:
        return LioEditSelection('protected')

    identity = dict(request_id=request_id, trip_id=trip.trip_id, expected_version=trip.version,
                    original_hash=sha256(trip.content).hexdigest())
    try:
        request = Request.parse(packed(dict(identity, version='TRIP-scoped-request.1',
            text=text, language='zh-Hans' if locale == 'zh' else 'en',
            selection=dict(kind='items', item_ids=[item['id']]))))
        selection = resolve(trip, request)
        if selection.status != 'READY':
            return LioEditSelection('clarify')
        edit = packed(dict(identity, version='TRIP-manual-edit.2', title=None, order=None,
                           changes=[dict(item_id=item['id'], field='text', value=replacement)]))
        candidate = preview(selection, edit)
    except (ValueError, Conflict):
        return LioEditSelection('clarify')
    if candidate.candidate is None:
        return LioEditSelection('clarify')
    return LioEditSelection('preview', candidate)
