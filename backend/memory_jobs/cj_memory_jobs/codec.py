"""Bounded internal encoding of canonical committed MESSAGE values, never consent."""
from cj_strict_json import compact
from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
import json

from cj_message.domain import Command, Cursor, HistoryMessage, Receipt
from cj_strict_json import reject_duplicates


class InvalidInput(ValueError): pass
class Conflict(Exception): pass
class Unavailable(Exception): pass
class CommitUnknown(Exception): pass


class SourceKind(StrEnum):
    MANUAL = 'manual'
    COMMITTED_MESSAGE = 'committed_message'
    CONVERSATION_SUMMARY = 'conversation_summary'
    STAFF_PROPOSED = 'staff_proposed'  # Reserved only; no M3 producer.


def identity(value):
    if type(value) is not str or not value.strip() or len(value) > 256:
        raise InvalidInput('bounded original identity required')
    return value


def pg_identity(value, max_bytes):
    if type(value) is not str or not value.strip() or '\0' in value:
        raise InvalidInput('original PostgreSQL identity required')
    try:
        if len(value.encode('utf-8')) > max_bytes:
            raise InvalidInput('identity exceeds byte bound')
    except UnicodeError:
        raise InvalidInput('invalid identity Unicode') from None
    return value


def job_identity(value):
    identity(value)
    return pg_identity(value,1024)  # At most 256 Unicode characters, exact UTF8.


def integer(value, minimum=0):
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        raise InvalidInput('bounded integer required')
    return value


@dataclass(frozen=True)
class Source:
    # Internal source binding, NOT an authorization capability or wire DTO.
    cursor: Cursor
    source_version: int
    memory_epoch: int

    def validate(self):
        if type(self.cursor) is not Cursor:
            raise InvalidInput('canonical MESSAGE cursor required')
        for name in ('scope', 'conversation_id', 'generation'):
            identity(getattr(self.cursor, name))
        integer(self.cursor.epoch, 1)
        integer(self.cursor.after)
        integer(self.cursor.through)
        if self.cursor.after > self.cursor.through:
            raise InvalidInput('cursor order')
        integer(self.source_version, 1)
        integer(self.memory_epoch, 1)
        return self


@dataclass(frozen=True)
class SourceV2:
    """MESSAGE-SOURCE@1 comparison values, never a SourcePolicy or permit."""
    cursor: Cursor
    source_version: int
    withdrawal_epoch: int

    def validate(self):
        if type(self.cursor) is not Cursor:
            raise InvalidInput('canonical MESSAGE cursor required')
        pg_identity(self.cursor.scope,4096)
        pg_identity(self.cursor.conversation_id,1024)
        pg_identity(self.cursor.generation,1024)
        integer(self.cursor.epoch)  # Canonical MESSAGE initial epoch is zero.
        integer(self.cursor.after)
        integer(self.cursor.through)
        if self.cursor.after > self.cursor.through:
            raise InvalidInput('cursor order')
        integer(self.source_version, 1)
        integer(self.withdrawal_epoch, 1)
        return self


def encode(source, rows, mode):
    return _encode(source, rows, mode, 'CJ020-internal.1', Command.parse_stored)


def encode_v2(source, rows, mode):
    """Additive batch version for committed MESSAGE send.2/send.3/send.4 too."""
    return _encode(source, rows, mode, 'CJ020-internal.2', Command.parse_original)


def _encode(source, rows, mode, version, parse_command):
    expected_source = SourceV2 if version == 'CJ020-internal.2' else Source
    if type(source) is not expected_source:
        raise InvalidInput('internal source required')
    source.validate()
    if mode not in ('incremental', 'conversation_end') or type(rows) is not tuple:
        raise InvalidInput('unsupported batch')
    c = source.cursor
    if not 1 <= len(rows) <= 100 or len(rows) != c.through - c.after:
        raise InvalidInput('complete bounded cursor interval required')
    messages, seen = [], set()
    for index, row in enumerate(rows):
        if type(row) is not HistoryMessage or type(row.receipt) is not Receipt:
            raise InvalidInput('canonical MESSAGE history required')
        r = row.receipt
        for value in (r.message_id, r.conversation_id, r.generation, r.run_id):
            if version == 'CJ020-internal.2':
                pg_identity(value,32768)
            else:
                identity(value)
        integer(r.sequence, 1)
        if type(row.original_utf8) is not bytes or len(row.original_utf8) > 32768:
            raise InvalidInput('bounded immutable source required')
        try:
            command = parse_command(row.original_utf8)
        except (ValueError, KeyError, TypeError):
            raise InvalidInput('invalid committed message') from None
        if (r.conversation_id != c.conversation_id or r.generation != c.generation
                or r.sequence != c.after + index + 1 or r.message_id in seen
                or command.message_id != r.message_id
                or command.conversation_id != c.conversation_id
                or r.input_sha256 != hashlib.sha256(row.original_utf8).hexdigest()
                or row.text != json.loads(row.original_utf8)['text']):
            raise InvalidInput('message binding/digest/sequence mismatch')
        seen.add(r.message_id)
        messages.append({'receipt': asdict(r), 'original_utf8': row.original_utf8.decode('utf-8')})
    value = {'version': version, 'source': asdict(source), 'mode': mode, 'messages': messages}
    if version == 'CJ020-internal.2':
        value['source_kind'] = (SourceKind.COMMITTED_MESSAGE if mode == 'incremental'
                                else SourceKind.CONVERSATION_SUMMARY)
    raw = compact(value, sort_keys=True, ensure_ascii=True, allow_nan=True)
    if len(raw) > 262144:
        raise InvalidInput('batch exceeds local bound')
    return raw


def decode(raw):
    """Strict persisted codec; decoding conveys zero source or dispatch authority."""
    return _decode(raw, 'CJ020-internal.1', encode)


def decode_v2(raw):
    """V1 and V2 are explicit consumers, with no failed-parse fallback."""
    return _decode(raw, 'CJ020-internal.2', encode_v2)


def _decode(raw, version, encoder):
    if type(raw) is not bytes or len(raw) > 262144:
        raise InvalidInput('bounded bytes required')
    try:
        obj = json.loads(raw.decode('ascii'), object_pairs_hook=reject_duplicates(InvalidInput, 'duplicate field'))
        fields = {'version', 'source', 'mode', 'messages'}
        if version == 'CJ020-internal.2':
            fields.add('source_kind')
        if set(obj) != fields or obj['version'] != version:
            raise InvalidInput('unsupported persisted batch')
        s = obj['source']
        epoch_field = 'withdrawal_epoch' if version == 'CJ020-internal.2' else 'memory_epoch'
        if set(s) != {'cursor', 'source_version', epoch_field}:
            raise InvalidInput('unsupported source fields')
        source_type = SourceV2 if version == 'CJ020-internal.2' else Source
        source = source_type(Cursor(**s['cursor']), s['source_version'], s[epoch_field])
        rows = []
        for message in obj['messages']:
            if set(message) != {'receipt', 'original_utf8'}:
                raise InvalidInput('unsupported message fields')
            original = message['original_utf8'].encode('utf-8')
            rows.append(HistoryMessage(Receipt(**message['receipt']), original,
                                       json.loads(original)['text']))
        rows = tuple(rows)
        if encoder(source, rows, obj['mode']) != raw:
            raise InvalidInput('noncanonical persisted batch')
        return source, rows, obj['mode']
    except (TypeError, KeyError, AttributeError, UnicodeError, ValueError, RecursionError):
        raise InvalidInput('invalid persisted batch') from None
