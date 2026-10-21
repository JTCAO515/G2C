"""MESSAGE-draft.1: synthetic single-threaded model. NEVER a production store/API."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json


class Rejected(Exception):
    pass


class LostAck(Exception):
    pass


@dataclass(frozen=True)
class Authority:
    # Test oracle only: real AUTH must supply and revalidate these, never callers.
    principal: str
    revision: int = 1
    eligible: bool = True
    email_status: str = "unknown"
    identity_status: str = "valid"


def parse(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Rejected('invalid_input')
            result[key] = value
        return result
    if type(raw) is not bytes:
        raise Rejected('invalid_input')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
    except (ValueError, UnicodeError, AttributeError):
        raise Rejected('invalid_input') from None
    keys = {'version', 'conversation_id', 'message_id', 'text', 'trip_id', 'creation_intent'}
    if not isinstance(value, dict) or set(value) != keys:
        raise Rejected('invalid_input')
    if value['version'] != 'MESSAGE-draft.1':
        raise Rejected('unsupported_version')
    for key in ('conversation_id', 'message_id', 'text'):
        if not isinstance(value[key], str) or not value[key].strip():
            raise Rejected('invalid_input')
    if value['trip_id'] is not None and not isinstance(value['trip_id'], str):
        raise Rejected('invalid_input')
    if value['trip_id'] == '' or value['creation_intent'] not in ('none', 'consider_trip'):
        raise Rejected('invalid_input')
    return value


class Model:
    def __init__(self, image=None):
        # An image is a deepcopy checkpoint, NOT durable storage or database isolation.
        self.s = deepcopy(image) if image is not None else {
            'auth': {}, 'chats': {}, 'actions': {}, 'jobs': {}, 'runs': {},
            'ended': {}, 'summary_acks': {}, 'expired': set(), 'cursors': {}, 'clock': 0}

    def image(self):
        return deepcopy(self.s)

    def authorize(self, a):
        if (a.identity_status != 'valid' or a.email_status != 'verified'
                or a.eligible is not True or self.s['auth'].get(a.principal) != a.revision):
            raise Rejected('unavailable')

    def chat(self, a, cid):
        self.authorize(a)
        c = self.s['chats'].get(cid)
        if c is None or c['owner'] != a.principal:
            raise Rejected('unavailable')
        return c

    def create(self, a, cid):
        self.authorize(a)
        if cid in self.s['chats']:
            self.chat(a, cid)
            return cid
        self.s['clock'] += 1
        self.s['chats'][cid] = {'owner': a.principal, 'messages': [], 'draft': b'',
                                'epoch': 0, 'generation': self.s['clock']}
        return cid

    def draft(self, a, cid, raw=None):
        c = self.chat(a, cid)
        if raw is not None:
            if not isinstance(raw, bytes):
                raise Rejected('invalid_input')
            c['draft'] = raw
        return c['draft']

    def receive(self, a, raw, crash=None):
        self.authorize(a)
        p = parse(raw)
        c = self.chat(a, p['conversation_id'])
        key = (a.principal, 'receive', p['message_id'])
        if key in self.s['expired']:
            raise Rejected('recovery_expired')
        if key in self.s['actions']:
            old = self.s['actions'][key]
            if old['raw'] != raw:
                raise Rejected('input_conflict')
            return deepcopy(old['receipt'])
        if p['conversation_id'] in self.s['ended']:
            raise Rejected('conversation_ended')
        if p['trip_id'] is not None:
            # No invented Trip authority or fake Trip binding in this isolated draft.
            raise Rejected('trip_authority_required')
        if crash == 'before_commit':
            raise LostAck()
        run = 'fixture-run-' + str(len(self.s['actions']) + 1)
        receipt = {'version': 'MESSAGE-draft.1', 'message_id': p['message_id'],
                   'conversation_id': p['conversation_id'], 'run_id': run,
                   'sequence': len(c['messages']) + 1, 'accepted': True,
                   'input_sha256': hashlib.sha256(raw).hexdigest()}
        # Model's indivisible transition: record + immutable receipt + dispatch obligation.
        self.s['actions'][key] = {'raw': raw, 'receipt': receipt, 'payload': p}
        c['messages'].append(key)
        self.s['jobs'][run] = {'key': key, 'state': 'pending'}
        if crash == 'after_commit':
            raise LostAck()
        return deepcopy(receipt)

    def query(self, a, mid):
        self.authorize(a)
        key = (a.principal, 'receive', mid)
        if key in self.s['expired']:
            return {'state': 'recovery_expired'}
        action = self.s['actions'].get(key)
        if action is None:
            # Only a successful authoritative lookup of the intact ledger means absent.
            return {'state': 'not_received'}
        run = action['receipt']['run_id']
        state = ('result_available' if self.s['runs'].get(run, {}).get('result') is not None
                 else 'accepted_pending' if run not in self.s['runs'] else 'running')
        return {'state': state, 'receipt': deepcopy(action['receipt']),
                'result': deepcopy(self.s['runs'].get(run, {}).get('result'))}

    def deliver(self, a, mid, crash=None):
        q = self.query(a, mid)
        if 'receipt' not in q:
            raise Rejected('unavailable')
        run = q['receipt']['run_id']
        c = self.chat(a, q['receipt']['conversation_id'])
        for key in c['messages'][:q['receipt']['sequence'] - 1]:
            if self.query(a, key[2])['state'] != 'result_available':
                raise Rejected('prior_run_pending')
        # RUN must atomically deduplicate the original run ID before external work.
        self.s['runs'].setdefault(run, {'result': None})
        if crash == 'after_run_accept':
            raise LostAck()
        self.s['jobs'][run]['state'] = 'delivered'
        return run

    def finish(self, a, mid, result):
        q = self.query(a, mid)
        if 'receipt' not in q or result is None:
            raise Rejected('invalid_transition')
        run = self.s['runs'].get(q['receipt']['run_id'])
        if run is None or (run['result'] is not None and run['result'] != result):
            raise Rejected('invalid_transition')
        run['result'] = deepcopy(result)

    def page(self, a, cid, cursor=None, limit=2):
        c = self.chat(a, cid)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise Rejected('invalid_input')
        if cursor is None:
            snapshot, offset = deepcopy(c['messages']), 0
        else:
            token = self.s['cursors'].get(cursor)
            if token is None or token['binding'] != (a.principal, a.revision, cid, c['generation'], c['epoch']):
                raise Rejected('resync_required')
            snapshot, offset = token['snapshot'], token['offset']
        end = min(offset + limit, len(snapshot))
        items = [deepcopy(self.s['actions'][k]['receipt']) for k in snapshot[offset:end]]
        next_cursor = None
        if end < len(snapshot):
            self.s['clock'] += 1
            next_cursor = 'fixture-cursor-' + str(self.s['clock'])
            self.s['cursors'][next_cursor] = {
                'binding': (a.principal, a.revision, cid, c['generation'], c['epoch']),
                'snapshot': deepcopy(snapshot), 'offset': end}
        return {'items': items, 'next_cursor': next_cursor, 'snapshot_count': len(snapshot)}

    def end(self, a, cid):
        c = self.chat(a, cid)
        if cid not in self.s['ended']:
            # Stable end boundary; subsequent messages require a new explicit conversation.
            self.s['ended'][cid] = {'conversation_id': cid, 'end_id': 'fixture-end-' + cid,
                                    'through_sequence': len(c['messages'])}
        return deepcopy(self.s['ended'][cid])

    def summary_batch(self, a, cid, limit=2):
        c = self.chat(a, cid)
        if cid not in self.s['ended'] or type(limit) is not int or not 1 <= limit <= 100:
            raise Rejected('invalid_transition')
        boundary = self.s['ended'][cid]
        after = self.s['summary_acks'].get(cid, 0)
        through = min(after + limit, boundary['through_sequence'])
        keys = c['messages'][after:through]
        if any(self.query(a, k[2])['state'] != 'result_available' for k in keys):
            raise Rejected('run_result_pending')
        return {'boundary': deepcopy(boundary), 'after': after, 'through': through,
                'sources': [deepcopy(self.s['actions'][k]) for k in keys]}

    def ack_summary(self, a, cid, batch, durable_receipt):
        self.chat(a, cid)
        current = self.s['summary_acks'].get(cid, 0)
        # Compare the exact original batch; consumer checkpoint must be durable first.
        expected = self.summary_batch(a, cid, max(1, batch['through'] - batch['after']))
        if batch != expected or not durable_receipt or batch['after'] != current:
            raise Rejected('checkpoint_conflict')
        self.s['summary_acks'][cid] = batch['through']

    def conversations(self, a, cursor=None, limit=2):
        self.authorize(a)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise Rejected('invalid_input')
        binding = (a.principal, a.revision, 'conversation-list')
        if cursor is None:
            snapshot = [(cid, c['generation'], c['epoch'])
                        for cid, c in self.s['chats'].items() if c['owner'] == a.principal]
            offset = 0
        else:
            token = self.s['cursors'].get(cursor)
            if token is None or token['binding'] != binding:
                raise Rejected('resync_required')
            snapshot, offset = token['snapshot'], token['offset']
        # Validate the whole captured snapshot before returning any ID. A removed or
        # revoked item invalidates this snapshot; never silently skip it as success.
        for entry in snapshot:
            if not isinstance(entry, tuple) or len(entry) != 3:
                raise Rejected('resync_required')
            cid, generation, epoch = entry
            c = self.s['chats'].get(cid)
            if (c is None or c['owner'] != a.principal
                    or c['generation'] != generation or c['epoch'] != epoch):
                raise Rejected('resync_required')
        end = min(offset + limit, len(snapshot))
        nxt = None
        if end < len(snapshot):
            self.s['clock'] += 1
            nxt = 'fixture-cursor-' + str(self.s['clock'])
            self.s['cursors'][nxt] = {'binding': binding, 'snapshot': deepcopy(snapshot), 'offset': end}
        return {'items': [cid for cid, _, _ in snapshot[offset:end]], 'next_cursor': nxt}
