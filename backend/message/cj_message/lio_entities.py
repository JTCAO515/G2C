"""Entity links: the places of the place library that an answer names (#1989, D-1; LIO-answer-rich.1).

The server decides what is tappable, never the model. `link` finds library places in the final visible
answer by name and alias; `effect` stores the result bound to the answer's sha-256; `wire` is what a read
sends: it drops everything when the answer changed and re-checks each entry against the current library.
Ranges are half-open and count Unicode scalar values (Python `str` indices) over the complete answer.

Off by default: `CJ_LIO_ENTITIES=on` writes the effect, and a row carries `rich.entities` only for a poll
that declared LIO-answer-rich.1 while `CJ_LIO_ANSWER_RICH=on` as well. The library itself (`cj_fact.places`)
holds only human-approved places, and holds none until the first review is merged: with no library the
linker returns nothing.
"""
from hashlib import sha256
from functools import lru_cache
import json
import os
import re
import unicodedata

ENTITIES_EFFECT = 'lio_entities:'
LIBRARY_VERSION = 'g2c-places.1'
MAX_ENTITIES = 20
SPAN = (2, 32)
MAX_ANSWER_SCALARS = 200000
MIN_NAME = {'zh': 2, 'en': 4}
_PLACE_ID = re.compile(r'pl_[a-z]{2}_[a-z0-9]+(?:_[a-z0-9]+)*')
_MARKDOWN = set('*_`[]()<>#|\\~!')
# A Chinese match followed by one of these is a different place (王府井站 is a station).
ZH_STOP_SUFFIXES = ('号线', '机场', '大道', '胡同', '路', '街', '站', '区', '市', '县', '镇', '村', '口')
EN_STOP_SUFFIXES = (' station', ' road', ' street', ' avenue', ' line', ' district', ' airport')
_SKIP = re.compile(r'```.*?```|`[^`\n]*`|\[[^\]\n]*\]\([^)\n]*\)|https?://\S+', re.S)
_HAS_HAN = re.compile(r'[㐀-鿿]')
_ASCII_WORD = re.compile(r'[A-Za-z0-9]')

# adcode prefix of the confirmed destination -> library city (a district code lies inside its city's prefix)
_ADCODE_CITY = (('1101', 'beijing'), ('11', 'beijing'), ('31', 'shanghai'), ('4401', 'guangzhou'), ('4403', 'shenzhen'),
                ('5101', 'chengdu'), ('50', 'chongqing'))


def _switch(name):
    value = os.environ.get(name, 'off')
    if value not in ('off', 'on'):
        raise ValueError('explicit ' + name + ' value required')
    return value == 'on'


def entities_enabled():
    """`CJ_LIO_ENTITIES`: write the effect. Default off; anything but off/on is a configuration error."""
    return _switch('CJ_LIO_ENTITIES')


def rich_enabled():
    """`CJ_LIO_ANSWER_RICH`: a rich declaration returns `rich` (off: the followups.1 row, never a 400)."""
    return _switch('CJ_LIO_ANSWER_RICH')


def city_for_adcode(adcode):
    """The library city of a confirmed destination (`CityReference.adcode`), or None for any other city."""
    if type(adcode) is not str or not re.fullmatch(r'[0-9]{6}', adcode):
        return None
    for prefix, city in _ADCODE_CITY:
        if adcode.startswith(prefix):
            return city
    return None


def _fold(text):
    """Case-fold without changing the length, so offsets in the folded copy are offsets in the original."""
    return ''.join(c.casefold() if len(c.casefold()) == 1 else c for c in text)


def _approved(place):
    review = place.get('review')
    return type(review) is dict and review.get('status') == 'approved'


def _names(place):
    """(name, language) pairs that may be matched: long enough, no Markdown character, at most 32 scalars."""
    found = []
    for field, language in (('name_zh', 'zh'), ('aliases_zh', 'zh'), ('name_en', 'en'), ('aliases_en', 'en')):
        value = place.get(field)
        for name in ([value] if type(value) is str else value if type(value) is list else []):
            if (type(name) is str and name == name.strip() and MIN_NAME[language] <= len(name) <= SPAN[1]
                    and not _MARKDOWN & set(name)):
                found.append((name, language))
    return found


def span_ok(answer, start, end):
    """The span rules every entity obeys, on a complete answer (the checker of the contract applies the same)."""
    if not (type(start) is int and type(end) is int and 0 <= start and SPAN[0] <= end - start <= SPAN[1]
            and end <= len(answer) <= MAX_ANSWER_SCALARS):
        return False
    piece = answer[start:end]
    if piece != piece.strip() or '\n' in piece or '\r' in piece or _MARKDOWN & set(piece):
        return False

    def regional(index):
        return 0 <= index < len(answer) and 0x1F1E6 <= ord(answer[index]) <= 0x1F1FF
    if start > 0 and answer[start - 1] == '‍':
        return False
    if regional(start - 1) and regional(start) or regional(end - 1) and regional(end):
        return False
    if end < len(answer):
        following = answer[end]
        code = ord(following)
        if (following == '‍' or unicodedata.category(following) in ('Mn', 'Mc', 'Me') or 0xFE00 <= code <= 0xFE0F
                or 0xE0100 <= code <= 0xE01EF or 0x1F3FB <= code <= 0x1F3FF or code == 0x20E3 or 0xE0020 <= code <= 0xE007F):
            return False
    if any(answer.startswith(suffix, end) for suffix in ZH_STOP_SUFFIXES if _HAS_HAN.search(piece[-1:])):
        return False
    if any(_fold(answer[end:end + len(suffix)]) == suffix for suffix in EN_STOP_SUFFIXES):
        return False
    if _ASCII_WORD.match(piece[-1:]) and end < len(answer) and _ASCII_WORD.match(answer[end]):
        return False
    if _ASCII_WORD.match(piece[:1]) and start > 0 and _ASCII_WORD.match(answer[start - 1]):
        return False
    return True


