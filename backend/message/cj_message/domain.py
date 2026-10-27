"""Pure message rules; does not import contract fixtures or authenticate callers."""
from dataclasses import dataclass
import hashlib
import json
import uuid


class InvalidInput(ValueError):
    pass


class InputConflict(Exception):
    pass


class Unavailable(Exception):
    pass


class ResyncRequired(Exception):
    pass


class CommitUnknown(Exception):
    """Caller must query original action; never automatically retry a commit."""


@dataclass(frozen=True)
class Command:
    conversation_id: str
    message_id: str
    raw: bytes

    @classmethod
    def parse(cls, raw):
        def pairs(items):
            result = {}
            for k, v in items:
                if k in result:
                    raise InvalidInput('duplicate field')
                result[k] = v
            return result
        if type(raw) is not bytes:
            raise InvalidInput('immutable UTF-8 bytes required')
        try:
            obj = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
        except (ValueError, UnicodeError) as exc:
            raise InvalidInput('invalid input') from exc
        fields = {'version', 'conversation_id', 'message_id', 'text', 'trip_id', 'creation_intent'}
        if not isinstance(obj, dict) or set(obj) != fields:
            raise InvalidInput('unsupported fields')
        if obj['version'] != 'MESSAGE-draft.1':
            raise InvalidInput('unsupported version')
        if any(not isinstance(obj[k], str) or not obj[k].strip() for k in ('conversation_id', 'message_id', 'text')):
            raise InvalidInput('empty identity/text')
        if obj['trip_id'] is not None:
            raise InvalidInput('non-null Trip not supported')
        if obj['creation_intent'] not in ('none', 'consider_trip'):
            raise InvalidInput('unsupported intent')
        return cls(obj['conversation_id'], obj['message_id'], raw)


@dataclass(frozen=True)
class Receipt:
    message_id: str
    conversation_id: str
    generation: str
    sequence: int
    run_id: str
    input_sha256: str


@dataclass(frozen=True)
class Stored:
    raw: bytes
    receipt: Receipt


@dataclass(frozen=True)
class Chat:
    generation: str
    epoch: int
    last_sequence: int


@dataclass(frozen=True)
class Cursor:
    # Internal repository value only. Must never be deserialized from caller fields.
    scope: str
    conversation_id: str
    generation: str
    epoch: int
    through: int
    after: int


