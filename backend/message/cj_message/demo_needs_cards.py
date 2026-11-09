"""Append-only dialogue needs cards and exact explicit action recovery."""
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import re

from cj_needs.domain import Command as NeedsCommand, InvalidInput as NeedsInvalid, decode, validate_fields
from cj_needs.runtime import apply_dialogue_confirmation

from .demo_dialogue import CHAT_PATTERN, PLANNING_VERSION, DialogueMessage, _identity, _json, enqueue_dialogue, message_id
from .domain import InputConflict, InvalidInput, SequenceConflict, Unavailable
from .needs_binding import needs_scope_for


ACTION_VERSION = 'DEMO-dialogue-action.1'
RECEIPT_VERSION = 'DEMO-dialogue-action-receipt.1'
CARD = re.compile(r'needs-[0-9a-f]{32}')
_COLUMNS = ('origin_message_id,origin_run_id,card_id,version,fields,city,action_id,input_sha256,'
            'operation,result_message_id')


@dataclass(frozen=True)
class Card:
    origin_message_id: str
    origin_run_id: str
    id: str
    version: int
    fields: dict
    city: str | None
    action_id: str | None = None
    input_sha256: str | None = None
    operation: str | None = None
    result_message_id: str | None = None

    @classmethod
    def read(cls, row):
        values = list(row)
        values[4] = decode(bytes(values[4]))
        validate_fields(values[4], complete=True)
        return cls(*values)

    def project(self):
        def observed(value):
            return value.get('value') if value.get('state') == 'known' else None

        def at(event):
            day = observed(event['date'])
            time = observed(event['time'])
            return day+'T'+time if day is not None and time is not None else None

        start = observed(self.fields.get('arrival', {}).get('date', {}))
        end = observed(self.fields.get('departure', {}).get('date', {}))
        return dict(card_id=self.id, version=self.version,
            status='confirmed' if self.operation=='confirm_needs' else 'pending',
            dates=None if start is None and end is None else dict(start=start, end=end),
            city=self.city, party_size=observed(self.fields.get('party_size', {})),
            pace=observed(self.fields.get('pace', {})),
            fixed_items=[dict(item_id=item['item_id'], label=item['description'],
                              starts_at=at(item['start']), ends_at=at(item['end']),
                              time_zone=observed(item['start']['timezone']))
                         for item in self.fields.get('fixed_items', [])])


@dataclass(frozen=True)
class Action:
    id: str
    conversation: str
    card: str
    expected_version: int
    operation: str
    digest: str
    changes: dict | None = None

    @classmethod
    def parse(cls, raw):
        try:
            value = decode(raw)
            fields = {'version','action_id','conversation_id','card_id','expected_version','operation'}
            if type(value) is not dict or value.get('version') != ACTION_VERSION:
                raise InvalidInput('invalid dialogue action version')
            operation = value.get('operation')
            if operation == 'correct_needs':
                fields.add('changes')
            elif operation not in ('confirm_needs','accept_trip'):
                raise InvalidInput('unsupported dialogue action')
            if set(value) != fields:
                raise InvalidInput('invalid dialogue action fields')
            conversation, card, version = value['conversation_id'], value['card_id'], value['expected_version']
            pattern=CARD if operation!='accept_trip' else re.compile(r'p-[0-9a-f-]{36}')
            if (type(conversation) is not str or not CHAT_PATTERN.fullmatch(conversation)
                    or type(card) is not str or not pattern.fullmatch(card)
                    or type(version) is not int or not 1 <= version < 64
                    or operation=='accept_trip' and version!=1):
                raise InvalidInput('invalid dialogue action identity')
            changes = value.get('changes')
            if operation == 'correct_needs':
                validate_fields(changes)
            return cls(message_id(value['action_id']), conversation, card, version, operation,
                       sha256(raw).hexdigest(), changes)
        except (NeedsInvalid, UnicodeError) as exc:
            raise InvalidInput('invalid dialogue action') from exc


def _insert(cur, scope, card):
    cur.execute('INSERT INTO cj_demo_needs_card(scope,'+_COLUMNS+') VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        (scope,card.origin_message_id,card.origin_run_id,card.id,card.version,_json(card.fields),card.city,
         card.action_id,card.input_sha256,card.operation,card.result_message_id))


def publish(cur, binding, fields, city):
    card = Card(binding.message_id, binding.run_id, 'needs-'+_identity(binding.scope,binding.run_id), 1, fields, city)
    _insert(cur, binding.scope, card)


def read_initial(tx, mid, run):
    row = tx.cur.execute('SELECT '+_COLUMNS+' FROM cj_demo_needs_card '
                         'WHERE scope=%s AND origin_message_id=%s AND origin_run_id=%s AND version=1',
                         (tx.scope,mid,run)).fetchone()
    return Card.read(row).project() if row is not None else None


def _lookup(tx, aid):
    row = tx.cur.execute('SELECT '+_COLUMNS+' FROM cj_demo_needs_card WHERE scope=%s AND action_id=%s',
                         (tx.scope,aid)).fetchone()
    return Card.read(row) if row is not None else None


def _receipt(tx, card):
    origin = tx.find(card.origin_message_id)
    tx.chat(origin.receipt.conversation_id,origin.receipt.generation)
    queued = tx.find(card.result_message_id).receipt if card.result_message_id is not None else None
    return dict(action_id=card.action_id,conversation_id=origin.receipt.conversation_id,card_id=card.id,
                version=card.version,operation=card.operation,input_sha256=card.input_sha256,
                message_id=queued.message_id if queued is not None else None,
                run_id=queued.run_id if queued is not None else None,card=card.project())


