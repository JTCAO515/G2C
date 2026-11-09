"""Zero-setup admission using the original MESSAGE outbox and Travel authority."""
from dataclasses import dataclass
import hashlib
import json
import re
import uuid

from .domain import Command, InputConflict, InvalidInput, Unavailable, unique_fields
from .travel import ABI, Action, Service as TravelService


MESSAGE_VERSION = 'DEMO-dialogue-message.1'
RECEIPT_VERSION = 'DEMO-dialogue-receipt.1'
CHAT_PATTERN = re.compile(r'demo-dialogue-[0-9a-f]{32}')


def message_id(value):
    if (type(value) is not str or not value.strip() or '\x00' in value
            or len(value.encode('utf-8')) > 256):
        raise InvalidInput('invalid dialogue message identifier')
    return value


@dataclass(frozen=True)
class DialogueMessage:
    id: str
    text: str
    locale: str
    conversation_id: str | None
    new_conversation: bool
    input_sha256: str

    @classmethod
    def parse(cls, raw):
        try:
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_fields)
            required = {'version', 'message_id', 'text', 'locale'}
            if (type(value) is not dict or not required <= value.keys()
                    or value.keys() - required - {'conversation_id', 'new_conversation'}
                    or value['version'] != MESSAGE_VERSION or value['locale'] not in ('zh', 'en')
                    or ('new_conversation' in value and (value['new_conversation'] is not True
                                                       or 'conversation_id' in value))):
                raise InvalidInput('invalid dialogue message fields')
            text = value['text']
            if type(text) is not str or not text.strip() or '\x00' in text or len(text.encode('utf-8')) > 12000:
                raise InvalidInput('invalid dialogue text')
            conversation = value.get('conversation_id')
            if 'conversation_id' in value and (type(conversation) is not str or not CHAT_PATTERN.fullmatch(conversation)):
                raise InvalidInput('invalid dialogue conversation identifier')
            return cls(message_id(value['message_id']), text, value['locale'], conversation,
                       value.get('new_conversation', False), hashlib.sha256(raw).hexdigest())
        except (UnicodeError, ValueError) as exc:
            raise InvalidInput('invalid dialogue message') from exc


@dataclass(frozen=True)
class DialogueReceipt:
    message_id: str
    conversation_id: str
    run_id: str
    input_sha256: str


def _identity(scope, purpose):
    return hashlib.sha256(f'{purpose}\x00{scope}'.encode()).hexdigest()[:32]


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _original_digest(tx, mid):
    row = tx.cur.execute('SELECT demo_dialogue_input_sha256 FROM cj_message_receipt '
                         'WHERE scope=%s AND message_id=%s', (tx.scope, mid)).fetchone()
    return row[0] if row is not None else None


def _receipt(stored, digest):
    receipt = stored.receipt
    return DialogueReceipt(receipt.message_id, receipt.conversation_id, receipt.run_id, digest)


def _travel(tx, repository):
    context_id = _identity(tx.scope, 'demo-dialogue-travel.1')
    current = tx.cur.execute('SELECT version,active FROM cj_travel_context '
                             'WHERE scope=%s AND context_id=%s FOR SHARE',
                             (tx.scope, context_id)).fetchone()
    if current is None:
        action = Action.parse(_json(dict(version='TRAVEL-context-action.1', action_id=uuid.uuid4().hex,
                                        operation='create', travel_context=None)))
        TravelService(repository).apply_locked(tx, action, creation_id=context_id)
        version = 1
    else:
        version, active = current
        if not active:
            raise Unavailable('default dialogue Travel context retired')
    return dict(id=context_id, expected_version=version)


def receive(service, raw):
    command = DialogueMessage.parse(raw)
    with service.repository.transaction() as tx:
        tx.lock_scope()
        stored = tx.find(command.id)
        if stored is not None:
            digest = _original_digest(tx, command.id)
            if digest != command.input_sha256:
                raise InputConflict()
            tx.chat(stored.receipt.conversation_id, stored.receipt.generation)
            return _receipt(stored, digest)

        conversation = command.conversation_id
        if conversation is None:
            purpose = 'new:' + command.id if command.new_conversation else 'default:' + command.locale
            conversation = 'demo-dialogue-' + _identity(tx.scope, purpose)
        chat = tx.active_head(conversation)
        if chat is None:
            if command.conversation_id is not None:
                raise Unavailable('dialogue conversation unavailable')
            chat = tx.open_chat(conversation, uuid.uuid4().hex)
            if chat is None:
                raise Unavailable('dialogue conversation unavailable')
        elif command.conversation_id is not None or chat.last_sequence:
            original = tx.cur.execute('SELECT 1 FROM cj_message_receipt WHERE scope=%s AND conversation_id=%s '
                                      'AND generation=%s AND demo_dialogue_input_sha256 IS NOT NULL LIMIT 1',
                                      (tx.scope, conversation, chat.generation)).fetchone()
            if original is None:
                raise Unavailable('dialogue conversation unavailable')

        tx.cur.execute("SELECT set_config('cj.message_context_abi',%s,true)", (ABI,))
        selection = _travel(tx, service.repository)
        inner = Command.parse_v2(_json(dict(version='MESSAGE-send.2', conversation_id=conversation,
            message_id=command.id, text=command.text, trip_id=None, creation_intent='none',
            expected_generation=chat.generation, expected_sequence=chat.last_sequence,
            travel_context=selection, needs_reference=None)))
        receipt = service.accept_new(tx, inner, travel=True, dialogue=command)
        return DialogueReceipt(receipt.message_id, receipt.conversation_id, receipt.run_id, command.input_sha256)


def query(service, mid):
    with service.repository.transaction() as tx:
        tx.lock_scope()
        digest = _original_digest(tx, mid)
        if digest is None:
            return None
        stored = tx.find(mid)
        tx.chat(stored.receipt.conversation_id, stored.receipt.generation)
        return _receipt(stored, digest)
