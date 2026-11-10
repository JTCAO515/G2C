"""Read the authenticated user's Lio message originals in conversation order."""
from dataclasses import dataclass
import hashlib
import json

from .demo_dialogue import LIO_VERSION, admitted_dialogue, lio_conversation
from .domain import Command, InvalidInput, Unavailable
from .travel_reference import read_reference


PAGE_SIZE = 20


@dataclass(frozen=True)
class TimelineMessage:
    message_id: str
    run_id: str
    sequence: int
    text: str
    locale: str


@dataclass(frozen=True)
class TimelinePage:
    conversation_id: str | None
    generation: str | None
    messages: tuple[TimelineMessage, ...]
    next_before: str | None


def original(service, message_id):
    with service.repository.transaction() as tx:
        tx.lock_scope()
        row = tx.cur.execute(
            'SELECT conversation_id,generation FROM cj_message_receipt WHERE scope=%s '
            'AND message_id=%s AND demo_dialogue_protocol=%s',
            (tx.scope, message_id, LIO_VERSION)).fetchone()
        if row is None:
            return None
        tx.chat(*row)
        stored = tx.find(message_id)
        read_reference(tx, stored)
        return stored


def read(service, conversation_id, before, *, multiple=False):
    with service.repository.transaction() as tx:
        conversation = lio_conversation(tx.scope)
        if conversation_id is not None and conversation_id != conversation:
            if not multiple:
                raise InvalidInput('invalid Lio conversation identifier')
            conversation = conversation_id
            head = tx.active_head(conversation)
            if head is None or not admitted_dialogue(tx, conversation, head.generation, lio=True):
                raise InvalidInput('invalid Lio conversation identifier')
        else:
            head = tx.active_head(conversation)
        if head is None:
            if before is not None:
                raise InvalidInput('invalid timeline cursor')
            return TimelinePage(None, None, (), None)
        params = (tx.scope, conversation, head.generation, LIO_VERSION)
        sequence = None
        if before is not None:
            cursor = tx.cur.execute(
                'SELECT sequence FROM cj_message_receipt WHERE scope=%s AND conversation_id=%s '
                'AND generation=%s AND demo_dialogue_protocol=%s AND message_id=%s',
                (*params, before)).fetchone()
            if cursor is None:
                raise InvalidInput('invalid timeline cursor')
            sequence = cursor[0]
        rows = tx.cur.execute(
            'SELECT message_id,run_id,sequence,raw_input,input_sha256,demo_dialogue_locale FROM cj_message_receipt '
            'WHERE scope=%s AND conversation_id=%s AND generation=%s AND demo_dialogue_protocol=%s '
            'AND (%s::bigint IS NULL OR sequence<%s) ORDER BY sequence DESC LIMIT %s',
            (*params, sequence, sequence, PAGE_SIZE + 1)).fetchall()
        messages = []
        for mid, run_id, position, raw_input, digest, locale in reversed(rows[:PAGE_SIZE]):
            raw = bytes(raw_input)
            try:
                command = Command.parse_original(raw)
            except (ValueError, UnicodeError, KeyError) as exc:
                raise Unavailable('invalid original dialogue message') from exc
            if ((command.message_id, command.conversation_id) != (mid, conversation)
                    or hashlib.sha256(raw).hexdigest() != digest):
                raise Unavailable('original dialogue binding changed')
            messages.append(TimelineMessage(mid, run_id, position, json.loads(command.raw)['text'], locale))
        return TimelinePage(conversation, head.generation, tuple(messages),
                            messages[0].message_id if len(rows) > PAGE_SIZE else None)
