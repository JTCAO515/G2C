"""Service conversation and server-initiated assistant messages (#1770, ADR-0009 sections 3-4).

A service conversation is a MESSAGE chat with conversation_kind='service'. It is isolated from
trip conversations: user receipts in it never get a delivery obligation (no RUN, so no planning
context and no memory extraction) and never carry travel/trip/edit references or NEEDS
(enforced in domain.Service.accept_new and by migration 0057 triggers).

A server-initiated message takes last_sequence+1 of the same conversation head under the same
MESSAGE scope row lock as a user send (ADR-0008 single total order). An in-flight user send then
gets SEQUENCE_CONFLICT and recovers with reconcile_original. Authority (which service request,
which state change) goes to cj_service_message_authority, which is INSERT-only for the runtime
and never projected; its primary key makes one state change produce at most one message.

Callers must already have bound cj.message_scope to `scope` in the current transaction.
No HTTP route, push, prompt template or payment lives here.
"""
from __future__ import annotations

import secrets
import uuid

from .domain import Chat, Unavailable

SERVICE = 'service'
ORIGIN_SERVER = 'server_initiated'
ORIGIN_USER = 'user'
# Signed by the server from the conversation kind; never chosen by the client.
SIGNATURE = {SERVICE: {'zh': 'CJ 服务团队', 'en': 'CJ Service Team'}}

_HUMAN_ZH = '本服务由真人陪同人员提供。'
_HUMAN_EN = 'This service is provided by a human escort.'
_BODIES = {
    'submitted': ('已收到你的陪同服务请求，服务团队会尽快确认。',
                  'We received your escort request. The service team will confirm it soon.'),
    'accepted': ('服务团队已受理你的请求，正在准备报价。',
                 'The service team accepted your request and is preparing a quote.'),
    'quoted': ('报价已更新，金额和 App 外付款方式请在服务请求里查看。',
               'The quote is updated. See the service request for the amount and how to pay outside the app.'),
    'in_progress': ('陪同人员已到场，服务进行中。', 'Your escort has arrived. The service is in progress.'),
    'completed': ('本次陪同服务已完成。', 'This escort service is complete.'),
    'user_cancelled': ('你的服务请求已取消。', 'Your service request is cancelled.'),
    'unavailable': ('很抱歉，本次无法为你安排陪同服务。', 'Sorry, we cannot arrange this escort service.'),
    'outcome_unknown': ('我们暂时无法确认本次服务的结果，服务团队核实后会告诉你。',
                        'We cannot confirm the outcome yet. The service team will check and let you know.'),
}


def compose(to_state, human_service):
    """Server-generated bilingual body. Named human service: always says a person provides it.

    The customer-facing human details stay in SERVICE-REQUEST@1 `human_service`; the body may
    mention them but is not their only carrier.
    """
    if to_state == 'arranged':
        name = human_service.get('escort_display_name')
        arrival = human_service.get('arrival') or {}
        if not name or not arrival.get('local_time') or not arrival.get('place'):
            raise Unavailable('arranged without escort details')
        zh = (f'已为你安排真人陪同：{name}，{arrival["local_time"]} 在 {arrival["place"]} 与你会合。'
              '详细信息和取消规则以服务请求页面为准。')
        en = (f'Your human escort {name} will meet you at {arrival["place"]} at {arrival["local_time"]}. '
              'The service request page has the full details and cancellation rules.')
    elif to_state in _BODIES:
        zh, en = _BODIES[to_state]
    else:
        return None
    provided_by_human = human_service.get('provided_by_human') is True
    if provided_by_human:
        zh, en = zh + _HUMAN_ZH, en + ' ' + _HUMAN_EN
    return provided_by_human, zh, en


def _lock_scope(cur, scope, create):
    cur.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE', (scope,))
    if cur.fetchone() is not None:
        return True
    if not create:
        return False
    cur.execute('INSERT INTO cj_message_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING', (scope,))
    cur.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE', (scope,))
    if cur.fetchone() is None:
        raise Unavailable()
    return True


def _service_head(cur, scope):
    cur.execute("SELECT conversation_id,generation,epoch,last_sequence FROM cj_message_chat "
                "WHERE scope=%s AND conversation_kind='service' AND active FOR UPDATE", (scope,))
    return cur.fetchone()


