"""TRAVEL-CONTEXT@1: local-only owner identity, exact original action ledger.

The repository is supplied by canonical MESSAGE Boundary. No caller scope,
credentials, Trip, conversation selection or memory facts are accepted here.
"""
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime
import json
import re
import uuid

from .domain import InputConflict, InvalidInput, SequenceConflict, Unavailable

ABI = 'MESSAGE-TRAVEL-CONSUMER@1'
PROFILE = 'message-travel.1'


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise InvalidInput('duplicate field')
            result[key] = value
        return result
    if type(raw) is not bytes or len(raw) > 65536:
        raise InvalidInput('bounded immutable UTF8 required')
    try:
        return json.loads(raw.decode('utf8'), object_pairs_hook=pairs)
    except (ValueError, UnicodeError) as exc:
        raise InvalidInput('invalid JSON') from exc


@dataclass(frozen=True)
class Selection:
    id: str
    expected_version: int

    @classmethod
    def parse(cls, value):
        if (type(value) is not dict or set(value) != {'id', 'expected_version'}
                or type(value['id']) is not str
                or re.fullmatch('[0-9a-f]{32}', value['id']) is None
                or type(value['expected_version']) is not int
                or not 1 <= value['expected_version'] <= 9223372036854775807):
            raise InvalidInput('invalid travel context reference')
        return cls(value['id'], value['expected_version'])


@dataclass(frozen=True)
class Action:
    action_id: str
    operation: str
    travel_context: Selection | None
    raw: bytes

    @classmethod
    def parse(cls, raw):
        obj = decode(raw)
        if (type(obj) is not dict or set(obj) != {'version', 'action_id', 'operation', 'travel_context'}
                or obj['version'] != 'TRAVEL-context-action.1'
                or type(obj['action_id']) is not str
                or re.fullmatch('[!-~]{1,96}', obj['action_id']) is None
                or obj['operation'] not in ('create', 'advance', 'deactivate')):
            raise InvalidInput('invalid travel action')
        if obj['operation'] == 'create':
            if obj['travel_context'] is not None:
                raise InvalidInput('create requires null context')
            selection = None
        else:
            selection = Selection.parse(obj['travel_context'])
        return cls(obj['action_id'], obj['operation'], selection, raw)


@dataclass(frozen=True)
class Context:
    id: str
    version: int
    active: bool
    created_at: datetime | None = None


@dataclass(frozen=True)
class ActionReceipt:
    action_id: str
    operation: str
    context: Context
    raw: bytes

    @classmethod
    def build(cls, action, context):
        raw = json.dumps(dict(version='TRAVEL-context-receipt.1', action_id=action.action_id,
            operation=action.operation, travel_context=dict(id=context.id,
            version=context.version, active=context.active)), separators=(',', ':')).encode()
        return cls(action.action_id, action.operation, context, raw)