def link(answer, docs):
    """`[(start, end, place_id), …]` for the approved places of `docs` (library city documents) named in `answer`.

    Left to right, the longest name first, no overlap, never inside a Markdown link, code or a URL, each place
    only the first time it appears, at most MAX_ENTITIES. Fewer links rather than a wrong one: a doubtful
    match is skipped.
    """
    if type(answer) is not str or not answer or len(answer) > MAX_ANSWER_SCALARS:
        return []
    folded = _fold(answer)
    skipped = [m.span() for m in _SKIP.finditer(answer)]

    def inside_skipped(start, end):
        return any(s < end and start < e for s, e in skipped)

    candidates = []
    for doc in docs:
        for place in doc.get('places', ()):
            if type(place) is not dict or not _approved(place) or not _PLACE_ID.fullmatch(str(place.get('id'))):
                continue
            for name, language in _names(place):
                needle = _fold(name) if language == 'en' else name
                haystack = folded if language == 'en' else answer
                at = haystack.find(needle)
                while at != -1:
                    candidates.append((at, -len(name), place['id'], at + len(name)))
                    at = haystack.find(needle, at + 1)
    candidates.sort()
    taken, linked, seen, last_end = [], [], set(), 0
    for start, _, place_id, end in candidates:
        if start < last_end or place_id in seen or inside_skipped(start, end) or not span_ok(answer, start, end):
            continue
        linked.append((start, end, place_id))
        seen.add(place_id)
        last_end = end
        if len(linked) == MAX_ENTITIES:
            break
    return linked


def answer_sha256(answer):
    return sha256(answer.encode('utf-8')).hexdigest()


def effect(answer, items):
    """The stored effect: the hash of the exact answer the ranges were computed on, the ranges, the library version."""
    return ENTITIES_EFFECT + json.dumps(dict(answer_sha256=answer_sha256(answer), items=[list(item) for item in items],
                                             places=LIBRARY_VERSION), separators=(',', ':'), sort_keys=True)


def wire(effect_value, answer, is_approved):
    """`rich.entities` for a row, or None. `effect_value` is the stored effect string, `answer` the answer the row
    is about to send, `is_approved(place_id)` the current library. Everything is dropped when the answer's hash
    differs; an entry that no longer passes is dropped alone. Never raises."""
    try:
        payload = json.loads(effect_value.removeprefix(ENTITIES_EFFECT))
        if (type(payload) is not dict or set(payload) != {'answer_sha256', 'items', 'places'} or payload['places'] != LIBRARY_VERSION
                or type(payload['items']) is not list or type(answer) is not str
                or payload['answer_sha256'] != answer_sha256(answer)):
            return None
        rows, seen, last_end = [], set(), 0
        for item in payload['items'][:MAX_ENTITIES]:
            if type(item) is not list or len(item) != 3:
                continue
            start, end, place_id = item
            if (type(place_id) is not str or not _PLACE_ID.fullmatch(place_id) or len(place_id) > 64 or place_id in seen
                    or not span_ok(answer, start, end) or start < last_end or not is_approved(place_id)):
                continue
            rows.append(dict(type='place', start=start, end=end, place_id=place_id))
            seen.add(place_id)
            last_end = end
        return rows or None
    except Exception:   # a stored value of any shape reads as nothing; the row still goes out
        return None


# -- the library, read lazily (cj_fact is not imported until a switch is on) ------------------------------------

def library_docs(city):
    """The approved-place documents to link from for a destination city, or [] (no library copy, no city)."""
    if city is None:
        return []
    from cj_fact.places import load_city
    from cj_fact.policy import FactFailure
    try:
        return [load_city(city)]
    except FactFailure:
        return []


@lru_cache(maxsize=1)
def approved_ids():
    """Every approved place id of the library as a frozenset (the read-side check)."""
    from cj_fact.places import CITIES, load_city
    from cj_fact.policy import FactFailure
    found = set()
    for city in CITIES:
        try:
            doc = load_city(city)
        except FactFailure:
            continue
        found.update(place['id'] for place in doc['places'] if _approved(place))
    return frozenset(found)


def entity_effect(answer, adcode, docs=None):
    """The effect string for a finished answer, or None (switch off, no confirmed library city, nothing linked).

    `docs` lets a test supply library documents; production reads `cj_fact.places`."""
    if not entities_enabled() or type(answer) is not str or not answer.strip():
        return None
    city = city_for_adcode(adcode)
    documents = docs if docs is not None else library_docs(city)
    items = link(answer, documents)
    return effect(answer, items) if items else None
