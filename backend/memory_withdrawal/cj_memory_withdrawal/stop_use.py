"""MEMORY-STOP-USE@1: canonical scope-locked stop-use, no deletion or cleanup."""
from dataclasses import dataclass
import json

from cj_memory.domain import Command, Conflict, InvalidInput, Unavailable
from .domain import Action, SourceReference, check_history


@dataclass(frozen=True, repr=False)
class StopUse(Action):
    @classmethod
    def parse(cls, raw):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise InvalidInput('duplicate field')
                result[key] = value
            return result
        if type(raw) is not bytes or len(raw) > 32768:
            raise InvalidInput('original UTF8 bytes required')
        try:
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        except (ValueError, UnicodeError):
            raise InvalidInput('invalid JSON') from None
        if type(value) is not dict or value.pop('version', None) != 'MEMORY-STOP-USE@1':
            raise InvalidInput('explicit stop-use version required')
        # Reuse the fixed legacy action grammar, retaining this version's bytes.
        action = Action.parse(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())
        return cls(action.action_id, action.operation, action.item_id, action.expected_version,
                   action.source_id, action.expected_source_version, raw)


def source_history(tx, item):
    """Server enumerates the complete connected edit chain under the scope lock."""
    tx.cur.execute('''SELECT action_id FROM cj_memory_management_action
        WHERE scope=%s AND item_id=%s AND operation='edit' ORDER BY version''',
                   (tx.scope,item.command.item_id))
    actions = tx.cur.fetchall()
    if len(actions) >= 1000:
        raise Unavailable('source history exceeds bound')
    sources = {item.command.source_id}
    edges = []
    for (action_id,) in actions:
        tx.action(action_id)  # Existing DB-boundary original bytes/lineage check.
        tx.cur.execute('''SELECT previous_source_id,new_source_id
            FROM cj_memory_management_action WHERE scope=%s AND action_id=%s''',
                       (tx.scope,action_id))
        previous,current = tx.cur.fetchone()
        edges.append((previous,current)); sources.update((previous,current))
    # Each edit appends exactly one source. Refuse disconnected, forked or cyclic
    # history instead of guessing which earlier source belongs to the item.
    if edges:
        chain = [edges[0][0]]
        for previous,current in edges:
            if previous != chain[-1] or current in chain:
                raise Unavailable('source chain is incomplete or ambiguous')
            chain.append(current)
        if chain[-1] != item.command.source_id or set(chain) != sources:
            raise Unavailable('current source differs from complete history')
    history=[]
    for source_id in sorted(sources):
        tx.cur.execute('''SELECT version,approved_input FROM cj_memory_source
            WHERE scope=%s AND source_id=%s FOR UPDATE''',(tx.scope,source_id))
        row=tx.cur.fetchone()
        if row is None:
            raise Unavailable('source history unavailable')
        command=Command.parse(bytes(row[1]))
        if (command.item_id != item.command.item_id or command.source_id != source_id
                or command.source_version != row[0]):
            raise Unavailable('source history projection mismatch')
        if source_id == item.command.source_id and bytes(row[1]) != item.command.raw:
            raise Unavailable('current source bytes differ from item')
        tx.cur.execute('''SELECT item_id FROM cj_memory_item WHERE scope=%s AND source_id=%s
            UNION SELECT item_id FROM cj_memory_management_action
            WHERE scope=%s AND (previous_source_id=%s OR new_source_id=%s)''',
                       (tx.scope,source_id,tx.scope,source_id,source_id))
        references=tuple(r[0] for r in tx.cur.fetchall())
        if references != (item.command.item_id,):
            raise Unavailable('shared or unresolved source history')
        history.append(SourceReference(source_id,row[0],references))
    return tuple(history)


def withdraw(tx, action):
    item=tx.detail(action.item_id)
    if item is None:
        raise Unavailable('memory unavailable')
    tx.cur.execute('''SELECT source_id,source_version FROM cj_memory_item
        WHERE scope=%s AND item_id=%s FOR UPDATE''',(tx.scope,action.item_id))
    physical=tx.cur.fetchone()
    if (item.command.item_id != action.item_id or physical !=
            (item.command.source_id,item.command.source_version)):
        raise Unavailable('item source projection mismatch')
    if item.version != action.expected_version:
        raise Conflict('item version changed')
    if (item.command.source_id != action.source_id
            or item.command.source_version != action.expected_source_version):
        raise Conflict('source version changed')
    if item.status == 'withdrawn':
        raise Conflict('already stopped; reconcile original action')
    history=source_history(tx,item)
    check_history(action,history)
    for source in history:
        tx.cur.execute('UPDATE cj_memory_source SET active=false WHERE scope=%s AND source_id=%s',
                       (tx.scope,source.source_id))
    tx.cur.execute('''UPDATE cj_memory_item SET status='withdrawn',version=version+1
        WHERE scope=%s AND item_id=%s AND version=%s AND source_id=%s
        AND source_version=%s RETURNING version''',
                   (tx.scope,action.item_id,action.expected_version,action.source_id,action.expected_source_version))
    updated=tx.cur.fetchone()
    if updated is None:
        raise Conflict('item or source version changed')
    version=updated[0]
    tx.cur.execute('UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope=%s RETURNING epoch',(tx.scope,))
    epoch=tx.cur.fetchone()[0]
    encoded=json.dumps([dict(source_id=s.source_id,source_version=s.source_version,item_ids=s.item_ids)
                        for s in history],separators=(',',':'))
    tx.cur.execute('''INSERT INTO cj_memory_management_action
        (scope,action_id,operation,original_input,item_id,version,status,withdrawal_history,withdrawal_epoch)
        VALUES (%s,%s,'withdraw',%s,%s,%s,'withdrawn',%s::jsonb,%s)''',
                   (tx.scope,action.action_id,action.raw,action.item_id,version,encoded,epoch))
    return tx.action(action.action_id)[1]


def validate_stored(tx, action, receipt):
    tx.cur.execute('''SELECT withdrawal_history,withdrawal_epoch FROM cj_memory_management_action
        WHERE scope=%s AND action_id=%s''',(tx.scope,action.action_id))
    row=tx.cur.fetchone()
    if row is None or type(row[0]) is not list or type(row[1]) is not int or row[1]<2:
        raise Unavailable('stop-use receipt history unavailable')
    try:
        history=tuple(SourceReference(x['source_id'],x['source_version'],tuple(x['item_ids'])) for x in row[0])
        check_history(action,history)
    except (KeyError,TypeError,ValueError):
        raise Unavailable('stop-use history invalid') from None
    if receipt.status != 'withdrawn':
        raise Unavailable('stop-use receipt projection mismatch')
    return receipt