def _open(cur, scope, create):
    """Under the scope lock: the one active service conversation, created only when allowed."""
    row = _service_head(cur, scope)
    if row is not None or not create:
        return row
    cur.execute("INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch,conversation_kind) "
                "VALUES(%s,%s,%s,0,'service') RETURNING conversation_id,generation,epoch,last_sequence",
                (scope, 'svc_' + secrets.token_hex(16), uuid.uuid4().hex))
    return cur.fetchone()


def emit(cur, scope, request_id, history_seq, to_state, human_service, *, create):
    """Write one server-initiated message for one SERVICE-REQUEST state change.

    Returns the written message (message_id, conversation_id, generation, sequence) or None when
    the state has no message, there is no service conversation and none may be created, or this
    state change was already delivered. Never writes NEEDS, RUN or trip data.
    """
    composed = compose(to_state, human_service)
    if composed is None:
        return None
    provided_by_human, zh, en = composed
    if not _lock_scope(cur, scope, create):
        return None
    row = _open(cur, scope, create)
    if row is None:
        return None
    cid, generation, _, last = row
    message_id = 'sm_' + secrets.token_hex(16)
    # Idempotency key first; the FK to the message is deferred to commit.
    cur.execute('INSERT INTO cj_service_message_authority(scope,request_id,history_seq,to_state,message_id) '
                'VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                (scope, request_id, history_seq, to_state, message_id))
    if cur.rowcount == 0:
        return None
    sequence = last + 1
    cur.execute('INSERT INTO cj_service_message(scope,conversation_id,generation,sequence,message_id,origin,'
                'provided_by_human,body_zh,body_en) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (scope, cid, generation, sequence, message_id, ORIGIN_SERVER, provided_by_human, zh, en))
    cur.execute('UPDATE cj_message_chat SET last_sequence=%s WHERE scope=%s AND conversation_id=%s '
                'AND generation=%s AND active AND last_sequence=%s', (sequence, scope, cid, generation, last))
    if cur.rowcount != 1:
        raise Unavailable()
    return {'message_id': message_id, 'conversation_id': cid, 'generation': generation, 'sequence': sequence}


def open_service_conversation(repository, *, enabled):
    """The caller's service conversation; a new one only while CJ_SERVICE_REQUEST_ENABLED is on."""
    if type(enabled) is not bool:
        raise Unavailable()
    with repository.transaction() as tx:
        tx.lock_scope()
        row = _open(tx.cur, repository.scope, enabled)
    if row is None:
        return None
    return row[0], Chat(row[1], row[2], row[3])


def service_messages(repository, conversation_id):
    """Client projection of one service conversation in sequence order.

    User messages come from receipts; server messages carry origin and the server signature.
    Authority audit is never read here.
    """
    with repository.transaction() as tx:
        tx.lock_scope()
        cur = tx.cur
        cur.execute("SELECT generation,last_sequence FROM cj_message_chat WHERE scope=%s AND conversation_id=%s "
                    "AND conversation_kind='service' AND active FOR UPDATE", (repository.scope, conversation_id))
        head = cur.fetchone()
        if head is None:
            raise Unavailable()
        generation, last = head
        cur.execute('SELECT sequence,message_id,raw_input FROM cj_message_receipt WHERE scope=%s AND '
                    'conversation_id=%s AND generation=%s', (repository.scope, conversation_id, generation))
        out = {s: {'sequence': s, 'message_id': m, 'origin': ORIGIN_USER, 'role': 'user', 'raw': bytes(r)}
               for s, m, r in cur.fetchall()}
        cur.execute('SELECT sequence,message_id,provided_by_human,body_zh,body_en FROM cj_service_message '
                    'WHERE scope=%s AND conversation_id=%s AND generation=%s',
                    (repository.scope, conversation_id, generation))
        for s, m, human, zh, en in cur.fetchall():
            if s in out:
                raise Unavailable()
            out[s] = {'sequence': s, 'message_id': m, 'origin': ORIGIN_SERVER, 'role': 'assistant',
                      'signature': SIGNATURE[SERVICE], 'provided_by_human': human, 'text_zh': zh, 'text_en': en}
    if sorted(out) != list(range(1, last + 1)):
        raise Unavailable()
    return {'conversation_id': conversation_id, 'generation': generation, 'last_sequence': last,
            'kind': SERVICE, 'messages': [out[s] for s in sorted(out)]}
