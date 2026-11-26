"""#1769 SERVICE-REQUEST@1 store on a fresh restricted PG (scripts/pg_suites.py service_request).

Runtime SQL runs as cj_m1_runtime, the account hook as cj_local_cleanup; only test setup
(backdating terminal times, inspection) uses the cluster owner. Synthetic data only.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import threading
import time

import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import migrate  # noqa: E402
from cj_cleanup.coordinator import Coordinator  # noqa: E402
from cj_cleanup.core import digest, encode  # noqa: E402
from cj_cleanup.hooks_v1_1 import Selection  # noqa: E402
from cj_cleanup.registry import freeze  # noqa: E402
from cj_cleanup.store import Store  # noqa: E402
from cj_service_request.contract import InvalidInput, InvalidTransition  # noqa: E402
from cj_service_request.lifecycle import ServiceRequestHook, scope_digest  # noqa: E402
from cj_service_request.store import (Conflict, FeatureDisabled, NotFound, Repository,  # noqa: E402
                                      Unavailable)

POLICY = {'cancellation_policy': {'text_en': 'Free cancellation until arranged.', 'text_zh': '安排前可免费取消。'},
          'refund_by': {'text_en': 'Refunded manually by the operator.', 'text_zh': '由运营主体人工退款。'}}
QUOTE = {'amount_minor': 100, 'currency': 'CNY', 'payment': 'outside_app',
         'instructions_en': 'Staff will tell you how to pay outside the app.', 'instructions_zh': '工作人员会告知 App 外的付款方式。'}
ESCORT = {'escort_display_name': 'Escort A', 'arrival': {'local_time': '2026-12-10T09:00', 'place': 'Gate 1'}}


def body(cid, **change):
    value = dict(client_request_id=cid, service_type='gz_business_escort_zh_en', service_date='2026-12-10',
                 time_window='half_day_am', venue='Synthetic Hall A', customer_name='Test Customer',
                 contact_phone='+85200000000', meeting_purpose='', counterpart=None, note='private note',
                 consents=dict(location_sensitive=True, share_with_escort=True, cross_border=True,
                               text_version='svc-consent-1'))
    value.update(change)
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def expect(exc, fn, *args, **kw):
    try:
        fn(*args, **kw)
    except exc:
        return
    raise AssertionError(f'{fn.__name__} did not raise {exc.__name__}')


def main(config):
    with psycopg.connect(**config, autocommit=True) as conn:
        assert conn.execute('SELECT max(version) FROM cj.schema_migrations').fetchone()[0] >= 56
    runtime = lambda: psycopg.connect(**dict(config, user='cj_m1_runtime'))
    owner = lambda: psycopg.connect(**config)
    cleanup = lambda: psycopg.connect(**dict(config, user='cj_local_cleanup'))
    flag = {'on': True}
    repo = lambda scope: Repository(runtime, scope, policy=POLICY, flag=lambda: flag['on'])
    alice, bob = repo('local:test:alice'), repo('local:test:bob')

    # Submit, exact-byte idempotence, conflict, own-scope reads.
    raw = body('c1')
    first = alice.submit(raw)
    assert first['state'] == 'submitted' and [h['to'] for h in first['history']] == ['user_confirmed', 'submitted']
    assert first['quote'] is None and first['human_service']['provided_by_human'] is True
    assert first['human_service']['escort_display_name'] is None and first['details']['note'] == 'private note'
    assert first['shared_with_escort'] == ['customer_name', 'language', 'service_date', 'time_window', 'venue',
                                           'contact_phone']
    assert all(set(h) == {'seq', 'from', 'to', 'at', 'actor'} and set(h['actor']) == {'kind'} for h in first['history'])
    assert alice.submit(raw) == first
    expect(Conflict, alice.submit, body('c1', note='changed'))
    expect(InvalidInput, alice.submit, b'{"owner":"x"}')
    assert alice.get(first['request_id']) == first == alice.by_client_request_id('c1')
    assert alice.by_client_request_id('missing') is None
    expect(NotFound, bob.get, first['request_id'])
    expect(NotFound, alice.get, 'sr_' + '0' * 32)
    assert bob.by_client_request_id('c1') is None
    other = bob.submit(raw)  # same client id in another account is a separate request
    assert other['request_id'] != first['request_id']
    print('PASS submit/original bytes/idempotent replay/409 conflict/own-scope read; other and missing indistinguishable')

    # Concurrent duplicates produce exactly one request.
    dup = body('c-concurrent')
    barrier = threading.Barrier(8)

    def race(_):
        barrier.wait()
        return alice.submit(dup)['request_id']
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = set(pool.map(race, range(8)))
    with owner() as conn:
        count = conn.execute("SELECT count(*) FROM cj_service_request WHERE client_request_id='c-concurrent'").fetchone()[0]
        hist = conn.execute("SELECT count(*) FROM cj_service_request_history h JOIN cj_service_request r USING(scope,request_id) "
                            "WHERE r.client_request_id='c-concurrent'").fetchone()[0]
    assert len(ids) == 1 and count == 1 and hist == 2, (ids, count, hist)
    print('PASS 8 concurrent identical submissions -> one request and one history pair')

    # State machine through the contract; illegal transitions and missing evidence refused.
    rid = first['request_id']
    staff = dict(actor='staff', staff_ref='staff-internal-7')
    expect(InvalidTransition, alice.transition, rid, 'completed', evidence_kind='completion_summary', evidence_body='x', **staff)
    expect(InvalidInput, alice.transition, rid, 'accepted', evidence_kind='quote', evidence_body='x', **staff)
    expect(InvalidTransition, alice.transition, rid, 'accepted', actor='user', evidence_kind='staff_accept', evidence_body='x')
    expect(InvalidInput, alice.transition, rid, 'accepted', actor='staff', evidence_kind='staff_accept', evidence_body='x')
    alice.transition(rid, 'accepted', evidence_kind='staff_accept', evidence_body='accepted by desk', **staff)
    expect(InvalidInput, alice.transition, rid, 'quoted', evidence_kind='quote', evidence_body='q', **staff)
    quoted = alice.transition(rid, 'quoted', evidence_kind='quote', evidence_body='quote v1', quote=QUOTE, **staff)
    assert quoted['quote'] == QUOTE and quoted['state'] == 'quoted'
    expect(InvalidInput, alice.transition, rid, 'arranged', evidence_kind='arrangement', evidence_body='a', **staff)
    arranged = alice.transition(rid, 'arranged', evidence_kind='arrangement', evidence_body='escort confirmed',
                                escort=ESCORT, **staff)
    assert arranged['human_service']['escort_display_name'] == 'Escort A'
    view = alice.escort_view(rid, 'escort-ref-1')
    assert set(view) == set(arranged['shared_with_escort']) and 'note' not in view and view['language'] == 'zh_en'
    alice.transition(rid, 'in_progress', evidence_kind='arrival', evidence_body='arrived', **staff)
    expect(InvalidTransition, alice.transition, rid, 'completed', actor='system', evidence_kind='completion_summary',
           evidence_body='x')
    unknown = alice.transition(rid, 'outcome_unknown', evidence_kind='unknown_reason', evidence_body='no evidence', **staff)
    expect(InvalidTransition, alice.cancel, rid, 'c1')
    done = alice.transition(rid, 'completed', evidence_kind='completion_summary', evidence_body='SUMMARY_SECRET', **staff)
    assert done['state'] == 'completed' and unknown['state'] == 'outcome_unknown'
    expect(InvalidTransition, alice.transition, rid, 'unavailable', evidence_kind='unavailable_reason', evidence_body='x', **staff)
    text = json.dumps(done)
    assert 'staff-internal-7' not in text and 'SUMMARY_SECRET' not in text and 'escort confirmed' not in text
    assert [h['seq'] for h in done['history']] == list(range(1, 9))
    with owner() as conn:
        first_terminal, later = conn.execute(
            "SELECT first_terminal_at,(SELECT max(at) FROM cj_service_request_history WHERE request_id=%s) "
            'FROM cj_service_request WHERE request_id=%s', (rid, rid)).fetchone()
        assert first_terminal < later  # outcome_unknown -> completed keeps the first terminal time
        expect(psycopg.Error, conn.execute, "UPDATE cj_service_request_history SET evidence_body='rewritten' WHERE request_id=%s", (rid,))
        conn.rollback()
    with runtime() as conn:
        conn.execute("SELECT set_config('cj.message_scope','local:test:alice',false)")
        expect(psycopg.Error, conn.execute, 'UPDATE cj_service_request_history SET evidence_body=NULL WHERE request_id=%s', (rid,))
        conn.rollback()
    with runtime() as conn:
        conn.execute("SELECT set_config('cj.message_scope','local:test:alice',false)")
        expect(psycopg.Error, conn.execute, 'DELETE FROM cj_service_request WHERE request_id=%s', (rid,))
        conn.rollback()
    with cleanup() as conn:
        conn.execute("SELECT set_config('cj.cleanup_scope','local:test:alice',false),"
                     "set_config('cj.cleanup_purpose','service_request_retention',false)")
        assert conn.execute('DELETE FROM cj_service_request WHERE request_id=%s', (rid,)).rowcount == 0
    print('PASS contract transitions/evidence/actors, quote and escort payloads, audited escort view, unknown->completed keeps first terminal time, append-only history, no runtime early delete, no staff ref/evidence in projection')

    # Cancel: idempotent; wrong client id is not found.
    second = alice.submit(body('c2', meeting_purpose='Meet supplier', counterpart={'company': 'Co', 'name': ''}))
    assert second['shared_with_escort'] == ['customer_name', 'language', 'service_date', 'time_window', 'venue',
                                            'meeting_purpose', 'counterpart', 'contact_phone']
    expect(NotFound, alice.cancel, second['request_id'], 'c1')
    expect(NotFound, bob.cancel, second['request_id'], 'c2')
    cancelled = alice.cancel(second['request_id'], 'c2')
    assert cancelled['state'] == 'user_cancelled' and alice.cancel(second['request_id'], 'c2') == cancelled
    print('PASS user cancel idempotent, foreign/wrong-id cancel indistinguishable from missing')

    # Switch off: no new submission (nothing written); reads, replay, cancel and terminal progress continue.
    open_a = alice.submit(body('c3'))
    open_b = alice.submit(body('c4'))
    flag['on'] = False
    expect(FeatureDisabled, alice.submit, body('c5'))
    assert alice.by_client_request_id('c5') is None
    assert alice.submit(body('c3')) == alice.get(open_a['request_id'])
    expect(FeatureDisabled, alice.transition, open_b['request_id'], 'accepted', evidence_kind='staff_accept',
           evidence_body='x', **staff)
    assert alice.cancel(open_a['request_id'], 'c3')['state'] == 'user_cancelled'
    assert alice.transition(open_b['request_id'], 'unavailable', evidence_kind='unavailable_reason',
                            evidence_body='no escort', **staff)['state'] == 'unavailable'
    assert len(alice.list_own()) == 5
    flag['on'] = True
    print('PASS CJ_SERVICE_REQUEST_ENABLED off: new submit feature_disabled and unwritten; replay/read/cancel/terminal progress continue')

    # Retention: summary body 90 days, whole request 12 months, from first terminal time.
    with owner() as conn:
        conn.execute("UPDATE cj_service_request SET first_terminal_at=clock_timestamp()-interval '91 days' WHERE request_id=%s", (rid,))
    assert alice.purge_expired(cleanup) == {'summaries_erased': 1, 'requests_deleted': 0}
    with owner() as conn:
        assert conn.execute("SELECT evidence_body FROM cj_service_request_history WHERE request_id=%s AND evidence_kind='completion_summary'",
                            (rid,)).fetchone() == (None,)
        assert conn.execute("SELECT evidence_body FROM cj_service_request_history WHERE request_id=%s AND evidence_kind='arrival'",
                            (rid,)).fetchone() == ('arrived',)
        conn.execute("UPDATE cj_service_request SET first_terminal_at=clock_timestamp()-interval '13 months' WHERE request_id=%s", (rid,))
    assert alice.purge_expired(cleanup) == {'summaries_erased': 0, 'requests_deleted': 1}
    expect(NotFound, alice.get, rid)
    with owner() as conn:
        assert conn.execute('SELECT count(*) FROM cj_service_request_history WHERE request_id=%s', (rid,)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM cj_service_request_view WHERE request_id=%s', (rid,)).fetchone()[0] == 0
    assert len(alice.list_own()) == 4 and bob.get(other['request_id'])['state'] == 'submitted'
    # Cleanup-role retention DELETE negatives: cross-owner and runtime identity delete nothing.
    expired_bob = bob.submit(body('bob-expired'))['request_id']
    with owner() as conn:
        conn.execute("UPDATE cj_service_request SET state='unavailable',first_terminal_at=clock_timestamp()-interval '13 months' "
                     'WHERE request_id=%s', (expired_bob,))
    with cleanup() as conn:
        conn.execute("SELECT set_config('cj.cleanup_scope','local:test:alice',false),"
                     "set_config('cj.cleanup_purpose','service_request_retention',false)")
        assert conn.execute('DELETE FROM cj_service_request WHERE request_id=%s', (expired_bob,)).rowcount == 0
        for table in ('cj_service_request_history', 'cj_service_request_view'):
            assert conn.execute(f'DELETE FROM {table} WHERE request_id=%s', (expired_bob,)).rowcount == 0
    with runtime() as conn:
        conn.execute("SELECT set_config('cj.message_scope','local:test:bob',false)")
        for table in ('cj_service_request', 'cj_service_request_history', 'cj_service_request_view'):
            expect(psycopg.Error, conn.execute, f'DELETE FROM {table} WHERE request_id=%s', (expired_bob,))
            conn.rollback()
            conn.execute("SELECT set_config('cj.message_scope','local:test:bob',false)")
    with owner() as conn:
        assert conn.execute("SELECT count(*) FROM information_schema.role_table_grants WHERE grantee='cj_m1_runtime' "
                            "AND table_name LIKE 'cj_service_request%%' AND privilege_type IN ('DELETE','TRUNCATE')").fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM cj_service_request WHERE request_id=%s', (expired_bob,)).fetchone()[0] == 1
    assert bob.purge_expired(cleanup)['requests_deleted'] == 1
    print('PASS cleanup-role retention DELETE: cross-owner and runtime identity delete nothing; own expired request deleted')
    print('PASS retention: completion_summary body erased after 90 days, request/history/evidence/view audit deleted after 12 months, others kept')

    # Account erasure hook: waits for an in-flight writer, erases everything, fences late writes.
    scope = 'local:test:alice'
    with owner() as conn:
        extra = conn.execute("SELECT request_id FROM cj_service_request WHERE scope=%s AND client_request_id='c-concurrent'", (scope,)).fetchone()[0]
        conn.execute("UPDATE cj_service_request SET state='arranged',arranged_at=clock_timestamp() WHERE request_id=%s", (extra,))
    alice.escort_view(extra, 'escort-ref-2')
    subject = digest(b'synthetic alice subject')
    store = Store(lambda: psycopg.connect(**dict(config, user='cj_local_cleanup')), subject, lambda stage: None)
    target = 'business/service-requests'
    registry = encode(dict(version='service-request-local-proof', stores=[dict(id='business', objects=[dict(
        id='service-requests', cleanup_protocol='CLEANUP@1.1',
        objects=['cj_service_request', 'cj_service_request_history', 'cj_service_request_view', 'cj_service_request_scope'])])]))
    frozen = freeze(registry, (target,), versions=('CLEANUP@1.1',))
    host = Coordinator(store, lambda: frozen, {target: ServiceRequestHook(store, scope)})
    host.create('erase-service-requests', digest(b'synthetic confirmation'), 'account',
                {target: {'domain_scope': scope, 'selection': {'kind': 'account'}}})
    request = host.request('erase-service-requests', target, scope, Selection('account'))
    writer = runtime()
    try:
        writer.execute("SELECT set_config('cj.message_scope',%s,false)", (scope,))
        writer.execute('SELECT retired FROM cj_service_request_scope WHERE scope_digest=%s FOR UPDATE', (scope_digest(scope),))
        with ThreadPoolExecutor(max_workers=1) as pool:
            cleanup = pool.submit(host.advance, request)
            deadline, blocked = time.monotonic() + 5, False
            while time.monotonic() < deadline and not blocked:
                with owner() as inspect:
                    blocked = inspect.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename='cj_local_cleanup' "
                                              "AND wait_event_type='Lock')").fetchone()[0]
                time.sleep(.01)
            assert blocked and not cleanup.done(), 'cleanup did not wait for the in-flight writer'
            writer.execute("INSERT INTO cj_service_request_view(scope,request_id,viewer_ref,fields) VALUES(%s,%s,'inflight','[]')",
                           (scope, extra))
            writer.commit()
            assert cleanup.result(timeout=10)['status'] == 'complete'
    finally:
        writer.close()
    assert host.advance(request)['status'] == 'complete' and host.reconcile(request)['status'] == 'complete'
    with owner() as conn:
        for table in ('cj_service_request', 'cj_service_request_history', 'cj_service_request_view'):
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE scope=%s', (scope,)).fetchone()[0] == 0, table
        assert conn.execute('SELECT retired FROM cj_service_request_scope WHERE scope_digest=%s', (scope_digest(scope),)).fetchone() == (True,)
        assert conn.execute("SELECT count(*) FROM cj_service_request WHERE scope='local:test:bob'").fetchone()[0] == 1
    expect(Unavailable, alice.submit, body('late'))
    expect(Unavailable, alice.by_client_request_id, 'c1')
    with runtime() as conn:
        conn.execute("SELECT set_config('cj.message_scope',%s,false)", (scope,))
        expect(psycopg.Error, conn.execute, 'UPDATE cj_service_request_scope SET retired=false')
        conn.rollback()
    with runtime() as conn:
        conn.execute("SELECT set_config('cj.message_scope',%s,false)", (scope,))
        expect(psycopg.Error, conn.execute,
               "INSERT INTO cj_service_request(scope,request_id,client_request_id,original_input,input_sha256,state,details,human_service) "
               "VALUES(%s,%s,'raw',%s,%s,'submitted','{}','{}')", (scope, 'sr_' + 'a' * 32, b'x', 'b' * 64))
        conn.rollback()
    assert bob.get(other['request_id'])['state'] == 'submitted'
    try:
        with psycopg.connect(**config, autocommit=True) as conn:
            migrate.down(conn, migrate.load(), 55)
    except psycopg.Error:
        pass
    else:
        raise AssertionError('down dropped retained service requests or fence')
    print('PASS account hook: waits for in-flight writer, erases requests/history/evidence/view audit, irreversible fence refuses API and raw late writes, other account kept, original result replayed, nonempty down refused')


if __name__ == '__main__':
    main(json.loads(Path(os.environ['CJ_E2E_CONNINFO']).read_text()))
