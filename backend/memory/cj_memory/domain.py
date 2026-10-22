"""MEMORY internal candidate; trusted composition is the only entry authority."""
from dataclasses import dataclass
from datetime import datetime
import json

class InvalidInput(ValueError): pass
class Conflict(Exception): pass
class Unavailable(Exception): pass
class CommitUnknown(Exception): pass

@dataclass(frozen=True)
class Command:
    operation_id: str
    item_id: str
    subject: str
    slot: str
    kind: str
    text: str
    extent: str
    context_id: str | None
    source_id: str
    source_version: int
    occurred_at: str
    raw: bytes

    @classmethod
    def parse(cls, raw):
        def unique(pairs):
            obj = {}
            for k, v in pairs:
                if k in obj: raise InvalidInput('duplicate field')
                obj[k] = v
            return obj
        if type(raw) is not bytes or len(raw) > 32768: raise InvalidInput('bytes required')
        try: obj = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        except (ValueError, UnicodeError): raise InvalidInput('invalid JSON') from None
        fields = set(cls.__dataclass_fields__) - {'raw'}
        if type(obj) is not dict or set(obj) != fields: raise InvalidInput('unsupported fields')
        for k in fields - {'source_version', 'context_id'}:
            if type(obj[k]) is not str or not obj[k].strip() or len(obj[k]) > 4096:
                raise InvalidInput('invalid field')
        if obj['kind'] not in ('fact', 'experience', 'preference', 'inference'): raise InvalidInput('kind')
        if obj['extent'] not in ('long_term', 'current'): raise InvalidInput('extent')
        if obj['extent'] == 'long_term' and obj['context_id'] is not None: raise InvalidInput('context')
        if obj['extent'] == 'current' and (type(obj['context_id']) is not str or not obj['context_id'].strip()): raise InvalidInput('context')
        if type(obj['source_version']) is not int or obj['source_version'] < 1: raise InvalidInput('version')
        # Approximate time is a display value, explicitly supplied; never invent a date.
        return cls(**obj, raw=raw)

@dataclass(frozen=True)
class Receipt:
    operation_id: str
    item_id: str
    version: int
    status: str

@dataclass(frozen=True)
class Item:
    command: Command
    version: int
    status: str
    recorded_at: datetime

@dataclass(frozen=True)
class Context:
    items: tuple[Item, ...]
    # Entire scope epoch must be rechecked by RUN before publishing results.
    epoch: int

class Service:
    def __init__(self, repository): self.repository = repository

    def save(self, raw):
        c = Command.parse(raw)
        with self.repository.transaction() as tx:
            tx.lock_scope()
            old = tx.operation(c.operation_id)
            if old:
                if old[0] != raw: raise Conflict('operation bytes differ')
                result = old[1]
            else:
                # Authority row is installed by trusted composition, never by this service.
                confirmed = tx.source(c)
                status = 'active' if confirmed and c.kind != 'inference' else 'candidate'
                result = tx.insert(c, status)
        return result

    def query(self, operation_id):
        with self.repository.transaction() as tx:
            tx.lock_scope()
            old = tx.operation(operation_id)
        return old[1] if old else None  # Absence is not permission to resend an unknown action.

    def detail(self, item_id):
        with self.repository.transaction() as tx:
            tx.lock_scope()
            item = tx.detail(item_id)
        return item

    def groups(self):
        with self.repository.transaction() as tx:
            tx.lock_scope()
            result = tx.groups()
        return result

    def list_items(self, after=None, limit=50):
        if type(limit) is not int or not 1 <= limit <= 100: raise InvalidInput("limit")
        if after is not None and (type(after) is not str or not after): raise InvalidInput("after")
        with self.repository.transaction() as tx:
            tx.lock_scope()
            result = tx.list_items(after, limit)
        return result  # Live keyset page, not an immutable snapshot.

    def effective(self, subject, context_id=None):
        if type(subject) is not str or not subject: raise InvalidInput('subject')
        with self.repository.transaction() as tx:
            epoch = tx.lock_scope()
            rows = tx.effective(subject, context_id)
            # Explicit current constraints override the same canonical slot for this request only.
            selected = {i.command.slot: i for i in rows if i.command.extent == 'long_term'}
            selected.update({i.command.slot: i for i in rows if i.command.extent == 'current'})
        return Context(tuple(selected[k] for k in sorted(selected)), epoch)

    def check_fence(self, epoch):
        with self.repository.transaction() as tx:
            if tx.lock_scope() != epoch: raise Conflict('context changed')
        # RUN must hold this same scope lock through publication; a prior check alone is insufficient.
