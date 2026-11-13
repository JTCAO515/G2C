"""Sourced, internal planning context.2. Model updates never grant a write."""
from dataclasses import dataclass
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from cj_needs.domain import InvalidInput, decode
from cj_message.lio_exploration_schema import ProfileUpdate

from .lio_exploration_factors import BY_KEY, LABELS, defaults
from .lio_planning_grounding import NUMBERS
from .lio_positive_trip import supports as positive_trip_support,city_literal

CONTEXT = 'lio_planning_context.2:'
VERSION = 'lio_planning_context.2'
POLICY = '922-profile.1'
_DECLINED = re.compile(r'随便|都行|无所谓|不需要|不想回答|不想说|'
    r'no preference|anything|whatever|either is fine|prefer not to (?:say|answer)', re.I)
_CLAUSE = re.compile(r'[，,。；;\n]|\.(?=\s|$)|\b(?:but|however)\b|而是|不过|但是|但', re.I)
_RETURN_VISIT = re.compile(r'不是第一次(?:来)?|\bnot (?:my |our |the )?first (?:visit|time)\b', re.I)


def _positive_payload(key, text):
    """Only recognized affirmative wrappers can normalize a whole statement.

    Everything else stays literal. This is deliberately an allow-list, not a
    list of supposedly exhaustive negative/conditional words.
    """
    text = text.strip().rstrip('。.!！').strip()
    label = '|'.join(re.escape(v) for v in LABELS[key])
    selected = re.fullmatch(r'(?:'+label+r')\s*(?:改为|换成|是|[:：])\s*[:：]?\s*(.+)',text,re.I)
    if selected:
        return selected[1].strip()
    if key == 'city':
        selected = re.fullmatch(r'(?:I|we) (?:want|would like) to (?:visit|go to|travel to) (.+)|(?:我|我们)?想去(.+)',text,re.I)
        if selected:return selected[1] or selected[2]
    for pattern in (
        r'(?:I|we)\s+(?:(?:now|usually|always|generally)\s+)?(?:prefer|like|enjoy|want)\s+(.+)',
        r'(?:我|我们)?(?:更|通常|平时|比较)?(?:喜欢|偏好|想要|想体验|希望体验|选择)\s*(.+)'):
        selected = re.fullmatch(pattern,text,re.I)
        if selected:
            return re.sub(r'^(?:a|an|the)\s+','',selected[1],flags=re.I)
    if key == 'pace':
        selected = re.fullmatch(r'change (?:my |our )?(?:travel )?pace to (.+)',text,re.I)
        if selected:return selected[1]
        selected = re.fullmatch(r'(?:先|后来(?:改为|换成))(.+)',text)
        if selected:return selected[1]
    if key == 'first_visit':
        selected = re.fullmatch(r'this is (?:my |our )?(.+)',text,re.I)
        if selected:return selected[1]
    return text


def _source_clause(original, offset, quote):
    before = _CLAUSE.split(original[:offset])[-1]
    after = _CLAUSE.split(original[offset+len(quote):])[0]
    return before+quote+after


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


class _Updates(_DTO):
    version: Literal['LIO-profile-update.1']
    updates: list[ProfileUpdate] = Field(max_length=28)


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


def _canonical(key, text):
    # Map only a complete supported expression, never a keyword found inside an
    # arbitrary statement. Unknown Memory stays the exact opaque original text.
    payload = _positive_payload(key,text)
    aliases = _ALIASES.get(key, {})
    words = {word.casefold():value for value,forms in aliases.items() for word in forms}
    if aliases:
        # The finite bank's complete display expressions are also valid whole
        # answers. Do not fall back to substring matching for contextual labels.
        words.update({text.casefold():option.key for option in BY_KEY[key].options
                      for text in (option.zh,option.en)})
    if key == 'dietary':
        words.update({word:'mild' for word in ('i do not eat spicy food',"i don't eat spicy food",'do not eat spicy food')})
    if payload.casefold() in words:
        value=words[payload.casefold()]
        return (value,) if BY_KEY[key].multiple else value
    if aliases:
        form='|'.join(re.escape(word) for word in sorted(words,key=len,reverse=True))
        # A bounded positive noun suffix does not admit "dislike", a question,
        # quoted examples, negation or conditional clauses around a keyword.
        suffix=r'(?:\s+(?:travel|trip|trips|pace|travel pace|travel experiences)|旅行节奏|旅行|行程|节奏)?'
        pattern=r'(?:'+form+r')'+suffix
        if BY_KEY[key].multiple:
            pattern+=r'(?:(?:\s*(?:and|和|与|、|&)\s*)(?:'+form+r'))*'
        if re.fullmatch(pattern,payload,re.I):
            values=tuple(dict.fromkeys(words[m[0].casefold()] for m in re.finditer(form,payload,re.I)))
            return values if BY_KEY[key].multiple else values[0]
        return (text,) if BY_KEY[key].multiple else text
    return (payload,) if BY_KEY[key].multiple else payload


