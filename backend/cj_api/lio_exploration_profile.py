"""Sourced, internal planning context.2. Model updates never grant a write."""
from dataclasses import dataclass
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from cj_needs.domain import InvalidInput, decode

from .lio_exploration_factors import BY_KEY
from .lio_planning_grounding import NUMBERS

CONTEXT = 'lio_planning_context.2:'
VERSION = 'lio_planning_context.2'
POLICY = '922-profile.1'
_DECLINED = re.compile(r'随便|都行|无所谓|不需要|不想回答|不想说|'
    r'no preference|anything|whatever|either is fine|prefer not to (?:say|answer)', re.I)
_NEGATED = re.compile(r'(?:不是|并非|不要|不选|不想|不喜欢|not|never|rather than)\s*$', re.I)


@dataclass(frozen=True)
class Original:
    """A host-protected original MESSAGE, not client-provided evidence."""
    message_id: str
    sequence: int
    text: str


@dataclass(frozen=True)
class Source:
    message_id: str
    sequence: int
    quote: str
    offset: int


@dataclass(frozen=True)
class MemorySource:
    slot: str
    source_id: str
    source_version: int
    version: int
    text: str


@dataclass(frozen=True)
class DefaultSource:
    message_id: str
    policy: str


@dataclass(frozen=True)
class Fact:
    key: str
    value: object
    state: str
    sources: tuple[Source | MemorySource | DefaultSource, ...]

    @property
    def order(self):
        return max((s.sequence, s.offset) for s in self.sources if isinstance(s, Source))


