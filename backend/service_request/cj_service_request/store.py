"""SERVICE-REQUEST@1 repository (#1769): owner-scoped store, state machine, retention.

Injected fresh DB-API connections as cj_m1_runtime. The owner scope is server-resolved,
never request data. HTTP routes are not part of this module (operations console #1771,
App ticket); every caller goes through Repository.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import logging
import os
import re
import secrets

from .contract import (EVIDENCE, SERVICE_TYPE, TERMINAL, InvalidInput, InvalidTransition, Submission,
                       check_transition, parse_submission, _text)
from .lifecycle import bind_runtime

FLAG = 'CJ_SERVICE_REQUEST_ENABLED'
LANGUAGE = 'zh_en'
_REQUEST_ID = re.compile(r'sr_[0-9a-f]{32}', re.ASCII)
_CLIENT_ID = re.compile(r'[A-Za-z0-9_-]{1,128}', re.ASCII)
_LOCAL_TIME = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}', re.ASCII)
_STAMP = "to_char({} AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')"
DETAILS = ('service_date', 'time_window', 'venue', 'customer_name', 'contact_phone', 'meeting_purpose',
           'counterpart', 'note')


class Unavailable(Exception):
    """503: storage unavailable; nothing about the request is disclosed."""


class CommitUnknown(Unavailable):
    """503 outcome unknown: reconcile with the original bytes / client_request_id."""


class Conflict(Exception):
    """409 conflict: same client_request_id, different original bytes."""


class NotFound(Exception):
    """404: not found and not owned are indistinguishable."""


class FeatureDisabled(Exception):
    """404 feature_disabled: only new submissions (and non-terminal staff progress)."""


def enabled(environ=None) -> bool:
    return (os.environ if environ is None else environ).get(FLAG) == '1'


def _bilingual(value):
    if not isinstance(value, dict) or set(value) != {'text_en', 'text_zh'}:
        raise InvalidInput('policy text')
    for text in value.values():
        _text(text, 2000, nonblank=True)
    return {'text_en': value['text_en'], 'text_zh': value['text_zh']}


def _quote(value):
    if not isinstance(value, dict) or set(value) != {'amount_minor', 'currency', 'payment', 'instructions_en',
                                                     'instructions_zh'}:
        raise InvalidInput('quote')
    if type(value['amount_minor']) is not int or not 0 < value['amount_minor'] <= 100_000_000:
        raise InvalidInput('quote amount')
    if value['currency'] != 'CNY' or value['payment'] != 'outside_app':
        raise InvalidInput('quote payment')
    _text(value['instructions_en'], 500, nonblank=True)
    _text(value['instructions_zh'], 500, nonblank=True)
    return dict(value)


def _escort(value):
    if not isinstance(value, dict) or set(value) != {'escort_display_name', 'arrival'}:
        raise InvalidInput('escort')
    _text(value['escort_display_name'], 40, nonblank=True)
    arrival = value['arrival']
    if not isinstance(arrival, dict) or set(arrival) != {'local_time', 'place'}:
        raise InvalidInput('arrival')
    if not isinstance(arrival['local_time'], str) or not _LOCAL_TIME.fullmatch(arrival['local_time']):
        raise InvalidInput('arrival time')
    _text(arrival['place'], 200, nonblank=True)
    return {'escort_display_name': value['escort_display_name'],
            'arrival': {'local_time': arrival['local_time'], 'place': arrival['place']}}


def _identifier(value, pattern, error):
    if type(value) is not str or not pattern.fullmatch(value):
        raise error
    return value


def shared_with_escort(details) -> list[str]:
    out = ['customer_name', 'language', 'service_date', 'time_window', 'venue']
    if details['meeting_purpose']:
        out.append('meeting_purpose')
    if details['counterpart'] is not None:
        out.append('counterpart')
    out.append('contact_phone')
    return out


class Repository:
    def __init__(self, connect, scope, *, policy, flag=enabled):
        if not callable(connect) or type(scope) is not str or not scope or not callable(flag):
            raise Unavailable()
        if not isinstance(policy, dict) or set(policy) != {'cancellation_policy', 'refund_by'}:
            raise Unavailable()
        self.connect, self.scope, self.flag = connect, scope, flag
        self.policy = {k: _bilingual(v) for k, v in policy.items()}

    # -- transaction -------------------------------------------------------------
    @contextmanager
    def transaction(self, lock_key=None, *, writing=False):
        conn = None
        commit_started = False
        try:
            conn = self.connect()
            if conn.autocommit is not False or conn.info.transaction_status != 0:
                raise Unavailable()
            cur = conn.cursor()
            cur.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
            cur.execute("SET LOCAL lock_timeout = '5s'")
            cur.execute("SET LOCAL statement_timeout = '10s'")
            bind_runtime(cur, self.scope)
            if lock_key is not None:
                # Serializes concurrent duplicates of one client_request_id; the UNIQUE stays exact.
                cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                            (json.dumps(['service_request', self.scope, lock_key]),))
            yield cur
            commit_started = True
            conn.commit()
        except (InvalidInput, InvalidTransition, Conflict, NotFound, FeatureDisabled, Unavailable):
            raise
        except BaseException:
            if writing and commit_started:
                raise CommitUnknown() from None
            raise Unavailable() from None
        finally:
            if conn is not None:
                try:
                    if not commit_started:
                        conn.rollback()
                    conn.close()
                except BaseException:
                    logging.getLogger(__name__).warning('service request connection cleanup failed')

    # -- reads -------------------------------------------------------------------
    def _row(self, cur, where, value, *, lock=False):
        cur.execute('SELECT request_id,client_request_id,original_input,input_sha256,state,details,human_service,quote '
                    'FROM cj_service_request WHERE scope=%s AND ' + where + '=%s' + (' FOR UPDATE' if lock else ''),
                    (self.scope, value))
        row = cur.fetchone()
        if row is None:
            return None
        rid, cid, raw, digest, state, details, human, quote = row
        raw = bytes(raw)
        if sha256(raw).hexdigest() != digest:
            raise Unavailable()
        return dict(request_id=rid, client_request_id=cid, original=raw, state=state, details=details,
                    human_service=human, quote=quote)

    def _project(self, cur, row):
        cur.execute('SELECT seq,from_state,to_state,' + _STAMP.format('at') + ',actor_kind '
                    'FROM cj_service_request_history WHERE scope=%s AND request_id=%s ORDER BY seq',
                    (self.scope, row['request_id']))
        history = [{'seq': s, 'from': f, 'to': t, 'at': at, 'actor': {'kind': k}} for s, f, t, at, k in cur.fetchall()]
        details = {k: row['details'][k] for k in DETAILS}
        return {'request_id': row['request_id'], 'client_request_id': row['client_request_id'],
                'service_type': SERVICE_TYPE, 'state': row['state'], 'history': history, 'details': details,
                'shared_with_escort': shared_with_escort(details), 'human_service': row['human_service'],
                'quote': row['quote']}

    def get(self, request_id):
        rid = _identifier(request_id, _REQUEST_ID, NotFound())
        with self.transaction() as cur:
            row = self._row(cur, 'request_id', rid)
            if row is None:
                raise NotFound()
            return self._project(cur, row)

    def by_client_request_id(self, client_request_id):
        cid = _identifier(client_request_id, _CLIENT_ID, InvalidInput('client_request_id'))
        with self.transaction() as cur:
            row = self._row(cur, 'client_request_id', cid)
            return None if row is None else self._project(cur, row)

    def list_own(self):
        with self.transaction() as cur:
            cur.execute('SELECT request_id FROM cj_service_request WHERE scope=%s ORDER BY submitted_at DESC,request_id',
                        (self.scope,))
            ids = [r[0] for r in cur.fetchall()]
            return [self._project(cur, self._row(cur, 'request_id', rid)) for rid in ids]

    # -- submit ------------------------------------------------------------------
    def submit(self, original: bytes):
        submission = parse_submission(original)
        cid = submission.client_request_id
        with self.transaction(cid, writing=True) as cur:
            old = self._row(cur, 'client_request_id', cid)
            if old is not None:
                if old['original'] != submission.original:
                    raise Conflict()
                return self._project(cur, old)
            # Only new submissions are gated; replays/reads above still answer.
            if not self.flag():
                raise FeatureDisabled()
            return self._insert(cur, submission)

    def _insert(self, cur, submission: Submission):
        f = submission.fields
        rid = 'sr_' + secrets.token_hex(16)
        details = {k: f[k] for k in DETAILS}
        human = {'provided_by_human': True, 'escort_display_name': None, 'arrival': None, **self.policy}
        cur.execute('INSERT INTO cj_service_request(scope,request_id,client_request_id,original_input,input_sha256,'
                    "state,details,human_service) VALUES(%s,%s,%s,%s,%s,'submitted',%s::jsonb,%s::jsonb)",
                    (self.scope, rid, submission.client_request_id, submission.original,
                     sha256(submission.original).hexdigest(), json.dumps(details), json.dumps(human)))
        consent = json.dumps(f['consents'], sort_keys=True, separators=(',', ':'))
        cur.execute('INSERT INTO cj_service_request_history(scope,request_id,seq,from_state,to_state,actor_kind,'
                    "evidence_kind,evidence_body) VALUES(%s,%s,1,NULL,'user_confirmed','user','consent',%s),"
                    "(%s,%s,2,'user_confirmed','submitted','system','receipt',%s)",
                    (self.scope, rid, consent, self.scope, rid, sha256(submission.original).hexdigest()))
        self._notify(cur, rid, 2, 'submitted', human)
        return self._project(cur, self._row(cur, 'request_id', rid))

    # -- transitions -------------------------------------------------------------
    def transition(self, request_id, target, *, actor, evidence_kind, evidence_body, staff_ref=None,
                   quote=None, escort=None):
        rid = _identifier(request_id, _REQUEST_ID, NotFound())
        if actor == 'staff':
            if type(staff_ref) is not str or not 1 <= len(staff_ref) <= 128:
                raise InvalidInput('staff_ref')
        elif staff_ref is not None:
            raise InvalidInput('staff_ref')
        _text(evidence_body, 2000, nonblank=True)
        quote = _quote(quote) if target == 'quoted' else quote
        escort = _escort(escort) if target == 'arranged' else escort
        if target != 'quoted' and quote is not None or target != 'arranged' and escort is not None:
            raise InvalidInput('unexpected payload')
        if target not in TERMINAL and not self.flag():
            # Switched off: existing requests may still be cancelled or brought to an end.
            raise FeatureDisabled()
        with self.transaction(writing=True) as cur:
            row = self._row(cur, 'request_id', rid, lock=True)
            if row is None:
                raise NotFound()
            return self._advance(cur, row, target, actor, evidence_kind, evidence_body, staff_ref, quote, escort)

    def _advance(self, cur, row, target, actor, evidence_kind, evidence_body, staff_ref, quote, escort):
        check_transition(row['state'], target, actor, evidence_kind)
        rid = row['request_id']
        cur.execute('SELECT coalesce(max(seq),0)+1 FROM cj_service_request_history WHERE scope=%s AND request_id=%s',
                    (self.scope, rid))
        seq = cur.fetchone()[0]
        cur.execute('INSERT INTO cj_service_request_history(scope,request_id,seq,from_state,to_state,actor_kind,'
                    'staff_ref,evidence_kind,evidence_body) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (self.scope, rid, seq, row['state'], target, actor, staff_ref, evidence_kind, evidence_body))
        human = row['human_service']
        if escort is not None:
            human = {**human, **escort}
        cur.execute('UPDATE cj_service_request SET state=%s,human_service=%s::jsonb,quote=coalesce(%s::jsonb,quote),'
                    "arranged_at=CASE WHEN %s='arranged' THEN coalesce(arranged_at,clock_timestamp()) ELSE arranged_at END,"
                    'first_terminal_at=CASE WHEN %s THEN coalesce(first_terminal_at,clock_timestamp()) '
                    'ELSE first_terminal_at END WHERE scope=%s AND request_id=%s',
                    (target, json.dumps(human), None if quote is None else json.dumps(quote), target,
                     target in TERMINAL, self.scope, rid))
        if cur.rowcount != 1:
            raise Unavailable()
        self._notify(cur, rid, seq, target, human)
        return self._project(cur, self._row(cur, 'request_id', rid))

    # -- server-initiated messages (#1770, ADR-0009 section 3) -------------------
    def _notify(self, cur, rid, seq, to_state, human):
        """Same transaction as the state change: committed together or not at all.

        Switched off, no service conversation is created; an existing one still receives the
        message for a request being brought to an end ("existing requests can finish").
        """
        from cj_message.service_session import emit
        return emit(cur, self.scope, rid, seq, to_state, human, create=self.flag())

    def redeliver(self, request_id, seq):
        """Idempotent retry for one recorded state change; a delivered change writes nothing."""
        rid = _identifier(request_id, _REQUEST_ID, NotFound())
        if type(seq) is not int or seq < 2:
            raise InvalidInput('seq')
        with self.transaction(writing=True) as cur:
            row = self._row(cur, 'request_id', rid, lock=True)
            if row is None:
                raise NotFound()
            cur.execute('SELECT to_state FROM cj_service_request_history WHERE scope=%s AND request_id=%s AND seq=%s',
                        (self.scope, rid, seq))
            found = cur.fetchone()
            if found is None:
                raise NotFound()
            return self._notify(cur, rid, seq, found[0], row['human_service'])

    def cancel(self, request_id, client_request_id):
        """User cancel (contract section 6): idempotent, allowed while switched off."""
        rid = _identifier(request_id, _REQUEST_ID, NotFound())
        cid = _identifier(client_request_id, _CLIENT_ID, InvalidInput('client_request_id'))
        with self.transaction(writing=True) as cur:
            row = self._row(cur, 'request_id', rid, lock=True)
            if row is None or row['client_request_id'] != cid:
                raise NotFound()
            if row['state'] == 'user_cancelled':
                return self._project(cur, row)
            return self._advance(cur, row, 'user_cancelled', 'user', EVIDENCE['user_cancelled'],
                                 'user_request', None, None, None)

    # -- escort view audit -------------------------------------------------------
    def escort_view(self, request_id, viewer_ref):
        """Shared fields for the escort inside the window; every view is audited."""
        rid = _identifier(request_id, _REQUEST_ID, NotFound())
        if type(viewer_ref) is not str or not 1 <= len(viewer_ref) <= 128:
            raise InvalidInput('viewer_ref')
        with self.transaction(writing=True) as cur:
            cur.execute('SELECT details FROM cj_service_request WHERE scope=%s AND request_id=%s AND arranged_at IS NOT NULL '
                        "AND (first_terminal_at IS NULL OR clock_timestamp() < first_terminal_at + interval '24 hours')",
                        (self.scope, rid))
            found = cur.fetchone()
            if found is None:
                raise NotFound()
            details = found[0]
            fields = shared_with_escort(details)
            cur.execute('INSERT INTO cj_service_request_view(scope,request_id,viewer_ref,fields) VALUES(%s,%s,%s,%s::jsonb)',
                        (self.scope, rid, viewer_ref, json.dumps(fields)))
            return {k: (LANGUAGE if k == 'language' else details[k]) for k in fields}

    # -- retention (PIPIA section 9) ---------------------------------------------
    def purge_expired(self, cleanup_connect):
        """Erase completion_summary bodies after 90 days and whole requests after 12 months.

        Cutoffs come from the database clock and the first terminal time, never the caller.
        Bodies are cleared as the runtime; whole requests are deleted through cleanup_connect
        (cj_local_cleanup; the runtime holds no DELETE grant). No scheduler is started here.
        """
        with self.transaction(writing=True) as cur:
            cur.execute("UPDATE cj_service_request_history h SET evidence_body=NULL WHERE h.scope=%s "
                        "AND h.evidence_kind='completion_summary' AND h.evidence_body IS NOT NULL AND EXISTS("
                        'SELECT 1 FROM cj_service_request r WHERE r.scope=h.scope AND r.request_id=h.request_id '
                        "AND r.first_terminal_at < clock_timestamp() - interval '90 days')", (self.scope,))
            summaries = cur.rowcount
        conn = None
        try:
            conn = cleanup_connect()
            cur = conn.cursor()
            cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),"
                        "set_config('cj.cleanup_purpose','service_request_retention',true)", (self.scope,))
            cur.execute("DELETE FROM cj_service_request WHERE scope=%s AND first_terminal_at IS NOT NULL "
                        "AND first_terminal_at < clock_timestamp() - interval '12 months'", (self.scope,))
            deleted = cur.rowcount
            conn.commit()
        except BaseException:
            raise Unavailable() from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except BaseException:
                    pass
        return {'summaries_erased': summaries, 'requests_deleted': deleted}