class Service:
    """Internal domain service; use MESSAGE Boundary for public admission."""
    def __init__(self, repository):
        self.repository = repository

    @contextmanager
    def _transaction(self):
        with self.repository.transaction() as tx:
            tx.cur.execute("SELECT set_config('cj.message_context_abi',%s,true)", (ABI,))
            tx.lock_scope()
            yield tx

    def apply(self, raw):
        action = Action.parse(raw)
        with self._transaction() as tx:
            old = self._original(tx, action.action_id)
            if old is not None:
                if old[0] != raw:
                    raise InputConflict()
                return old[1]
            if action.operation == 'create':
                context = Context(uuid.uuid4().hex, 1, True)
            else:
                ref = action.travel_context
                tx.cur.execute('SELECT version,active FROM cj_travel_context '
                    'WHERE scope=%s AND context_id=%s FOR UPDATE', (tx.scope, ref.id))
                row = tx.cur.fetchone()
                if row is None:
                    raise Unavailable('travel context unavailable')
                if not row[1] or row[0] != ref.expected_version or row[0] == 9223372036854775807:
                    raise SequenceConflict('travel context version conflict')
                context = Context(ref.id, row[0] + 1, action.operation == 'advance')
            receipt = ActionReceipt.build(action, context)
            tx.cur.execute('INSERT INTO cj_travel_context_action '
                '(scope,action_id,operation,context_id,expected_version,result_version,result_active,original_input,original_receipt) '
                'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (tx.scope, action.action_id, action.operation, context.id,
                 None if action.travel_context is None else action.travel_context.expected_version,
                 context.version, context.active, raw, receipt.raw))
            if action.operation == 'create':
                tx.cur.execute('INSERT INTO cj_travel_context(scope,context_id,version,active,head_action_id) '
                    'VALUES(%s,%s,%s,%s,%s)',
                    (tx.scope, context.id, context.version, context.active, action.action_id))
            else:
                tx.cur.execute('UPDATE cj_travel_context SET version=%s,active=%s,head_action_id=%s '
                    'WHERE scope=%s AND context_id=%s',
                    (context.version, context.active, action.action_id, tx.scope, context.id))
        return receipt.raw

    def _original(self, tx, action_id):
        tx.cur.execute('SELECT original_input,original_receipt,operation,context_id,expected_version,result_version,result_active FROM cj_travel_context_action '
                       'WHERE scope=%s AND action_id=%s', (tx.scope, action_id))
        row = tx.cur.fetchone()
        if row is None:
            return None
        raw, receipt = bytes(row[0]), bytes(row[1])
        try:
            action = Action.parse(raw)
            obj = decode(receipt)
            value = obj['travel_context']
            ref = Selection.parse({'id': value['id'], 'expected_version': value['version']})
            if (set(obj) != {'version', 'action_id', 'operation', 'travel_context'}
                    or set(value) != {'id', 'version', 'active'} or type(value['active']) is not bool
                    or obj['version'] != 'TRAVEL-context-receipt.1'
                    or obj['action_id'] != action_id or action.action_id != action_id
                    or obj['operation'] != action.operation):
                raise InvalidInput('inconsistent original travel receipt')
            expected = None if action.travel_context is None else action.travel_context.expected_version
            if tuple(row[2:]) != (action.operation, ref.id, expected, ref.expected_version, value['active']):
                raise InvalidInput('stored travel action metadata mismatch')
            # The DB action/state chain protects the result; validate stored bytes at this boundary.
            if action.operation == 'create' and (ref.expected_version != 1 or not value['active']):
                raise InvalidInput('invalid original create receipt')
            if action.travel_context is not None and (ref.id != action.travel_context.id
                    or ref.expected_version != action.travel_context.expected_version + 1
                    or value['active'] != (action.operation == 'advance')):
                raise InvalidInput('invalid original transition receipt')
        except (InvalidInput, KeyError, TypeError) as exc:
            raise Unavailable('original travel receipt unavailable') from exc
        return raw, receipt

    def query_action(self, action_id):
        if type(action_id) is not str or re.fullmatch('[!-~]{1,96}', action_id) is None:
            raise InvalidInput('invalid action ID')
        with self._transaction() as tx:
            row = self._original(tx, action_id)
        return None if row is None else row[1]

    def get(self, context_id):
        Selection.parse({'id': context_id, 'expected_version': 1})
        with self._transaction() as tx:
            tx.cur.execute('SELECT version,active,created_at FROM cj_travel_context WHERE scope=%s AND context_id=%s',
                           (tx.scope, context_id))
            row = tx.cur.fetchone()
            if row is None:
                raise Unavailable('travel context unavailable')
            if (type(row[0]) is not int or row[0] < 1 or type(row[1]) is not bool
                    or not isinstance(row[2], datetime) or row[2].tzinfo is None):
                raise Unavailable('invalid stored travel context')
            result = Context(context_id, *row)
        return result