def _supported_source(update, clause, quote,cities=()):
    key=update.factor_key
    if _DECLINED.fullmatch(quote.strip()):
        return _positive_payload(key,clause).casefold() == quote.strip().casefold()
    if update.state == 'inferred':
        # Inference can cite a recognized affirmative source fact (for example
        # "with children"), but not an arbitrary phrase containing its keyword.
        for factor in BY_KEY.values():
            whole=_canonical(factor.key,clause);part=_canonical(factor.key,quote)
            allowed={option.key for option in factor.options}
            if whole == part and (isinstance(part,str) and part in allowed or
                    isinstance(part,tuple) and set(part) <= allowed):return True
        return False
    if positive_trip_support(key,clause,quote,cities):return True
    whole,part=_canonical(key,clause),_canonical(key,quote)
    if BY_KEY[key].multiple and isinstance(whole,tuple) and isinstance(part,tuple):
        return set(part) <= set(whole)
    return whole == part


def _known_value(update, sources):
    """Known values must be literal spans or canonical equivalents of those spans."""
    value = tuple(update.value) if isinstance(update.value, list) else update.value
    quotes = [source.quote for source in sources]
    if update.factor_key == 'duration_days':
        matches=[re.fullmatch(r'([0-9]{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|[一二两三四五六七八九十])\s*(?:天|日|days?)',
                 _positive_payload('duration_days',quote),re.I) for quote in quotes]
        if any(match is None for match in matches):
            raise InvalidInput('affirmative original duration required')
        counts = {int(match[1]) if match[1].isascii() and match[1].isdecimal() else NUMBERS[match[1].casefold()] for match in matches}
        if type(value) is int and 1 <= value <= 366 and counts == {value}:
            return value
    elif update.factor_key == 'first_visit':
        choices=set()
        for quote in quotes:
            payload=_positive_payload('first_visit',quote)
            if re.fullmatch(r'第一次(?:来)?|first visit|first time',payload,re.I):choices.add(True)
            elif re.fullmatch(r'来过中国|来过了|returning to china|been to china',payload,re.I) or _RETURN_VISIT.fullmatch(payload):choices.add(False)
            else:raise InvalidInput('affirmative original visit statement required')
        if type(value) is bool and choices == {value}:
            return value
    elif type(value) is str or isinstance(value, tuple):
        expected = [_canonical(update.factor_key, quote) for quote in quotes]
        if all(value == candidate for candidate in expected):
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
    cities=tuple(ref.quote for update in packet.updates if update.factor_key=='city' and update.state=='known'
        for ref in update.sources if update.value==ref.quote and city_literal(ref.quote))
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
            if not offsets or any(not _supported_source(update,
                    _source_clause(original.text,offset,ref.quote),ref.quote,cities) for offset in offsets):
                raise InvalidInput('profile quote is absent or negated')
            sources.append(Source(original.message_id, original.sequence, ref.quote, offsets[-1]))
        # The code recognizes explicit refusal regardless of a model's state
        # label, so "随便" cannot be smuggled back as known or inferred.
        declined = all(_DECLINED.fullmatch(s.quote.strip()) for s in sources)
        state = 'not_needed' if declined else update.state
        if state == 'not_needed':
            if not declined:
                raise InvalidInput('explicit profile refusal required')
            value = None
        elif state == 'inferred':
            if not factor.inferable or update.value is None:
                raise InvalidInput('factor cannot be inferred')
            value = tuple(update.value) if isinstance(update.value, list) else update.value
            allowed = {o.key for o in factor.options}
            if not (type(value) is str and value in allowed or
                    factor.multiple and isinstance(value, tuple) and value and len(value) == len(set(value)) and set(value) <= allowed):
                raise InvalidInput('bounded inferred factor value required')
        else:
            value = _known_value(update, sources)
        facts.append(Fact(factor.key, value, state, tuple(sources)))
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
        if fact.key not in result or result[fact.key].state in ('default','inferred'):
            result[fact.key] = fact
    for fact in sorted(updates, key=lambda fact: fact.order):
        old = result.get(fact.key)
        if old is not None:
            if fact.state == 'inferred' and old.state in ('known','not_needed','memory'):
                continue
            if old.state in ('known','not_needed') and fact.state in ('known','not_needed') and fact.order < old.order:
                continue
            if old.state == fact.state == 'inferred' and fact.order < old.order:
                continue
        result[fact.key] = fact
    return result