class _DTO(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class _Quote(_DTO):
    source_index: int = Field(ge=0)
    quote: str = Field(min_length=1, max_length=4000)


class _Update(_DTO):
    factor_key: str
    value: str | int | bool | list[str] | None
    state: Literal['known', 'not_needed', 'inferred']
    sources: list[_Quote] = Field(min_length=1, max_length=8)


class _Updates(_DTO):
    version: Literal['LIO-profile-update.1']
    updates: list[_Update] = Field(max_length=28)


_ALIASES = {
    'pace': {'relaxed': ('轻松','悠闲','慢节奏','relaxed','leisurely','slow'),
             'moderate': ('适中','中等','moderate','balanced'),
             'packed': ('紧凑','密集','packed','fast')},
    'party_type': {'solo': ('一个人','一人','solo','alone'),
                   'two_adults': ('两个成人','two adults'),
                   'family': ('带孩子','with children'), 'friends': ('和朋友','with friends')},
    'season': {'spring': ('春季','春天','spring'), 'summer': ('夏季','夏天','summer'),
               'autumn': ('秋季','秋天','autumn','fall'), 'winter': ('冬季','冬天','winter')},
    'lodging_tier': {'simple': ('简洁实用','经济型','simple and practical','budget-friendly'),
                     'comfortable': ('舒适型','comfortable'), 'luxury': ('高端型','豪华','奢华','luxury','luxurious')},
    'interests': {'history': ('历史','history','historic'), 'food': ('美食','food'),
                  'nature': ('山水','自然','nature','scenery'), 'modern': ('现代城市','modern city')},
    'dietary': {'none': ('无饮食限制','no dietary restrictions'),
                'mild': ('不吃辣','no spicy food','do not eat spicy','avoid spicy'),
                'vegetarian': ('素食','vegetarian'), 'halal': ('清真','halal')},
}


def _has(text, phrase):
    pattern = re.escape(phrase)
    if phrase.isascii():
        pattern = r'(?<![A-Za-z])'+pattern+r'(?![A-Za-z])'
    return re.search(pattern, text, re.I) is not None


def _canonical(key, text):
    aliases = _ALIASES.get(key, {})
    values = tuple(value for value, words in aliases.items() if any(_has(text, w) for w in words))
    if BY_KEY[key].multiple:
        return values or (text,)
    return values[0] if len(values) == 1 else text


def _known_value(update, sources):
    """Known values must be literal spans or canonical equivalents of those spans."""
    value = tuple(update.value) if isinstance(update.value, list) else update.value
    quotes = [source.quote for source in sources]
    if update.factor_key == 'duration_days':
        counts = {int(raw) if raw.isascii() and raw.isdecimal() else NUMBERS[raw.casefold()]
                  for quote in quotes for raw in re.findall(
                      r'(?<![A-Za-z0-9])([0-9]{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|[一二两三四五六七八九十])\s*(?:天|日|days?)(?![A-Za-z])', quote, re.I)}
        if type(value) is int and 1 <= value <= 366 and counts == {value}:
            return value
    elif update.factor_key == 'first_visit':
        choices = {True for quote in quotes if re.fullmatch(r'第一次(?:来)?|first visit|first time', quote, re.I)}
        choices |= {False for quote in quotes if re.fullmatch(r'来过中国|来过了|returning to china|been to china', quote, re.I)}
        if type(value) is bool and choices == {value}:
            return value
    elif type(value) is str or isinstance(value, tuple):
        expected = [_canonical(update.factor_key, quote) for quote in quotes]
        if value in expected:
            return value
        if BY_KEY[update.factor_key].multiple and isinstance(value, tuple) and value and len(set(value)) == len(value):
            combined = tuple(dict.fromkeys(v for group in expected for v in group))
            if set(value) == set(combined):
                return value
    raise InvalidInput('profile value differs from its original quote')


def parse_updates(raw, originals):
    """Validate untrusted model JSON once against protected original text/MIDs."""
    try:
        packet = _Updates.model_validate(decode(raw.encode() if isinstance(raw, str) else raw))
    except ValidationError:
        raise InvalidInput('exact sourced profile updates required') from None
    facts = []
    for update in packet.updates:
        factor = BY_KEY.get(update.factor_key)
        if factor is None:
            raise InvalidInput('unknown exploration factor')
        sources = []
        for ref in update.sources:
            if ref.source_index >= len(originals) or not ref.quote.strip():
                raise InvalidInput('original profile quote required')
            original = originals[ref.source_index]
            offsets = [match.start() for match in re.finditer(re.escape(ref.quote), original.text)]
            if not offsets or any(_NEGATED.search(original.text[:offset]) for offset in offsets):
                raise InvalidInput('profile quote is absent or negated')
            sources.append(Source(original.message_id, original.sequence, ref.quote, offsets[-1]))
        if update.state == 'not_needed':
            if update.value is not None or not all(_DECLINED.fullmatch(s.quote.strip()) for s in sources):
                raise InvalidInput('explicit profile refusal required')
            value = None
        elif update.state == 'inferred':
            if not factor.inferable or update.value is None:
                raise InvalidInput('factor cannot be inferred')
            value = tuple(update.value) if isinstance(update.value, list) else update.value
            allowed = {o.key for o in factor.options}
            if not (type(value) is str and value in allowed or
                    factor.multiple and isinstance(value, tuple) and value and len(value) == len(set(value)) and set(value) <= allowed):
                raise InvalidInput('bounded inferred factor value required')
        else:
            value = _known_value(update, sources)
        facts.append(Fact(factor.key, value, update.state, tuple(sources)))
    return tuple(facts)


def memory_prefill(memory_run):
    """Consume the already captured, admitted Memory payload, never a model copy.

    The caller retains the real RuntimeRun hold through final publication. Every
    turn rebuilds this projection from the current snapshot. A manual Memory
    source has its actual ID/version/text; it has no invented chat MID or quote.
    """
    if memory_run is None:
        return ()
    data = json.loads(memory_run.payload)
    facts = []
    for factor in BY_KEY.values():
        rows = [row for row in data['items'] if row['subject'] == 'self' and row['slot'] in factor.memory_slots]
        if rows:
            sources = tuple(MemorySource(row['slot'], row['source_id'], row['source_version'], row['version'], row['text']) for row in rows)
            # Two saved slots for one factor are both retained, not silently
            # resolved by unrelated per-item version numbers.
            value = _canonical(factor.key, sources[0].text) if len(sources) == 1 else tuple(source.text for source in sources)
            facts.append(Fact(factor.key, value, 'memory', sources))
    return tuple(facts)


def merge(previous, updates, memory=()):
    """Code, not the model, determines precedence. Never writes long-term Memory."""
    result = {key: fact for key, fact in previous.items() if fact.state != 'memory'}
    for fact in memory:
        if fact.key not in result or result[fact.key].state == 'default':
            result[fact.key] = fact
    for fact in sorted(updates, key=lambda fact: fact.order):
        old = result.get(fact.key)
        if old is not None:
            if fact.state == 'inferred' and old.state in ('known','not_needed','memory'):
                continue
            if old.state in ('known','not_needed','inferred') and fact.order < old.order:
                continue
        result[fact.key] = fact
    return result


def snapshot(profile):
    """Plain internal event data, not a NEEDS contract or a save receipt."""
    def source(row):
        if isinstance(row, Source):
            return dict(kind='message', message_id=row.message_id, sequence=row.sequence,
                        quote=row.quote, offset=row.offset)
        if isinstance(row, MemorySource):
            return dict(kind='memory', slot=row.slot, source_id=row.source_id,
                        source_version=row.source_version, version=row.version, text=row.text)
        return dict(kind='default', message_id=row.message_id, policy=row.policy)
    return dict(version=VERSION, factors=[dict(factor_key=fact.key, value=fact.value,
        state=fact.state, sources=[source(s) for s in fact.sources]) for fact in profile.values()])


class _StoredSource(_DTO):
    kind: Literal['message']
    message_id: str
    sequence: int
    quote: str = Field(min_length=1, max_length=4000)
    offset: int = Field(ge=0)


class _StoredMemory(_DTO):
    kind: Literal['memory']
    slot: str
    source_id: str
    source_version: int
    version: int
    text: str


class _StoredDefault(_DTO):
    kind: Literal['default']
    message_id: str
    policy: str


class _StoredFact(_DTO):
    factor_key: str
    value: str | int | bool | list[str] | None
    state: Literal['known','not_needed','inferred','default','memory']
    sources: list[_StoredSource | _StoredMemory | _StoredDefault] = Field(min_length=1, max_length=8)


class _Snapshot(_DTO):
    version: Literal['lio_planning_context.2']
    factors: list[_StoredFact] = Field(max_length=14)


def restore(raw, originals, memory_run=None):
    """Read persisted state at the boundary; rebind all retained user evidence.

    Stored memory/default projections never become fresh user authority. Memory
    is rebuilt from the current admitted capture; defaults must be recomputed and
    disclosed for the actual new planning selection by WP4/WP8.
    """
    try:
        stored = _Snapshot.model_validate(decode(raw.encode() if isinstance(raw, str) else raw))
    except ValidationError:
        raise InvalidInput('exact planning context.2 required') from None
    if len({fact.factor_key for fact in stored.factors}) != len(stored.factors):
        raise InvalidInput('duplicate profile factor')
    by_mid = {original.message_id: index for index,original in enumerate(originals)}
    updates = []
    for fact in stored.factors:
        if fact.factor_key not in BY_KEY:
            raise InvalidInput('unknown exploration factor')
        if fact.state in ('memory','default'):
            expected = _StoredMemory if fact.state == 'memory' else _StoredDefault
            if any(not isinstance(source,expected) for source in fact.sources):
                raise InvalidInput('profile source kind differs from state')
            continue
        refs = []
        for source in fact.sources:
            if not isinstance(source,_StoredSource) or source.message_id not in by_mid:
                raise InvalidInput('protected original profile source unavailable')
            index = by_mid[source.message_id]
            original = originals[index]
            if (source.sequence != original.sequence or
                    original.text[source.offset:source.offset+len(source.quote)] != source.quote):
                raise InvalidInput('persisted profile source differs from original')
            refs.append(dict(source_index=index,quote=source.quote))
        updates.append(dict(factor_key=fact.factor_key,value=fact.value,state=fact.state,sources=refs))
    parsed = parse_updates(json.dumps(dict(version='LIO-profile-update.1',updates=updates)), originals)
    return merge({}, parsed, memory_prefill(memory_run))
