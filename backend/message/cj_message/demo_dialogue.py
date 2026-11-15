"""Zero-setup admission using the original MESSAGE outbox and Travel authority."""
from cj_strict_json import compact
from dataclasses import dataclass
import hashlib
import json
import re
import uuid

from .domain import Command, CommitUnknown, InputConflict, InvalidInput, Unavailable, unique_fields
from .travel import ABI, Action, Service as TravelService


MESSAGE_VERSION = 'DEMO-dialogue-message.1'
LIO_VERSION = 'LIO-message.1'
LIO_VERSION_V2 = 'LIO-message.2'
LIO_VERSION_V3 = 'LIO-message.3'
LIO_VERSION_V4 = 'LIO-message.4'
RECEIPT_VERSION = 'DEMO-dialogue-receipt.1'
CHAT_PATTERN = re.compile(r'demo-dialogue-[0-9a-f]{32}')
LIO_CHAT_PATTERN = re.compile(r'lio-dialogue-[0-9a-f]{32}')


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
    protocol: str = MESSAGE_VERSION
    wire_input: bytes | None = None

    @classmethod
    def parse(cls, raw, *, version=MESSAGE_VERSION):
        try:
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_fields)
            required = {'version', 'message_id', 'text', 'locale'}
            optional = {'conversation_id'} if version == LIO_VERSION else {'conversation_id', 'new_conversation'}
            if (type(value) is not dict or not required <= value.keys()
                    or value.keys() - required - optional
                    or value['version'] != version or value['locale'] not in ('zh', 'en')
                    or ('new_conversation' in value and (value['new_conversation'] is not True
                                                       or 'conversation_id' in value))):
                raise InvalidInput('invalid dialogue message fields')
            text = value['text']
            if type(text) is not str or not text.strip() or '\x00' in text or len(text.encode('utf-8')) > 12000:
                raise InvalidInput('invalid dialogue text')
            conversation = value.get('conversation_id')
            pattern = CHAT_PATTERN if version == MESSAGE_VERSION else LIO_CHAT_PATTERN
            if 'conversation_id' in value and (type(conversation) is not str or not pattern.fullmatch(conversation)):
                raise InvalidInput('invalid dialogue conversation identifier')
            return cls(message_id(value['message_id']), text, value['locale'], conversation,
                       value.get('new_conversation', False), hashlib.sha256(raw).hexdigest(), value['version'],
                       raw if version in (LIO_VERSION_V3,LIO_VERSION_V4) else None)
        except (UnicodeError, ValueError) as exc:
            raise InvalidInput('invalid dialogue message') from exc


@dataclass(frozen=True)
class DialogueReceipt:
    message_id: str
    conversation_id: str
    run_id: str
    input_sha256: str
    protocol: str = LIO_VERSION
    requires_new_lio: bool = False
    requires_exploration: bool = False


def _identity(scope, purpose):
    return hashlib.sha256(f'{purpose}\x00{scope}'.encode()).hexdigest()[:32]


def lio_conversation(scope):
    return 'lio-dialogue-' + _identity(scope, 'lio-default')


def _json(value):
    return compact(value, allow_nan=True)


def _original_digest(tx, mid):
    row = tx.cur.execute('SELECT demo_dialogue_input_sha256 FROM cj_message_receipt '
                         'WHERE scope=%s AND message_id=%s', (tx.scope, mid)).fetchone()
    return row[0] if row is not None else None


def _receipt(stored, digest, protocol=LIO_VERSION, *, requires_new_lio=False,requires_exploration=False):
    receipt = stored.receipt
    return DialogueReceipt(receipt.message_id, receipt.conversation_id, receipt.run_id, digest, protocol, requires_new_lio,requires_exploration)


def has_new_lio_wire(tx, conversation, generation):
    return tx.cur.execute('SELECT 1 FROM cj_message_receipt WHERE scope=%s '
        'AND conversation_id=%s AND generation=%s AND lio_wire_protocol IS NOT NULL LIMIT 1',
        (tx.scope, conversation, generation)).fetchone() is not None


def has_exploration_wire(tx,conversation,generation):
    return tx.cur.execute('SELECT 1 FROM cj_message_receipt WHERE scope=%s '
        'AND conversation_id=%s AND generation=%s AND lio_wire_protocol=%s LIMIT 1',
        (tx.scope,conversation,generation,LIO_VERSION_V4)).fetchone() is not None


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
    return _receive(service, DialogueMessage.parse(raw))


def receive_lio(service, raw, *, prepare_scope, version=LIO_VERSION):
    command = DialogueMessage.parse(raw, version=version)
    try:
        return _receive(service, command, prepare_scope=prepare_scope)
    except CommitUnknown:
        original = query(service, command.id, lio=True)
        if original is None:
            raise
        if original.input_sha256 != command.input_sha256:
            raise InputConflict()
        return original