def default_proposals(profile, original):
    """Label planning defaults separately from user quotes and refusals.

    A literal exit supplies provenance for these proposals only. WP4/WP8 must
    still require the actual selected native4 policy before publishing a Trip;
    neither this data nor its policy string grants source/write authority.
    """
    if original.text.strip().casefold() not in ('直接出方案','plan now'):
        raise InvalidInput('original plan-now message required for default proposals')
    source = DefaultSource(original.message_id,POLICY)
    return tuple(Fact(key,value,'default',(source,)) for key,value in defaults(profile).items()
                 if key not in profile or profile[key].state == 'default')


def snapshot(profile,*,memory_epoch=None):
    """Plain internal event data, not a NEEDS contract or a save receipt."""
    def source(row):
        if isinstance(row, Source):
            return dict(kind='message', message_id=row.message_id, sequence=row.sequence,
                        quote=row.quote, offset=row.offset)
        if isinstance(row, MemorySource):
            return dict(kind='memory', slot=row.slot, source_id=row.source_id,
                        source_version=row.source_version, version=row.version, text=row.text)
        return dict(kind='default', message_id=row.message_id, policy=row.policy)
    return dict(version=VERSION,memory_epoch=memory_epoch, factors=[dict(factor_key=fact.key, value=fact.value,
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
    sources: list[_StoredSource | _StoredMemory | _StoredDefault] = Field(min_length=1, max_length=256)


class _Snapshot(_DTO):
    version: Literal['lio_planning_context.2']
    factors: list[_StoredFact] = Field(max_length=14)
    memory_epoch:int | None=Field(default=None,ge=0)


def decode_context(raw):
    """Validate persisted context at its read boundary, once."""
    try:
        stored = _Snapshot.model_validate(decode(raw.encode() if isinstance(raw, str) else raw))
    except ValidationError:
        raise InvalidInput('exact planning context.2 required') from None
    if len({fact.factor_key for fact in stored.factors}) != len(stored.factors):
        raise InvalidInput('duplicate profile factor')
    for fact in stored.factors:
        factor=BY_KEY.get(fact.factor_key)
        if factor is None:raise InvalidInput('unknown exploration factor')
        expected=(_StoredMemory if fact.state=='memory' else _StoredDefault if fact.state=='default' else _StoredSource)
        if any(not isinstance(source,expected) for source in fact.sources):
            raise InvalidInput('profile source kind differs from state')
        if fact.state=='memory' and any(source.slot not in factor.memory_slots for source in fact.sources):
            raise InvalidInput('profile Memory slot differs from factor')
    return stored


def restore(raw, originals, memory_run=None):
    return restore_context(decode_context(raw),originals,memory_run)


def restore_context(stored, originals, memory_run=None):
    """Rebind validated context to current protected originals/Memory.

    Stored memory/default projections never become fresh user authority. Memory
    is rebuilt from the current admitted capture; defaults must be recomputed and
    disclosed for the actual new planning selection by WP4/WP8.
    """
    by_mid = {original.message_id: index for index,original in enumerate(originals)}
    updates = []
    for fact in stored.factors:
        if fact.state in ('memory','default'):
            continue
        refs = []
        for source in fact.sources:
            if source.message_id not in by_mid:
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
