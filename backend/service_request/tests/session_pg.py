"""#1770 service conversation and server-initiated messages on a fresh restricted PG.

scripts/pg_suites.py service_session. Runtime SQL runs as cj_m1_runtime, the account hook as
cj_local_cleanup; only test setup and inspection use the cluster owner. Synthetic data only.
Covers ADR-0009 section 3 "to be verified": server message vs user send (one total order,
409 SEQUENCE_CONFLICT then reconcile_original), vs #163 send-status read (lock, one read of
receipt and head, no deadlock), and duplicate triggers of one state change (one message).
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid

import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import migrate  # noqa: E402
from cj_cleanup.account_hooks import MESSAGE, DomainHook  # noqa: E402
from cj_cleanup.coordinator import Coordinator  # noqa: E402
from cj_cleanup.core import digest, encode  # noqa: E402
from cj_cleanup.hooks_v1_1 import Selection  # noqa: E402
from cj_cleanup.registry import freeze  # noqa: E402
from cj_cleanup.store import Store  # noqa: E402
from cj_message.domain import Command, SequenceConflict, Service, Unavailable as MessageUnavailable  # noqa: E402
from cj_message.postgres import Repository as MessageRepository  # noqa: E402
from cj_message.service_session import open_service_conversation, service_messages  # noqa: E402
from cj_message.service_session_cleanup import ServiceSessionHook  # noqa: E402
from cj_service_request.store import FeatureDisabled, Repository  # noqa: E402

POLICY = {'cancellation_policy': {'text_en': 'Free cancellation until arranged.', 'text_zh': '安排前可免费取消。'},
          'refund_by': {'text_en': 'Refunded manually by the operator.', 'text_zh': '由运营主体人工退款。'}}
QUOTE = {'amount_minor': 100, 'currency': 'CNY', 'payment': 'outside_app',
         'instructions_en': 'Staff will tell you how to pay outside the app.', 'instructions_zh': '工作人员会告知 App 外的付款方式。'}
ESCORT = {'escort_display_name': 'Escort A', 'arrival': {'local_time': '2026-12-10T09:00', 'place': 'Gate 1'}}
STAFF = dict(actor='staff', staff_ref='staff-internal-7')


def body(cid):
    return json.dumps(dict(client_request_id=cid, service_type='gz_business_escort_zh_en', service_date='2026-12-10',
                           time_window='half_day_am', venue='Synthetic Hall A', customer_name='Test Customer',
                           contact_phone='+85200000000', meeting_purpose='', counterpart=None, note='private note',
                           consents=dict(location_sensitive=True, share_with_escort=True, cross_border=True,
                                         text_version='svc-consent-1')),
                      ensure_ascii=False, separators=(',', ':')).encode()


def wire(cid, generation, sequence, mid=None, text='你好'):
    return json.dumps(dict(version='MESSAGE-send.1', conversation_id=cid, message_id=mid or 'm-' + uuid.uuid4().hex,
                           text=text, trip_id=None, creation_intent='none', expected_generation=generation,
                           expected_sequence=sequence), ensure_ascii=False).encode()


def expect(exc, fn, *args, **kw):
    try:
        fn(*args, **kw)
    except exc:
        return
    raise AssertionError(f'{getattr(fn, "__name__", fn)} did not raise {exc.__name__}')


class Bound:
    """Real runtime connection whose MESSAGE scope is bound per transaction (LocalDatabase shape)."""

    def __init__(self, connection, scope):
        self.c, self.scope = connection, scope

    @property
    def autocommit(self):
        return self.c.autocommit

    def cursor(self):
        return self.c.cursor()

    def bind_scope(self, cur):
        cur.execute("SELECT set_config('cj.message_scope',%s,true)", (self.scope,))

    def commit(self):
        self.c.commit()

    def rollback(self):
        self.c.rollback()

    def close(self):
        self.c.close()


def main(config):
    with psycopg.connect(**config, autocommit=True) as conn:
        assert conn.execute('SELECT max(version) FROM cj.schema_migrations').fetchone()[0] >= 57
    runtime = lambda: psycopg.connect(**dict(config, user='cj_m1_runtime'))
    owner = lambda: psycopg.connect(**config)
    flag = {'on': False}
    requests = lambda scope: Repository(runtime, scope, policy=POLICY, flag=lambda: flag['on'])
    messages = lambda scope: MessageRepository(lambda: Bound(runtime(), scope), scope, service_sessions=True)
    chat = lambda scope: Service(messages(scope), lambda: 'r-' + uuid.uuid4().hex)
    alice, bob = 'local:test:alice', 'local:test:bob'

    # Switched off: no service conversation is created.
    with owner() as conn:
        conn.execute('INSERT INTO cj_message_scope(scope) VALUES(%s),(%s)', (alice, bob))
    assert open_service_conversation(messages(alice), enabled=False) is None
    expect(FeatureDisabled, requests(alice).submit, body('c0'))
    with owner() as conn:
        assert conn.execute("SELECT count(*) FROM cj_message_chat WHERE conversation_kind='service'").fetchone()[0] == 0
    flag['on'] = True
    req = requests(alice).submit(body('c1'))
    rid = req['request_id']
    cid, head = open_service_conversation(messages(alice), enabled=False)
    assert cid.startswith('svc_') and head.last_sequence == 1
    assert open_service_conversation(messages(alice), enabled=True)[0] == cid  # one per account
    view = service_messages(messages(alice), cid)
    first = view['messages'][0]
    assert first['origin'] == 'server_initiated' and first['role'] == 'assistant'
    assert first['signature'] == {'zh': 'CJ 服务团队', 'en': 'CJ Service Team'} and first['provided_by_human'] is True
    assert '真人' in first['text_zh'] and 'human' in first['text_en']
    assert rid not in json.dumps(view, ensure_ascii=False, default=str)
    print('PASS switched off: no service conversation created; on: submit opens one service conversation, '
          'server-signed server_initiated message states a human provides the service, no authority in projection')

    # Isolation: service-chat receipts get no RUN delivery; travel sends and raw side rows refused.
    svc = chat(alice)
    generation = head.generation
    user = svc.receive(wire(cid, generation, 1))
    assert user.sequence == 2
    assert svc.pending() == []
    with owner() as conn:
        assert conn.execute('SELECT count(*) FROM cj_message_delivery WHERE scope=%s', (alice,)).fetchone()[0] == 0
    with runtime() as conn:
        conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        expect(psycopg.Error, conn.execute, 'INSERT INTO cj_message_delivery(scope,message_id,run_id) VALUES(%s,%s,%s)',
               (alice, user.message_id, user.run_id))
        conn.rollback()
    command = Command.parse(wire(cid, generation, 2))
    for travel, dialogue in ((True, None), (False, object())):
        with messages(alice).transaction() as tx:
            tx.lock_scope()
            expect(MessageUnavailable, svc.accept_new, tx, command, travel=travel, dialogue=dialogue)
    with owner() as conn:
        assert conn.execute('SELECT last_sequence FROM cj_message_chat WHERE scope=%s AND conversation_id=%s',
                            (alice, cid)).fetchone()[0] == 2
    print('PASS isolation: service receipt has no delivery/RUN (no planning or memory extraction), '
          'raw delivery insert refused, travel send not accepted')

    # Server message vs user send: one total order; in-flight send gets 409 and reconciles.
    staff = requests(alice)
    staff.transition(rid, 'accepted', evidence_kind='staff_accept', evidence_body='desk', **STAFF)
    staff.transition(rid, 'quoted', evidence_kind='quote', evidence_body='q', quote=QUOTE, **STAFF)
    conflicts = wins = 0
    for _ in range(24):
        status = svc.send_status(cid)
        g, s = status.head.generation, status.head.last_sequence
        raw = wire(cid, g, s)
        barrier = threading.Barrier(2)

        def user_send():
            barrier.wait()
            try:
                return svc.receive(raw)
            except SequenceConflict:
                return None

        def server_send():
            barrier.wait()
            return staff.transition(rid, 'quoted', evidence_kind='quote', evidence_body='q', quote=QUOTE, **STAFF)
        with ThreadPoolExecutor(max_workers=2) as pool:
            sent, _ = pool.submit(user_send), pool.submit(server_send)
            receipt = sent.result(timeout=20)
        if receipt is None:
            conflicts += 1
            # reconcile_original (SEND-PERMIT section 3): receipt null, head moved past s -> not_accepted.
            mid = json.loads(raw)['message_id']
            status = svc.send_status(cid, mid)
            assert status.stored is None and status.head.last_sequence == s + 1
            retry = svc.receive(wire(cid, status.head.generation, status.head.last_sequence))
            assert retry.sequence == s + 2
        else:
            wins += 1
            assert receipt.sequence == s + 1
    view = service_messages(messages(alice), cid)
    seqs = [m['sequence'] for m in view['messages']]
    assert seqs == list(range(1, view['last_sequence'] + 1)), seqs
    # In flight: the state change is already queued on the scope row lock when the user send arrives.
    status = svc.send_status(cid)
    raw = wire(cid, status.head.generation, status.head.last_sequence)
    blocker = runtime()
    try:
        blocker.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        blocker.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE', (alice,))

        def waiting(n):
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with owner() as inspect:
                    if inspect.execute("SELECT count(*) FROM pg_stat_activity WHERE usename='cj_m1_runtime' "
                                       "AND wait_event_type='Lock'").fetchone()[0] >= n:
                        return
                time.sleep(.01)
            raise AssertionError('writers did not queue on the scope lock')
        with ThreadPoolExecutor(max_workers=2) as pool:
            server = pool.submit(staff.transition, rid, 'quoted', evidence_kind='quote', evidence_body='q',
                                 quote=QUOTE, **STAFF)
            waiting(1)
            user = pool.submit(svc.receive, raw)
            waiting(2)
            blocker.commit()
            server.result(timeout=20)
            try:
                user.result(timeout=20)
            except SequenceConflict:
                pass
            else:
                raise AssertionError('in-flight user send was not refused')
    finally:
        blocker.close()
    status = svc.send_status(cid, json.loads(raw)['message_id'])
    assert status.stored is None
    assert svc.receive(wire(cid, status.head.generation, status.head.last_sequence)).sequence == status.head.last_sequence + 1
    conflicts += 1

    # One user deterministic 409: a server message lands between head read and send.
    status = svc.send_status(cid)
    stale = wire(cid, status.head.generation, status.head.last_sequence)
    staff.transition(rid, 'quoted', evidence_kind='quote', evidence_body='q', quote=QUOTE, **STAFF)
    expect(SequenceConflict, svc.receive, stale)
    status = svc.send_status(cid, json.loads(stale)['message_id'])
    assert status.stored is None
    assert svc.receive(wire(cid, status.head.generation, status.head.last_sequence)).sequence == status.head.last_sequence + 1
    conflicts += 1
    assert conflicts >= 1
    print(f'PASS server message vs user send x24 (+1 queued in flight, +1 stale head): single total order, contiguous sequences; '
          f'{conflicts} in-flight sends got SEQUENCE_CONFLICT and reconciled, {wins} took the number first')

    # Server message vs #163 send-status read: consistent read-back, no deadlock.
    status = svc.send_status(cid)
    mine = svc.receive(wire(cid, status.head.generation, status.head.last_sequence))
    stop, seen, errors = threading.Event(), [], []

    def reader():
        while not stop.is_set():
            try:
                st = svc.send_status(cid, mine.message_id)
                assert st.stored.receipt == mine and st.head.last_sequence >= mine.sequence
                seen.append(st.head.last_sequence)
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(repr(exc))
                return

    with ThreadPoolExecutor(max_workers=4) as pool:
        readers = [pool.submit(reader) for _ in range(3)]
        for _ in range(12):
            staff.transition(rid, 'quoted', evidence_kind='quote', evidence_body='q', quote=QUOTE, **STAFF)
        stop.set()
        for r in readers:
            r.result(timeout=20)
    assert not errors, errors
    assert seen
    final = svc.send_status(cid).head.last_sequence
    assert max(seen) <= final and final == mine.sequence + 12
    with owner() as conn:
        assert conn.execute("SELECT count(*) FROM pg_stat_database WHERE datname='postgres' AND deadlocks>0").fetchone()[0] == 0
    print(f'PASS server message vs send-status read: {len(seen)} locked reads each saw the receipt and a head '
          '>= it, no error, no deadlock')

    # Duplicate triggers of one state change: exactly one message.
    with owner() as conn:
        before = conn.execute('SELECT count(*) FROM cj_service_message WHERE scope=%s', (alice,)).fetchone()[0]
        seq = conn.execute('SELECT max(seq) FROM cj_service_request_history WHERE request_id=%s', (rid,)).fetchone()[0]
    assert staff.redeliver(rid, seq) is None  # already delivered in the state-change transaction
    with owner() as conn:  # setup only: a recorded state change whose message was never written
        conn.execute("INSERT INTO cj_service_request_history(scope,request_id,seq,from_state,to_state,actor_kind,staff_ref,"
                     "evidence_kind,evidence_body) VALUES(%s,%s,%s,'quoted','quoted','staff','s','quote','q')",
                     (alice, rid, seq + 1))
    barrier = threading.Barrier(8)

    def again(_):
        barrier.wait()
        return staff.redeliver(rid, seq + 1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(again, range(8)))
    assert sum(r is not None for r in results) == 1, results
    with owner() as conn:
        assert conn.execute('SELECT count(*) FROM cj_service_message WHERE scope=%s', (alice,)).fetchone()[0] == before + 1
        assert conn.execute('SELECT count(*) FROM cj_service_message_authority WHERE scope=%s AND request_id=%s AND history_seq=%s',
                            (alice, rid, seq + 1)).fetchone()[0] == 1
    print('PASS duplicate triggers: redelivery of a delivered change writes nothing; 8 concurrent triggers of one '
          'undelivered change write exactly one message and one authority row')

    # Named human details: arranged message mentions the escort; contract human_service stays the carrier.
    arranged = staff.transition(rid, 'arranged', evidence_kind='arrangement', evidence_body='ok', escort=ESCORT, **STAFF)
    last = service_messages(messages(alice), cid)['messages'][-1]
    assert 'Escort A' in last['text_zh'] and 'Gate 1' in last['text_en'] and last['provided_by_human'] is True
    assert arranged['human_service']['escort_display_name'] == 'Escort A'
    text = json.dumps(service_messages(messages(alice), cid), ensure_ascii=False, default=str)
    assert 'staff-internal-7' not in text and rid not in text
    print('PASS arranged message names the human escort, time and place; human_service unchanged; no staff ref')

    # Grants and owners: audit unreadable, messages append-only, other owner sees and writes nothing.
    for statement in ('SELECT * FROM cj_service_message_authority', "UPDATE cj_service_message SET body_zh='x'",
                      'DELETE FROM cj_service_message', 'DELETE FROM cj_service_message_authority',
                      "UPDATE cj_message_chat SET conversation_kind='trip' WHERE conversation_kind='service'"):
        with runtime() as conn:
            conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
            assert conn.execute("SELECT count(*) FROM cj_message_chat WHERE conversation_kind='service'").fetchone()[0] == 1
            expect(psycopg.Error, conn.execute, statement)
            conn.rollback()
    with runtime() as conn:
        conn.execute("SELECT set_config('cj.message_scope',%s,false)", (bob,))
        assert conn.execute('SELECT count(*) FROM cj_service_message').fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM cj_message_chat WHERE conversation_kind='service'").fetchone()[0] == 0
        expect(psycopg.Error, conn.execute,
               "INSERT INTO cj_service_message(scope,conversation_id,generation,sequence,message_id,origin,provided_by_human,"
               "body_zh,body_en) VALUES(%s,%s,%s,99,%s,'server_initiated',true,'x','x')",
               (alice, cid, generation, 'sm_' + '0' * 32))
        conn.rollback()
    expect(MessageUnavailable, service_messages, messages(bob), cid)
    print('PASS runtime cannot read authority audit, update/delete server messages or change kind; '
          'other owner sees none and cannot write into this conversation')

    # Switched off with an existing request: ends still reach an existing service conversation; no new one.
    open_a = requests(alice).submit(body('c2'))
    dave = 'local:test:dave'
    with owner() as conn:
        conn.execute('INSERT INTO cj_message_scope(scope) VALUES(%s)', (dave,))
    open_d = requests(dave).submit(body('d1'))
    with owner() as conn:
        conn.execute("UPDATE cj_message_chat SET active=false WHERE scope=%s AND conversation_kind='service'", (dave,))
    flag['on'] = False
    head_before = svc.send_status(cid).head.last_sequence
    requests(alice).cancel(open_a['request_id'], 'c2')
    last = service_messages(messages(alice), cid)['messages'][-1]
    assert last['sequence'] == head_before + 1 and '取消' in last['text_zh']
    requests(dave).cancel(open_d['request_id'], 'd1')
    with owner() as conn:
        assert conn.execute("SELECT count(*) FROM cj_message_chat WHERE scope=%s AND conversation_kind='service' AND active",
                            (dave,)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM cj_service_message_authority WHERE scope=%s AND request_id=%s',
                            (dave, open_d['request_id'])).fetchone()[0] == 1  # submitted only
    assert open_service_conversation(messages(dave), enabled=False) is None
    flag['on'] = True
    print('PASS switched off: cancellation still reaches the existing service conversation; '
          'account without an active one gets no message and no new conversation')

    # Down with retained data refused.
    try:
        with psycopg.connect(**config, autocommit=True) as conn:
            migrate.down(conn, migrate.load(), 56)
    except psycopg.Error:
        pass
    else:
        raise AssertionError('down dropped retained service conversations')

    # Account erasure through the existing business/message hook: cascades remove both new tables.
    subject = digest(b'synthetic alice subject')
    store = Store(lambda: psycopg.connect(**dict(config, user='cj_local_cleanup')), subject, lambda stage: None)
    target, sessions = 'business/message', 'business/service-sessions'
    registry = encode(dict(version='service-session-local-proof', stores=[dict(id='business', objects=[
        dict(id='message', cleanup_protocol='CLEANUP@1.1'), dict(id='service-sessions', cleanup_protocol='CLEANUP@1.1')])]))
    frozen = freeze(registry, (target, sessions), versions=('CLEANUP@1.1',))

    def operation(subject, scope, store, name):
        plan = {t: {'domain_scope': scope, 'selection': {'kind': 'account'}} for t in (target, sessions)}
        host = Coordinator(store, lambda: frozen, {target: DomainHook(store, scope, MESSAGE),
                                                   sessions: ServiceSessionHook(store, scope)})
        host.create(name, digest(b'synthetic confirmation'), 'account', plan)
        with store.transaction(name) as cur:
            cur.execute("INSERT INTO cj_cleanup_request(subject_digest,operation_id,action_id,input_digest,registry_bytes,"
                        "inventory,plan_bytes,plan_digest,binding_id,phase) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,"
                        "'fixture-binding','confirmed')",
                        (subject, name, name + '-action', digest(b'proof'), registry, json.dumps([target, sessions]),
                         encode(plan), digest(encode(plan))))
            cur.execute('INSERT INTO cj_account_fence(subject_digest,owner_digest,operation_id,namespace_digests) '
                        'VALUES(%s,%s,%s,%s::jsonb)', (subject, digest(scope.encode()), name,
                                                      json.dumps([digest(scope.encode())])))
        return host, {t: host.request(name, t, scope, Selection('account')) for t in (target, sessions)}

    subject = digest(b'synthetic alice subject')
    store = Store(lambda: psycopg.connect(**dict(config, user='cj_local_cleanup')), subject, lambda stage: None)
    host, req = operation(subject, alice, store, 'erase-service-session')
    host.advance(req[target])  # gateway order: business/message first, unlisted targets after
    assert host.advance(req[sessions])['status'] == 'complete', host.query('erase-service-session')
    # Fail-closed: the verify-only hook refuses while rows remain (dave's message hook not run).
    dsubject = digest(b'synthetic dave subject')
    dstore = Store(lambda: psycopg.connect(**dict(config, user='cj_local_cleanup')), dsubject, lambda stage: None)
    dhost, dreq = operation(dsubject, dave, dstore, 'erase-dave-sessions')
    try:
        state = dhost.advance(dreq[sessions])
    except Exception:  # noqa: BLE001 - a refusal is the expected fail-closed outcome
        state = dhost.query('erase-dave-sessions')
    step = next(x for x in state['steps'] if x['target'] == sessions)
    assert step['state'] != 'confirmed' and state['status'] != 'complete', state
    with owner() as conn:
        assert conn.execute('SELECT count(*) FROM cj_service_message WHERE scope=%s', (dave,)).fetchone()[0] == 1
    print('PASS account erasure via existing business/message hook cascades server messages and authority audit '
          '(no new DELETE grant), verify-only business/service-sessions hook confirms empty and refuses while rows remain; other account kept; nonempty down refused')


if __name__ == '__main__':
    main(json.loads(Path(os.environ['CJ_E2E_CONNINFO']).read_text()))