class Service:
    """Repository is pre-scoped by a future trusted AUTH composition root.

    This class is intentionally NOT an authorization entry point. No client owner
    argument, token parser, default principal or public route is supplied.
    """
    def __init__(self, repository, new_run_id):
        self.repository = repository
        self.new_run_id = new_run_id

    def receive(self, raw):
        command = Command.parse(raw)
        with self.repository.transaction() as tx:
            # Scope lock serializes same-ID requests even across conversations.
            tx.lock_scope()
            old = tx.find(command.message_id)
            if old is not None:
                if old.raw != command.raw:
                    raise InputConflict()
                receipt = old.receipt
                tx.chat(receipt.conversation_id, receipt.generation)
            else:
                chat = tx.chat(command.conversation_id)
                receipt = Receipt(command.message_id, command.conversation_id,
                                  chat.generation, chat.last_sequence + 1,
                                  self.new_run_id(), hashlib.sha256(raw).hexdigest())
                tx.insert(Stored(raw, receipt))
                tx.enqueue(receipt)
        # Only leave the transaction with a receipt after commit has succeeded.
        return receipt

    def open_conversation(self, conversation_id):
        """Idempotently create an active chat for this scope; never reactivates an inactive one."""
        if (type(conversation_id) is not str or not conversation_id.strip()
                or len(conversation_id.encode('utf-8')) > 256 or '\x00' in conversation_id):
            raise InvalidInput('conversation ID required')
        with self.repository.transaction() as tx:
            tx.lock_scope()
            try:
                return tx.chat(conversation_id)
            except Unavailable:
                created = tx.open_chat(conversation_id, uuid.uuid4().hex)
                if created is None:
                    raise  # exists but inactive (or recreated elsewhere)
                return created

    def query(self, message_id):
        with self.repository.transaction() as tx:
            tx.lock_scope()
            old = tx.find(message_id)
            if old is not None:
                tx.chat(old.receipt.conversation_id, old.receipt.generation)
        # None means absent in this ledger; production retention policy still gates retry.
        return old

    def page(self, conversation_id, cursor=None, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput('invalid limit')
        with self.repository.transaction() as tx:
            tx.lock_scope()
            chat = tx.chat(conversation_id)
            if cursor is None:
                cursor = Cursor(self.repository.scope, conversation_id, chat.generation,
                                chat.epoch, chat.last_sequence, 0)
            if (type(cursor) is not Cursor or
                (cursor.scope, cursor.conversation_id, cursor.generation, cursor.epoch) !=
                (self.repository.scope, conversation_id, chat.generation, chat.epoch) or
                not 0 <= cursor.after <= cursor.through <= chat.last_sequence):
                raise ResyncRequired()
            rows = tx.page(conversation_id, cursor.generation, cursor.after, cursor.through, limit)
            # A hole is not an empty/successful history page.
            expected = min(limit, cursor.through - cursor.after)
            if len(rows) != expected or any(r.sequence != cursor.after + i + 1 for i, r in enumerate(rows)):
                raise ResyncRequired()
            after = rows[-1].sequence if rows else cursor.after
            nxt = (Cursor(cursor.scope, conversation_id, chat.generation, chat.epoch,
                          cursor.through, after) if after < cursor.through else None)
        return rows, nxt

    def conversations(self, cursor=None, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput('invalid limit')
        with self.repository.transaction() as tx:
            tx.lock_scope()
            generation, epoch, highwater = tx.list_boundary()
            if cursor is None:
                cursor = ChatListCursor(self.repository.scope, generation, epoch, highwater, 0)
            if (type(cursor) is not ChatListCursor or
                (cursor.scope, cursor.scope_generation, cursor.epoch) !=
                (self.repository.scope, generation, epoch) or
                not 0 <= cursor.after <= cursor.through <= highwater):
                raise ResyncRequired()
            rows = tx.conversations(cursor.after, cursor.through, limit + 1)
            more = len(rows) > limit
            rows = rows[:limit]
            nxt = (ChatListCursor(cursor.scope, generation, epoch, cursor.through,
                                  rows[-1].list_sequence) if more else None)
        return rows, nxt

    def message_history(self, conversation_id, cursor=None, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput('invalid limit')
        with self.repository.transaction() as tx:
            tx.lock_scope()
            chat = tx.chat(conversation_id)
            if cursor is None:
                cursor = Cursor(self.repository.scope, conversation_id, chat.generation,
                                chat.epoch, chat.last_sequence, 0)
            if (type(cursor) is not Cursor or
                (cursor.scope, cursor.conversation_id, cursor.generation, cursor.epoch) !=
                (self.repository.scope, conversation_id, chat.generation, chat.epoch) or
                not 0 <= cursor.after <= cursor.through <= chat.last_sequence):
                raise ResyncRequired()
            stored = tx.history(conversation_id, chat.generation, cursor.after, cursor.through, limit)
            if len(stored) != min(limit, cursor.through - cursor.after):
                raise ResyncRequired()
            rows = []
            for index, item in enumerate(stored):
                command = Command.parse(item.raw)
                if (item.receipt.sequence != cursor.after + index + 1 or
                    command.message_id != item.receipt.message_id or
                    command.conversation_id != conversation_id or
                    hashlib.sha256(item.raw).hexdigest() != item.receipt.input_sha256):
                    raise ResyncRequired()
                rows.append(HistoryMessage(item.receipt, item.raw, json.loads(item.raw)['text']))
            after = rows[-1].receipt.sequence if rows else cursor.after
            nxt = Cursor(cursor.scope, conversation_id, chat.generation, chat.epoch, cursor.through, after) if after < cursor.through else None
        return rows, nxt

    def read_draft(self, conversation_id, generation):
        if not isinstance(generation, str) or not generation:
            raise InvalidInput('explicit generation required')
        with self.repository.transaction() as tx:
            tx.lock_scope()
            tx.chat(conversation_id, generation)
            result = tx.draft(conversation_id, generation)
        return result

    def save_draft(self, conversation_id, generation, original_utf8, expected_revision):
        if (not isinstance(generation, str) or not generation or type(original_utf8) is not bytes
                or type(expected_revision) is not int or expected_revision < 0):
            raise InvalidInput('invalid draft')
        try:
            original_utf8.decode('utf-8')
        except UnicodeError:
            raise InvalidInput('invalid draft') from None
        with self.repository.transaction() as tx:
            tx.lock_scope()
            tx.chat(conversation_id, generation)
            old = tx.draft(conversation_id, generation)
            revision = old.revision if old else 0
            if expected_revision != revision:
                raise InputConflict()
            result = Draft(conversation_id, generation, revision + 1, original_utf8)
            tx.save_draft(result)
        return result

    def pending(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput('invalid limit')
        with self.repository.transaction() as tx:
            tx.lock_scope()
            return tx.pending(limit)
        # Returns stored run IDs only; RUN/AUTH/USAGE adapters must authorize actual dispatch.

    def acknowledge(self, receipt):
        """Mark one delivery handled after RUN holds its outcome. Idempotent; never deletes."""
        if type(receipt) is not Receipt:
            raise InvalidInput('stored receipt required')
        with self.repository.transaction() as tx:
            tx.lock_scope()
            old = tx.find(receipt.message_id)
            if old is None or old.receipt != receipt:
                raise InputConflict()
            tx.acknowledge(receipt.message_id, receipt.run_id)


@dataclass(frozen=True)
class ChatSummary:
    conversation_id: str
    generation: str
    epoch: int
    list_sequence: int


@dataclass(frozen=True)
class ChatListCursor:
    # Internal value, never deserialize caller-provided scope/generations as authority.
    scope: str
    scope_generation: str
    epoch: int
    through: int
    after: int


@dataclass(frozen=True)
class HistoryMessage:
    receipt: Receipt
    original_utf8: bytes
    text: str


@dataclass(frozen=True)
class Draft:
    conversation_id: str
    generation: str
    revision: int
    original_utf8: bytes
