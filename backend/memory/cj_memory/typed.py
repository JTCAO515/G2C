"""Additive MEMORY-manual.2 / stored-command.2; selectors are data, not permits."""
from dataclasses import dataclass
import hashlib
import json

from .domain import Command, InvalidInput

MANUAL_VERSION = 'MEMORY-manual.2'
STORED_VERSION = 'MEMORY-command.2'


def decode(raw, *, maximum=32768):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InvalidInput('duplicate field')
            result[key] = value
        return result
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise InvalidInput('bounded original UTF8 bytes required')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise InvalidInput('invalid JSON') from None
    if type(value) is not dict:
        raise InvalidInput('object required')
    return value


def travel_selection(value):
    from cj_message.travel import Selection
    from cj_message.domain import InvalidInput as MessageInvalidInput
    try:
        return Selection.parse(value)
    except MessageInvalidInput as error:
        raise InvalidInput('invalid original travel selection') from error


def packed(value):
    try:
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    except (ValueError, UnicodeError):
        raise InvalidInput('UTF8 values required') from None


@dataclass(frozen=True)
class ContextRef:
    kind: str
    id: str

    def __post_init__(self):
        if (self.kind not in ('legacy', 'travel') or type(self.id) is not str
                or not self.id.strip() or len(self.id) > 4096):
            raise InvalidInput('explicit context kind/id required')
        self.id.encode('utf-8')


@dataclass(frozen=True)
class TypedCommand(Command):
    typed_kind: str
    context_version: int | None

    @property
    def context_kind(self):
        return self.typed_kind

    @property
    def schema_version(self):
        return 2

    @classmethod
    def parse(cls, raw):
        value = decode(raw)
        base_fields = set(Command.__dataclass_fields__) - {'raw'}
        if (set(value) != base_fields | {'version', 'context_kind', 'context_version'}
                or value['version'] != STORED_VERSION):
            raise InvalidInput('unsupported stored command version/fields')
        base = Command.parse(packed({key:value[key] for key in base_fields}))
        kind, version = value['context_kind'], value['context_version']
        if base.extent == 'long_term':
            if kind != 'legacy' or version is not None:
                raise InvalidInput('long-term has no current context')
        else:
            if kind != 'travel' or type(version) is not int or version < 1:
                raise InvalidInput('typed current requires original travel version')
            ContextRef(kind, base.context_id)
        return cls(**{key:value[key] for key in base_fields}, raw=raw,
                   typed_kind=kind, context_version=version)


def parse_manual(raw):
    value = decode(raw)
    fields = set(Command.__dataclass_fields__) - {'raw','source_id','source_version','context_id'}
    if set(value) != fields | {'version','context'} or value['version'] != MANUAL_VERSION:
        raise InvalidInput('unsupported typed manual fields/version')
    context = value['context']
    if value['extent'] == 'long_term':
        if context is not None:
            raise InvalidInput('long-term context must be null')
        kind, identifier, version = 'legacy', None, None
    elif value['extent'] == 'current':
        if (type(context) is not dict or set(context) != {'kind','id','expected_version'}
                or context['kind'] != 'travel' or type(context['expected_version']) is not int
                or context['expected_version'] < 1):
            raise InvalidInput('explicit original travel reference required')
        selected=travel_selection({'id':context['id'],'expected_version':context['expected_version']})
        kind, identifier, version = 'travel', selected.id, selected.expected_version
    else:
        raise InvalidInput('unsupported extent')
    stored = {key:value[key] for key in fields}
    stored.update(version=STORED_VERSION, context_id=identifier, context_kind=kind,
                  context_version=version, source_id='manual-v2:'+hashlib.sha256(raw).hexdigest(),
                  source_version=1)
    return TypedCommand.parse(packed(stored))


def parse_stored(raw):
    # Only explicit V2 storage opts into this dispatch; legacy readers stay strict.
    value = decode(raw)
    return TypedCommand.parse(raw) if 'version' in value else Command.parse(raw)


def save_manual(service, raw, authority, principal):
    """Protected host only; genuine B M/T lease spans the canonical Memory commit."""
    from contextlib import nullcontext
    from .domain import Conflict, Unavailable
    from .manual import ManualPolicy
    command = parse_manual(raw)

    def original(tx):
        stored = tx.operation(command.operation_id)
        if stored is not None and stored[0] != raw:
            raise Conflict('operation bytes differ')
        return stored

    # Historical replay needs fresh owner admission, not a renewed travel permit.
    # Release MEMORY before acquiring M/T; never invert B's frozen lock order.
    with service.repository.transaction() as tx:
        tx.lock_scope()
        stored = original(tx)
    if stored is not None:
        return stored[1]
    if command.extent == 'current':
        from cj_message.travel_reference import MessageContextAuthority
        from cj_message.travel import Selection
        if (type(authority) is not MessageContextAuthority
                or authority.repository.scope != service.repository.scope
                or authority.admit() != principal):
            raise Unavailable('canonical principal-bound travel authority required')
        held = authority.hold_current(Selection(command.context_id,command.context_version))
    else:
        held = nullcontext(None)
    with held as lease:
        with service.repository.transaction() as tx:
            tx.lock_scope()
            stored = original(tx)
            if stored is not None:
                result = stored[1]
            else:
                if not tx.typed_context or type(service.manual_policy) is not ManualPolicy:
                    raise Unavailable('explicit typed storage and collection policy required')
                resolved = service.manual_policy.evaluate(command,raw)
                if lease is not None:
                    lease.check()
                tx.create_manual_source(command,resolved,service.manual_policy.expires_at)
                confirmed = tx.source(command)
                result = tx.insert(command,'active' if confirmed and command.kind!='inference' else 'candidate',
                                   operation_raw=raw)
                if lease is not None:
                    lease.check()
    return result