def _source(tx, card, conversation, chat):
    origin = tx.find(card.origin_message_id)
    if (origin is None or (origin.receipt.run_id,origin.receipt.conversation_id,origin.receipt.generation)
            != (card.origin_run_id,conversation,chat.generation)):
        raise Unavailable('original needs card unavailable')
    terminal = tx.cur.execute("SELECT status FROM cj_run_record r WHERE r.scope=%s AND r.run_id=%s "
        "AND EXISTS (SELECT 1 FROM cj_run_event e WHERE (e.scope,e.run_id)=(r.scope,r.run_id) "
        "AND e.kind='effect_committed' AND e.value='demo_needs_card')",
        (tx.scope,card.origin_run_id)).fetchone()
    if terminal != ('completed',):
        raise SequenceConflict('needs card publication is not complete')
    return origin


def _confirm(service, tx, card, conversation, chat, action, command=None):
    origin = _source(tx,card,conversation,chat)
    if not card.fields:
        raise SequenceConflict('confirming a needs card requires explicit details')
    needs_id = card.id
    needs = apply_dialogue_confirmation(tx.cur,needs_scope_for(tx.scope),NeedsCommand(_json(dict(
        action_id='demo-'+_identity(tx.scope,action.id),needs_id=needs_id,expected_version=0,
        source=dict(kind='manual',text='Explicit dialogue confirmation '+card.id),changes=card.fields))))
    text = json.loads(origin.raw)['text']
    if command is None:
        locale = tx.cur.execute('SELECT demo_dialogue_locale FROM cj_message_receipt WHERE scope=%s AND message_id=%s',
                                (tx.scope,card.origin_message_id)).fetchone()[0]
        command = DialogueMessage('demo-plan-'+_identity(tx.scope,action.id),text,locale,conversation,False,action.digest,PLANNING_VERSION)
    else:
        command = replace(command,text=text)
    queued = enqueue_dialogue(service,tx,command,conversation,chat,
                              needs=dict(id=needs.needs_id,expected_version=needs.version))
    return replace(card,version=card.version+1,action_id=action.id,input_sha256=action.digest,
                   operation=action.operation,result_message_id=queued.message_id), queued


def act(service, action):
    from .demo_trip_adoption import find as find_adoption
    with service.repository.transaction() as tx:
        tx.lock_scope()
        old = _lookup(tx,action.id)
        if old is not None:
            if old.input_sha256 != action.digest:
                raise InputConflict()
            return _receipt(tx,old)
        if find_adoption(tx,action.id) is not None:
            raise InputConflict()
        chat = tx.chat(action.conversation)
        row = tx.cur.execute('SELECT '+_COLUMNS+' FROM cj_demo_needs_card '
                             'WHERE scope=%s AND card_id=%s ORDER BY version DESC LIMIT 1',
                             (tx.scope,action.card)).fetchone()
        if row is None:
            raise Unavailable('needs card unavailable')
        card = Card.read(row)
        if card.version != action.expected_version or card.operation=='confirm_needs':
            raise SequenceConflict('needs card changed')
        if action.operation=='confirm_needs':
            updated,_ = _confirm(service,tx,card,action.conversation,chat,action)
        else:
            _source(tx,card,action.conversation,chat)
            fields = card.fields | action.changes
            try:
                validate_fields(fields,complete=True)
                if len(_json(fields))>131072:
                    raise NeedsInvalid('corrected card exceeds bound')
            except NeedsInvalid as exc:
                raise InvalidInput('invalid corrected needs') from exc
            city = card.city
            if 'arrival' in action.changes:
                place = action.changes['arrival']['place']
                city = place.get('value') if place['state']=='known' else None
            if city is not None and len(city.encode('utf-8'))>256:
                raise InvalidInput('city exceeds bound')
            updated = replace(card,version=card.version+1,fields=fields,city=city,action_id=action.id,
                              input_sha256=action.digest,operation=action.operation)
        _insert(tx.cur,tx.scope,updated)
        return _receipt(tx,updated)


def query(service, aid):
    with service.repository.transaction() as tx:
        tx.lock_scope()
        card = _lookup(tx,aid)
        return _receipt(tx,card) if card is not None else None


def confirm_text(service, tx, command, conversation, chat):
    rows = tx.cur.execute('SELECT '+_COLUMNS+' FROM (SELECT DISTINCT ON (c.card_id) '
        'c.* FROM cj_demo_needs_card c JOIN cj_message_receipt m ON (m.scope,m.message_id)=(c.scope,c.origin_message_id) '
        'JOIN cj_run_record r ON (r.scope,r.run_id)=(c.scope,c.origin_run_id) '
        "WHERE c.scope=%s AND m.conversation_id=%s AND m.generation=%s AND r.status='completed' "
        "ORDER BY c.card_id,c.version DESC) current WHERE operation IS DISTINCT FROM 'confirm_needs' LIMIT 2",
        (tx.scope,conversation,chat.generation)).fetchall()
    if not rows:
        return None
    if len(rows)!=1:
        raise SequenceConflict('choose the needs card to confirm')
    card = Card.read(rows[0])
    if card.version>=64:
        raise SequenceConflict('needs card has no remaining revisions')
    action = Action('speech-'+_identity(tx.scope,command.id),conversation,card.id,card.version,
                    'confirm_needs',command.input_sha256)
    from .demo_trip_adoption import find as find_adoption
    if find_adoption(tx,action.id) is not None:
        raise InputConflict()
    updated, queued = _confirm(service,tx,card,conversation,chat,action,command)
    _insert(tx.cur,tx.scope,updated)
    return queued
