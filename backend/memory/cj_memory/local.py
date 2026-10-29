"""Explicit local manual-collection policy; no production or permissive defaults.

Canonical slot identity and collection consent are operator configuration, not
model/user flags. Text is retained verbatim as an explicit user declaration;
this module does not infer facts, translate values or classify free-form text.
"""
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import stat
from types import MappingProxyType
from typing import Mapping

from .manual import ManualPolicy


class LocalMemoryConfigurationError(ValueError):
    pass


def _strings(value, *, empty=False):
    if (type(value) is not list or (not value and not empty)
            or any(type(v) is not str or not v.strip() or len(v) > 4096 for v in value)
            or len(set(value)) != len(value)):
        raise LocalMemoryConfigurationError('invalid explicit policy set')
    for item in value:
        item.encode('utf-8')
    return frozenset(value)


@dataclass(frozen=True)
class SlotPolicy:
    kind: str
    collection_allowed: bool
    semantic_resolved: bool


@dataclass(frozen=True)
class LocalMemoryProfile:
    subjects: frozenset[str]
    slots: Mapping[str, SlotPolicy]
    extents: frozenset[str]
    context_ids: frozenset[str]
    expires_at: datetime

    def content_allowed(self, command, original):
        entry = self.slots[command.slot]
        return entry.collection_allowed and command.kind in (entry.kind, 'inference')

    def semantic_resolved(self, command, original):
        # This attests the configured canonical subject/slot, never truth of text.
        # Inference remains candidate regardless of this flag (owned Service rule).
        return self.slots[command.slot].semantic_resolved

    def manual_policy(self):
        return ManualPolicy(subjects=self.subjects, slots=frozenset(self.slots),
                            extents=self.extents, context_ids=self.context_ids,
                            expires_at=self.expires_at, content_allowed=self.content_allowed,
                            semantic_resolved=self.semantic_resolved)


@dataclass(frozen=True)
class LocalMemoryConfiguration:
    # Keys are authenticated local JWT subjects, not request owner/subject fields.
    profiles: Mapping[str, LocalMemoryProfile]

    @classmethod
    def from_bytes(cls, raw):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result: raise LocalMemoryConfigurationError('duplicate policy field')
                result[key] = value
            return result
        try:
            if type(raw) is not bytes or not 0 < len(raw) <= 262144:
                raise LocalMemoryConfigurationError('bounded policy bytes required')
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
            if (type(value) is not dict or set(value) != {'version', 'expires_at', 'profiles'}
                    or value['version'] != 'local-memory-policy.1'):
                raise LocalMemoryConfigurationError('explicit policy format required')
            expiry = datetime.fromisoformat(value['expires_at'])
            if expiry.tzinfo is None or expiry.utcoffset() is None:
                raise LocalMemoryConfigurationError('explicit policy deadline offset required')
            rows = value['profiles']
            if type(rows) is not dict or not rows:
                raise LocalMemoryConfigurationError('explicit identity profiles required')
            profiles = {}
            for subject, profile in rows.items():
                if type(subject) is not str or not subject.strip() or len(subject) > 4096:
                    raise LocalMemoryConfigurationError('invalid identity profile')
                subject.encode('utf-8')
                if type(profile) is not dict or set(profile) != {'subjects', 'slots', 'extents', 'context_ids'}:
                    raise LocalMemoryConfigurationError('explicit profile fields required')
                slots = {}
                if type(profile['slots']) is not dict or not profile['slots']:
                    raise LocalMemoryConfigurationError('explicit canonical slots required')
                for slot, entry in profile['slots'].items():
                    if type(slot) is not str or not slot.strip() or len(slot) > 4096:
                        raise LocalMemoryConfigurationError('invalid canonical slot')
                    slot.encode('utf-8')
                    if (type(entry) is not dict or set(entry) != {'kind', 'collection_allowed', 'semantic_resolved'}
                            or entry['kind'] not in ('fact', 'experience', 'preference')
                            or type(entry['collection_allowed']) is not bool
                            or type(entry['semantic_resolved']) is not bool):
                        raise LocalMemoryConfigurationError('explicit slot approval required')
                    slots[slot] = SlotPolicy(**entry)
                extents = _strings(profile['extents'])
                if not extents <= {'long_term', 'current'}:
                    raise LocalMemoryConfigurationError('invalid policy extent')
                profiles[subject] = LocalMemoryProfile(_strings(profile['subjects']), MappingProxyType(slots),
                    extents, _strings(profile['context_ids'], empty=True), expiry)
            return cls(MappingProxyType(profiles))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise LocalMemoryConfigurationError('invalid local memory policy') from None


def read_private_policy(path):
    try:
        path = Path(path)
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077
                or not 0 < info.st_size <= 262144):
            raise LocalMemoryConfigurationError('private operator policy file required')
        return path.read_bytes()
    except (OSError, TypeError, ValueError):
        raise LocalMemoryConfigurationError('local memory policy unavailable') from None


def load_local_memory_configuration(path):
    return LocalMemoryConfiguration.from_bytes(read_private_policy(path))
