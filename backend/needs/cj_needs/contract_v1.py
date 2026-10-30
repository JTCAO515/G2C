"""NEEDS@1.0 data codec; owner, freshness and publication permission stay external."""
import base64
import binascii
from hashlib import sha256
import json

from .domain import (Command, InvalidInput, Revision, Snapshot, decode, exact,
                     identifier, validate_fields)

VERSION = 'NEEDS@1.0'
COMMAND_VERSION = 'NEEDS-command.1'
SNAPSHOT_VERSION = 'NEEDS-snapshot.1'
REVISION_VERSION = 'NEEDS-revision.1'
MAX_BYTES = 524288


def _dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')


def _load(raw):
    # The larger envelope contains base64 originals; domain.decode keeps the
    # existing smaller limit for commands and persisted content.
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise InvalidInput('bounded NEEDS envelope required')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise InvalidInput('duplicate NEEDS field')
            value[key] = item
        return value
    def constant(_): raise InvalidInput('nonfinite NEEDS value')
    try:
        return json.loads(raw.decode('utf8'), object_pairs_hook=unique, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise InvalidInput('invalid NEEDS envelope') from None


def _bytes(value):
    if type(value) is not str: raise InvalidInput('base64 original required')
    try: raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error): raise InvalidInput('invalid base64 original') from None
    if base64.b64encode(raw).decode('ascii') != value:
        raise InvalidInput('canonical base64 required')
    return raw


def encode_command(command: Command) -> bytes:
    return _dump(dict(version=COMMAND_VERSION,
                      original_input_utf8_base64=base64.b64encode(command.raw).decode('ascii')))


def decode_command(raw: bytes) -> Command:
    value = _load(raw)
    exact(value, ('version', 'original_input_utf8_base64'))
    if value['version'] != COMMAND_VERSION: raise InvalidInput('unsupported NEEDS command version')
    return Command(_bytes(value['original_input_utf8_base64']))


def _record(value):
    identifier(value['needs_id'])
    if type(value['revision']) is not int or not 1 <= value['revision'] < 2**63:
        raise InvalidInput('positive NEEDS revision required')
    if value['source_kind'] != 'user_provided': raise InvalidInput('unsupported NEEDS source')
    content = _bytes(value['content_utf8_base64'])
    fields = decode(content)
    validate_fields(fields, complete=True)
    if value['content_sha256'] != sha256(content).hexdigest():
        raise InvalidInput('NEEDS content association mismatch')
    return content, fields


def _value(record, version):
    value = dict(version=version, needs_id=record.needs_id, revision=record.version,
                 source_kind=record.source_kind,
                 content_utf8_base64=base64.b64encode(record.content).decode('ascii'),
                 content_sha256=sha256(record.content).hexdigest())
    # Snapshot/Revision are legacy DB row carriers, not validated domain objects.
    # Serialization is the persisted-data boundary, so validate the row here.
    _, fields = _record(value)
    return value, fields


def encode_snapshot(snapshot: Snapshot) -> bytes:
    value, _ = _value(snapshot, SNAPSHOT_VERSION)
    return _dump(value)


def decode_snapshot(raw: bytes) -> Snapshot:
    value = _load(raw)
    exact(value, ('version', 'needs_id', 'revision', 'source_kind',
                  'content_utf8_base64', 'content_sha256'))
    if value['version'] != SNAPSHOT_VERSION: raise InvalidInput('unsupported NEEDS snapshot version')
    content, _ = _record(value)
    return Snapshot(value['needs_id'], value['revision'], content)


def _revision(value, content, fields):
    identifier(value['action_id'])
    command = Command(_bytes(value['original_input_utf8_base64']))
    original = command.data
    if (original['needs_id'], original['action_id'], original['expected_version'] + 1) != (
            value['needs_id'], value['action_id'], value['revision']):
        raise InvalidInput('NEEDS original revision mismatch')
    if any(name not in fields or fields[name] != changed for name, changed in original['changes'].items()):
        raise InvalidInput('NEEDS original patch mismatch')
    if value['revision'] == 1 and fields != original['changes']:
        raise InvalidInput('NEEDS initial content mismatch')
    return Revision(value['needs_id'], value['revision'], value['action_id'], command.raw, content)


def encode_revision(revision: Revision) -> bytes:
    value, fields = _value(revision, REVISION_VERSION)
    value.update(action_id=revision.action_id,
                 original_input_utf8_base64=base64.b64encode(revision.original_input).decode('ascii'))
    _revision(value, revision.content, fields)
    return _dump(value)


def decode_revision(raw: bytes) -> Revision:
    value = _load(raw)
    exact(value, ('version', 'needs_id', 'revision', 'source_kind', 'content_utf8_base64',
                  'content_sha256', 'action_id', 'original_input_utf8_base64'))
    if value['version'] != REVISION_VERSION: raise InvalidInput('unsupported NEEDS history version')
    content, fields = _record(value)
    return _revision(value, content, fields)
