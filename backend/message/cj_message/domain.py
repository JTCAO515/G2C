"""Pure message rules; does not import contract fixtures or authenticate callers."""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING
import hashlib
import json
import uuid

if TYPE_CHECKING:
    from .travel import Selection
    from .trip_context import TripSelection
    from .travel_reference import OriginalMessageContextRef


class InvalidInput(ValueError):
    pass


class InputConflict(Exception):
    pass


class SequenceConflict(Exception):
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
    expected_generation: str | None = None
    expected_sequence: int | None = None
    travel_context: Selection | None = None
    needs_reference: tuple[str, int] | None = None
    trip_context: TripSelection | None = None
    modification_intent: str = 'none'

    @classmethod
    def parse(cls, raw):
        return cls._parse(raw, stored=False)

    @classmethod
    def parse_stored(cls, raw):
        """Historical draft.1 bytes remain readable; they never grant a new send."""
        return cls._parse(raw, stored=True)

    @classmethod
    def parse_v2(cls, raw):
        return cls._parse(raw, stored=False, travel=True)

    @classmethod
    def parse_v3(cls, raw):
        return cls._parse(raw, stored=False, travel=True, formal=True)

    @classmethod
    def parse_v4(cls,raw):
        from .edit_input import parse
        return parse(raw)

    @classmethod
    def parse_original(cls, raw):
        version = json.loads(raw)["version"]
        if version == "MESSAGE-send.4": return cls.parse_v4(raw)
        if version == "MESSAGE-send.3": return cls.parse_v3(raw)
        if version == "MESSAGE-send.2": return cls.parse_v2(raw)
        return cls.parse_stored(raw)

    @classmethod
    def _parse(cls, raw, *, stored, travel=False, formal=False):
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
        if not isinstance(obj, dict):
            raise InvalidInput('unsupported fields')
        version = obj.get('version')
        if version == 'MESSAGE-send.1':
            fields |= {'expected_generation', 'expected_sequence'}
        elif version == 'MESSAGE-send.3' and formal:
            fields |= {'expected_generation', 'expected_sequence', 'travel_context', 'needs_reference', 'trip_context'}
        elif version == 'MESSAGE-send.2' and travel:
            fields |= {'expected_generation', 'expected_sequence', 'travel_context', 'needs_reference'}
        elif version != 'MESSAGE-draft.1' or not stored:
            raise InvalidInput('unsupported version')
        if set(obj) != fields:
            raise InvalidInput('unsupported fields')
        if any(not isinstance(obj[k], str) or not obj[k].strip() for k in ('conversation_id', 'message_id', 'text')):
            raise InvalidInput('empty identity/text')
        if obj['trip_id'] is not None:
            raise InvalidInput('non-null Trip not supported')
        if obj['creation_intent'] not in ('none', 'consider_trip'):
            raise InvalidInput('unsupported intent')
        if travel and version != ('MESSAGE-send.3' if formal else 'MESSAGE-send.2'):
            raise InvalidInput('send.2 required')
        selection, needs = None, None
        if version in ('MESSAGE-send.2', 'MESSAGE-send.3'):
            from .travel import Selection
            from cj_needs.domain import identifier, InvalidInput as NeedsInvalid
            if obj['travel_context'] is not None:
                selection = Selection.parse(obj['travel_context'])
            value = obj['needs_reference']
            if obj['creation_intent'] == 'none':
                if value is not None:
                    raise InvalidInput('none intent requires null NEEDS reference')
            else:
                if (type(value) is not dict or set(value) != {'id', 'expected_version'}
                        or type(value['expected_version']) is not int
                        or not 1 <= value['expected_version'] <= 9223372036854775807):
                    raise InvalidInput('explicit NEEDS reference required')
                try:
                    needs = (identifier(value['id']), value['expected_version'])
                except NeedsInvalid as exc:
                    raise InvalidInput('invalid NEEDS identity') from exc
        if formal and obj['creation_intent'] != 'none':
            raise InvalidInput('send.3 is a read-only discussion version')
        trip = None
        if formal and obj['trip_context'] is not None:
            from .trip_context import TripSelection
            trip = TripSelection.parse(obj['trip_context'])
            if selection is not None or needs is not None or obj['creation_intent'] != 'none':
                raise InvalidInput('formal Trip discussion cannot grant creation authority')
        if version in ('MESSAGE-send.1', 'MESSAGE-send.2', 'MESSAGE-send.3'):
            if (len(obj['conversation_id'].encode('utf-8')) > 256 or '\x00' in obj['conversation_id']
                    or type(obj['expected_generation']) is not str or not obj['expected_generation'].strip()
                    or type(obj['expected_sequence']) is not int or obj['expected_sequence'] < 0):
                raise InvalidInput('invalid expected head')
        return cls(obj['conversation_id'], obj['message_id'], raw,
                   obj.get('expected_generation'), obj.get('expected_sequence'), selection, needs, trip)


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
    travel_reference_version: int | None = None
    trip_reference_version: int | None = None
    edit_reference_version: int | None = None


@dataclass(frozen=True)
class Chat:
    generation: str
    epoch: int
    last_sequence: int


@dataclass(frozen=True)
class SendStatus:
    stored: Stored | None
    head: Chat | None


@dataclass(frozen=True)
class TravelAcceptance:
    receipt: Receipt
    reference: OriginalMessageContextRef