def _receive(service, command, *, prepare_scope=None):
    with service.repository.transaction() as tx:
        tx.lock_scope()
        if prepare_scope is not None:
            prepare_scope(tx.cur, tx.scope)
        stored = tx.find(command.id)
        if stored is not None:
            digest = _original_digest(tx, command.id)
            if digest != command.input_sha256:
                raise InputConflict()
            tx.chat(stored.receipt.conversation_id, stored.receipt.generation)
            return _receipt(stored, digest, command.protocol if command.protocol in (LIO_VERSION_V3,LIO_VERSION_V4) else LIO_VERSION)

        conversation = command.conversation_id
        if command.protocol == LIO_VERSION:
            default = lio_conversation(tx.scope)
            if conversation is not None and conversation != default:
                raise InvalidInput('invalid Lio conversation identifier')
            conversation = default
        elif command.protocol in (LIO_VERSION_V2, LIO_VERSION_V3, LIO_VERSION_V4) and conversation is None:
            conversation = ('lio-dialogue-' + _identity(tx.scope, 'lio-new:' + command.id)
                            if command.new_conversation else lio_conversation(tx.scope))
        elif conversation is None:
            purpose = 'new:' + command.id if command.new_conversation else 'default:' + command.locale
            conversation = 'demo-dialogue-' + _identity(tx.scope, purpose)
        chat = tx.active_head(conversation)
        if chat is None:
            if command.conversation_id is not None:
                if command.protocol in (LIO_VERSION_V2, LIO_VERSION_V3, LIO_VERSION_V4):
                    raise InvalidInput('invalid Lio conversation identifier')
                raise Unavailable('dialogue conversation unavailable')
            chat = tx.open_chat(conversation, uuid.uuid4().hex)
            if chat is None:
                raise Unavailable('dialogue conversation unavailable')
        elif command.conversation_id is not None or chat.last_sequence or (
                command.protocol in (LIO_VERSION_V2, LIO_VERSION_V3, LIO_VERSION_V4) and command.new_conversation):
            if not admitted_dialogue(tx, conversation, chat.generation, lio=command.protocol != MESSAGE_VERSION):
                if command.protocol in (LIO_VERSION_V2, LIO_VERSION_V3, LIO_VERSION_V4) and command.conversation_id is not None:
                    raise InvalidInput('invalid Lio conversation identifier')
                raise Unavailable('dialogue conversation unavailable')

        if command.protocol in (LIO_VERSION, LIO_VERSION_V2):
            if has_new_lio_wire(tx, conversation, chat.generation):
                raise InvalidInput('calendar conversation requires the new Lio capability')

        if command.protocol==LIO_VERSION_V3 and has_exploration_wire(tx,conversation,chat.generation):
            raise InvalidInput('exploration conversation requires the new Lio capability')

        tx.cur.execute("SELECT set_config('cj.message_context_abi',%s,true)", (ABI,))
        selection = _travel(tx, service.repository)
        inner = Command.parse_v2(_json(dict(version='MESSAGE-send.2', conversation_id=conversation,
            message_id=command.id, text=command.text, trip_id=None, creation_intent='none',
            expected_generation=chat.generation, expected_sequence=chat.last_sequence,
            travel_context=selection, needs_reference=None)))
        receipt = service.accept_new(tx, inner, travel=True, dialogue=command)
        return DialogueReceipt(receipt.message_id, receipt.conversation_id, receipt.run_id, command.input_sha256,
                               command.protocol if command.protocol in (LIO_VERSION_V3,LIO_VERSION_V4) else LIO_VERSION)


def admitted_dialogue(tx, conversation, generation, *, lio):
    query = ('SELECT 1 FROM cj_message_receipt WHERE scope=%s AND conversation_id=%s '
             'AND generation=%s AND demo_dialogue_input_sha256 IS NOT NULL')
    args = (tx.scope, conversation, generation)
    if lio:
        query += ' AND demo_dialogue_protocol=%s'
        args += (LIO_VERSION,)
    return tx.cur.execute(query + ' LIMIT 1', args).fetchone() is not None


def query(service, mid, *, lio=False):
    with service.repository.transaction() as tx:
        tx.lock_scope()
        digest = _original_digest(tx, mid)
        if digest is None:
            return None
        stored = tx.find(mid)
        if (LIO_CHAT_PATTERN.fullmatch(stored.receipt.conversation_id) is not None) != lio:
            return None
        tx.chat(stored.receipt.conversation_id, stored.receipt.generation)
        protocol=tx.cur.execute('SELECT lio_wire_protocol FROM cj_message_receipt '
            'WHERE scope=%s AND message_id=%s',(tx.scope,mid)).fetchone()[0]
        return _receipt(stored, digest, LIO_VERSION if protocol is None else protocol,
            requires_new_lio=lio and has_new_lio_wire(tx, stored.receipt.conversation_id, stored.receipt.generation),
            requires_exploration=lio and has_exploration_wire(tx,stored.receipt.conversation_id,stored.receipt.generation))
