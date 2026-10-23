"""Bounded internal encoding of canonical committed MESSAGE values, never consent."""
from dataclasses import asdict, dataclass
import hashlib
import json

from cj_message.domain import Command, Cursor, HistoryMessage, Receipt


class InvalidInput(ValueError): pass
class Conflict(Exception): pass
class Unavailable(Exception): pass
class CommitUnknown(Exception): pass


def identity(value):
    if type(value) is not str or not value.strip() or len(value) > 256:
        raise InvalidInput('bounded original identity required')
    return value


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


def encode(source, rows, mode):
    if type(source) is not Source:
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
            identity(value)
        integer(r.sequence, 1)
        if type(row.original_utf8) is not bytes or len(row.original_utf8) > 32768:
            raise InvalidInput('bounded immutable source required')
        try:
            command = Command.parse(row.original_utf8)
        except ValueError:
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
    raw = json.dumps({'version': 'CJ020-internal.1', 'source': asdict(source),
                      'mode': mode, 'messages': messages}, ensure_ascii=True,
                     sort_keys=True, separators=(',', ':')).encode('ascii')
    if len(raw) > 262144:
        raise InvalidInput('batch exceeds local bound')
    return raw


def decode(raw):
    """Strict persisted codec; decoding conveys zero source or dispatch authority."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InvalidInput('duplicate field')
            result[key] = value
        return result
    if type(raw) is not bytes or len(raw) > 262144:
        raise InvalidInput('bounded bytes required')
    try:
        obj = json.loads(raw.decode('ascii'), object_pairs_hook=unique)
        if set(obj) != {'version', 'source', 'mode', 'messages'} or obj['version'] != 'CJ020-internal.1':
            raise InvalidInput('unsupported persisted batch')
        s = obj['source']
        if set(s) != {'cursor', 'source_version', 'memory_epoch'}:
            raise InvalidInput('unsupported source fields')
        source = Source(Cursor(**s['cursor']), s['source_version'], s['memory_epoch'])
        rows = []
        for message in obj['messages']:
            if set(message) != {'receipt', 'original_utf8'}:
                raise InvalidInput('unsupported message fields')
            original = message['original_utf8'].encode('utf-8')
            rows.append(HistoryMessage(Receipt(**message['receipt']), original,
                                       json.loads(original)['text']))
        rows = tuple(rows)
        if encode(source, rows, obj['mode']) != raw:
            raise InvalidInput('noncanonical persisted batch')
        return source, rows, obj['mode']
    except (TypeError, KeyError, AttributeError, UnicodeError, ValueError, RecursionError):
        raise InvalidInput('invalid persisted batch') from None