@dataclass(frozen=True)
class TravelSendStatus:
    stored: Stored | None
    head: Chat | None
    reference: OriginalMessageContextRef | None


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
        return self._receive(raw, travel=False)

    def receive_v2(self, raw):
        return self._receive(raw, travel=True)

    def receive_v4(self,raw):
        from .edit_reference import receive
        return receive(self,raw)

    def receive_v3(self, raw):
        return self._receive(raw,travel=True,formal=True)

    def _receive(self, raw, *, travel, formal=False):
        command = Command.parse_v3(raw) if formal else Command.parse_v2(raw) if travel else Command.parse(raw)
        with self.repository.transaction() as tx:
            # Scope lock serializes same-ID requests even across conversations.
            tx.lock_scope()
            old = tx.find(command.message_id)
            if old is not None:
                if old.raw != command.raw:
                    raise InputConflict()
                receipt = old.receipt
            else:
                chat = tx.chat(command.conversation_id)
                if (chat.generation, chat.last_sequence) != (command.expected_generation, command.expected_sequence):
                    raise SequenceConflict()
                if travel:
                    from .travel_reference import require_producer
                    if formal:
                        from .trip_reference import require_producer as require_trip
                        source=require_trip(tx,command)
                    else:
                        require_producer(tx,command)
                receipt = Receipt(command.message_id, command.conversation_id,
                                  chat.generation, chat.last_sequence + 1,
                                  self.new_run_id(), hashlib.sha256(raw).hexdigest())
                stored=Stored(raw,receipt)
                if travel:
                    from .travel_reference import insert_reference
                    tx.insert(stored,command=command)
                    if formal:
                        from .trip_reference import insert_reference as insert_trip
                        insert_trip(tx,stored,command,source)
                    else:
                        insert_reference(tx,stored,command)
                else:
                    tx.insert(stored)
                tx.enqueue(receipt)
            if travel:
                from .travel_reference import read_reference
                reference=read_reference(tx,Stored(raw,receipt))
        # Only leave the transaction with a receipt after commit has succeeded.
        return TravelAcceptance(receipt,reference) if travel else receipt

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

    def query_edit_message(self,message_id,*,require_active=True):
        from .edit_reference import read
        from .travel_reference import OriginalTravelMessage
        with self.repository.transaction() as tx:
            tx.lock_scope();stored=tx.find(message_id)
            if stored is None:return None
            if require_active:tx.chat(stored.receipt.conversation_id,stored.receipt.generation)
            if stored.edit_reference_version!=1:raise Unavailable('edit read requires original send.4')
            result=OriginalTravelMessage(stored,read(tx,stored))
        return result

    def query_trip_message(self,message_id, *, require_active=True):
        return self.query_travel_message(message_id,require_active=require_active,formal=True)

    def query_travel_message(self,message_id, *, require_active=True, formal=False):
        from .travel_reference import read_reference,OriginalTravelMessage
        with self.repository.transaction() as tx:
            tx.lock_scope()
            stored=tx.find(message_id)
            if stored is None:return None
            if require_active:
                tx.chat(stored.receipt.conversation_id,stored.receipt.generation)
            if (stored.trip_reference_version!=1 if formal else stored.travel_reference_version!=1):
                raise Unavailable('travel read requires original send.2')
            result=OriginalTravelMessage(stored,read_reference(tx,stored))
        return result

    def send_status(self, conversation_id, message_id=None):
        return self._send_status(conversation_id,message_id,travel=False)

    def send_status_v4(self,conversation_id,message_id=None):
        return self._send_status(conversation_id,message_id,travel=True,formal=True,edit=True)

    def send_status_v3(self, conversation_id, message_id=None):
        return self._send_status(conversation_id,message_id,travel=True,formal=True)

    def send_status_v2(self, conversation_id, message_id=None):
        return self._send_status(conversation_id,message_id,travel=True)

    def _send_status(self, conversation_id, message_id, *, travel, formal=False, edit=False):
        if (type(conversation_id) is not str or not conversation_id.strip()
                or len(conversation_id.encode('utf-8')) > 256 or '\x00' in conversation_id
                or (message_id is not None and (type(message_id) is not str or not message_id.strip()))):
            raise InvalidInput('explicit conversation and optional message required')
        with self.repository.transaction() as tx:
            # Both reads must follow the same scope lock as receive. READ COMMITTED
            # without this lock can combine an absent receipt with a newer head.
            tx.lock_scope()
            stored = tx.find(message_id) if message_id is not None else None
            if stored is not None and stored.receipt.conversation_id != conversation_id:
                stored = None
            head = tx.active_head(conversation_id)
            reference=None
            if travel and stored is not None:
                from .travel_reference import read_reference
                reference=read_reference(tx,stored)
                if not edit and reference.message_version=='MESSAGE-send.4':
                    raise Unavailable('send.4 requires its read version')
                if not formal and reference.message_version=='MESSAGE-send.3':
                    raise Unavailable('send.3 requires explicit versioned read')
        return TravelSendStatus(stored,head,reference) if travel else SendStatus(stored, head)

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

    def message_history(self, conversation_id, cursor=None, limit=20, *, formal=False):
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
                command = Command.parse_original(item.raw) if formal else Command.parse_stored(item.raw)
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
