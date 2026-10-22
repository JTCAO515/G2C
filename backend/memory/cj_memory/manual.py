"""Manual-source producer. Policy is server configuration, never request fields."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Callable
from .domain import Command, InvalidInput, Unavailable


def parse_manual(raw):
    # Reuse the strict Command decoder after adding ONLY server-derived source fields.
    if type(raw) is not bytes or len(raw) > 32768:
        raise InvalidInput('bytes required')
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result: raise InvalidInput('duplicate field')
            result[k] = v
        return result
    try:
        obj = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise InvalidInput('invalid JSON') from None
    fields = set(Command.__dataclass_fields__) - {'raw', 'source_id', 'source_version'}
    if type(obj) is not dict or set(obj) != fields:
        raise InvalidInput('manual fields only; source and approval are server-owned')
    # Exact original UTF8 includes operation_id: no normalization, translation or re-key.
    # Prefix identifies server manual provenance in the existing source namespace.
    obj['source_id'] = 'manual-v1:' + hashlib.sha256(raw).hexdigest()
    obj['source_version'] = 1
    return Command.parse(json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


@dataclass(frozen=True)
class ManualPolicy:
    """Explicit server-approved collection policy; no permissive defaults.

    content_allowed(c, original_utf8) must check sensitive collection/consent and
    reference ownership. semantic_resolved(c, original_utf8) attests the canonical
    subject/slot equivalence; UNKNOWN/False stays candidate. Neither is an LLM here.
    expires_at is an explicitly approved deadline, not an invented product duration.
    """
    subjects: frozenset[str]
    slots: frozenset[str]
    extents: frozenset[str]
    context_ids: frozenset[str]
    expires_at: datetime
    content_allowed: Callable[[Command, bytes], bool]
    semantic_resolved: Callable[[Command, bytes], bool]

    def __post_init__(self):
        for name in ('subjects', 'slots', 'extents', 'context_ids'):
            values = getattr(self, name)
            if type(values) is not frozenset or any(type(v) is not str or not v.strip() for v in values):
                raise ValueError('explicit immutable policy sets required')
        if not self.subjects or not self.slots or not self.extents or not self.extents <= {'long_term', 'current'}:
            raise ValueError('explicit manual scope required')
        if (not isinstance(self.expires_at, datetime) or self.expires_at.tzinfo is None
                or self.expires_at.utcoffset() is None or not callable(self.content_allowed)
                or not callable(self.semantic_resolved)):
            raise ValueError('explicit deadline and policy checks required')

    def evaluate(self, c, raw):
        if (c.subject not in self.subjects or c.slot not in self.slots
                or c.extent not in self.extents
                or (c.extent == 'current' and c.context_id not in self.context_ids)
                or self.expires_at <= datetime.now(timezone.utc)):
            raise Unavailable('manual policy unavailable')
        try:
            if self.content_allowed(c, raw) is not True:
                raise Unavailable('manual policy unavailable')
            resolved = self.semantic_resolved(c, raw) is True
        except Exception:
            raise Unavailable('manual policy unavailable') from None
        return resolved
