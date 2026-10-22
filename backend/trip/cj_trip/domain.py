"""Internal TRIP candidate v0.1; no HTTP schema or caller authorization."""
from dataclasses import dataclass
import hashlib
import json
import re

class Conflict(Exception): pass
class Denied(Exception): pass
class CommitUnknown(Exception): pass


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value):
        raise ValueError('invalid identifier')
    return value


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    trip_id: str
    expected_version: int
    basis_version: str
    expires_at: int
    content: bytes

    def __post_init__(self):
        for v in (self.proposal_id, self.trip_id, self.basis_version): identifier(v)
        if type(self.expected_version) is not int or self.expected_version < 0:
            raise ValueError('expected version required; zero means new trip')
        if type(self.expires_at) is not int or self.expires_at <= 0:
            raise ValueError('expiry required')
        if type(self.content) is not bytes or not 0 < len(self.content) <= 1_000_000:
            raise ValueError('immutable UTF-8 content required')
        # Minimal internal document, not the future PLACE/FACT or wire schema.
        doc = json.loads(self.content)
        if set(doc) != {'title', 'items'} or not isinstance(doc['title'], str) or not doc['title'].strip():
            raise ValueError('title and items required')
        if not isinstance(doc['items'], list) or not doc['items']:
            raise ValueError('empty trip rejected')
        seen = set()
        for item in doc['items']:
            if not isinstance(item, dict) or set(item) != {'id', 'text', 'verification', 'evidence'}:
                raise ValueError('explicit fact state required')
            identifier(item['id'])
            if item['id'] in seen: raise ValueError('duplicate item')
            seen.add(item['id'])
            if not isinstance(item['text'], str) or not item['text'].strip(): raise ValueError('empty text')
            if item['verification'] not in ('pending', 'verified'): raise ValueError('unknown fact state')
            if not isinstance(item['evidence'], list) or not all(isinstance(x, str) and x for x in item['evidence']): raise ValueError('invalid evidence')
            if item['verification'] == 'verified' and not item['evidence']: raise ValueError('verified needs evidence')
        # Reject duplicate JSON keys / alternate encodings: preserve accepted original bytes.
        if packed(doc) != self.content: raise ValueError('canonical content required')

    def digest(self, scope):
        return hashlib.sha256(packed([scope, self.proposal_id, self.trip_id, self.expected_version,
                                     self.basis_version, self.expires_at, self.content.decode('utf-8')])).hexdigest()


@dataclass(frozen=True)
class Action:
    action_id: str
    kind: str
    proposal_id: str
    candidate_hash: str
    confirmation_ref: str

    def __post_init__(self):
        for v in (self.action_id, self.proposal_id, self.confirmation_ref): identifier(v)
        if self.kind not in ('accept', 'reject'): raise ValueError('invalid action')
        if not isinstance(self.candidate_hash, str) or not re.fullmatch('[0-9a-f]{64}', self.candidate_hash): raise ValueError('hash required')

    def raw(self): return packed([self.action_id, self.kind, self.proposal_id, self.candidate_hash, self.confirmation_ref])


@dataclass(frozen=True)
class Receipt:
    action_id: str
    kind: str
    proposal_id: str
    candidate_hash: str
    trip_id: str
    committed_version: int | None


@dataclass(frozen=True)
class Trip:
    trip_id: str
    version: int
    content: bytes


@dataclass(frozen=True)
class ProposalDetail:
    proposal: Proposal
    candidate_hash: str
    status: str
