"""FEEDBACK internal candidate. Requests carry user feedback, never diagnostics."""
from dataclasses import dataclass
import hashlib
import json
import re

VERSION = 'CJ-FEEDBACK-INTERNAL@0.2.0'


class InvalidInput(Exception):
    def __init__(self): super().__init__('invalid feedback input')


class Conflict(Exception):
    def __init__(self): super().__init__('feedback action input conflict')


class Unavailable(Exception):
    def __init__(self): super().__init__('feedback unavailable')


class ReferenceUnavailable(Unavailable):
    """Same result for unavailable, foreign and nonexistent references."""


class CommitUnknown(Exception):
    commit_possible = True
    recovery = 'reconcile_original'
    def __init__(self): super().__init__('query original feedback action')


def identifier(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value) is None:
        raise InvalidInput()
    return value


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise InvalidInput()
        result[key] = value
    return result


@dataclass(frozen=True, repr=False)
class Action:
    original: bytes

    def __post_init__(self):
        self.fields()  # Revalidated at every ingress; no derived mutable fields.

    def fields(self):
        if type(self.original) is not bytes or not 1 <= len(self.original) <= 16384:
            raise InvalidInput()
        try:
            value = json.loads(self.original.decode('utf-8'), object_pairs_hook=_object,
                               parse_constant=lambda _: (_ for _ in ()).throw(InvalidInput()))
            if type(value) is not dict or set(value) != {'action_id', 'problem', 'expectation', 'references'}:
                raise InvalidInput()
            identifier(value['action_id'])
            for key in ('problem', 'expectation'):
                s = value[key]
                if type(s) is not str or len(s.encode('utf-8')) > 6000 or '\x00' in s:
                    raise InvalidInput()
            if not value['problem'].strip(): raise InvalidInput()
            refs = value['references']
            if type(refs) is not list or len(refs) > 2: raise InvalidInput()
            kinds = set()
            for ref in refs:
                if type(ref) is not dict or set(ref) != {'kind', 'id'}: raise InvalidInput()
                if ref['kind'] not in ('message', 'run') or ref['kind'] in kinds: raise InvalidInput()
                rid = ref['id']
                if type(rid) is not str or not rid.strip() or '\x00' in rid or len(rid.encode('utf-8')) > 1024:
                    raise InvalidInput()
                kinds.add(ref['kind'])
            if refs and 'message' not in kinds: raise InvalidInput()
            return value
        except (UnicodeError, ValueError, TypeError, RecursionError):
            raise InvalidInput() from None

    @property
    def action_id(self): return self.fields()['action_id']

    @property
    def digest(self): return hashlib.sha256(self.original).hexdigest()


@dataclass(frozen=True)
class SourceReference:
    message_id: str
    conversation_id: str
    generation: str
    message_sequence: int
    run_id: str
    message_input_sha256: str
    run_status_at_read: str
    event_highwater_at_read: int

    def __post_init__(self):
        for value in (self.message_id, self.conversation_id, self.generation, self.run_id):
            if type(value) is not str or not value.strip(): raise Unavailable()
        if (type(self.message_sequence) is not int or self.message_sequence < 1
                or type(self.event_highwater_at_read) is not int or self.event_highwater_at_read < 0
                or type(self.message_input_sha256) is not str
                or re.fullmatch('[0-9a-f]{64}', self.message_input_sha256) is None
                or self.run_status_at_read not in ('queued','running','completed','failed','cancelled','context_invalid','unknown')):
            raise Unavailable()


@dataclass(frozen=True)
class Receipt:
    action_id: str
    input_sha256: str
    submitted_at: str
    status: str = 'submitted'
    message_en: str = 'Feedback submitted.'
    message_zh: str = '反馈已提交。'
    source: SourceReference | None = None
