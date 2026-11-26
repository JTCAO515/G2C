"""Minimal operations console for SERVICE-REQUEST@1 (#1771, PIPIA sections 5, 7, 9).

Staff identity: the App's own session credential (the host's existing admission checker)
resolves a verified issuer/subject; only a pair on the server-configured roster is staff.
The roster maps it to an internal staff_ref that goes to the server-only audit and history,
never to customer-facing fields (ADR-0009 section 3). No password or credential is stored.

Database identities:
  * ops_connect   -> cj_ops_console (0058): reads across owners, note clearing, audit append.
  * runtime_connect -> cj_m1_runtime: every state change, through Repository.transition under
    the target owner's scope, so check_transition and CJ_SERVICE_REQUEST_ENABLED behave exactly
    as for #1769.
Every staff action writes one audit row (list, view, clear_note, each transition) before it
acts; if the audit cannot be written the action does not run. The state history row
(with staff_ref) is the record of the outcome.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import logging
import os
from pathlib import Path

from .contract import EVIDENCE, TERMINAL, InvalidInput
from .store import (_REQUEST_ID, _STAMP, DETAILS, NotFound, Repository, Unavailable, _identifier, enabled)

FLAG = 'CJ_OPS_CONSOLE_ENABLED'
ROSTER = 'CJ_OPS_STAFF_ROSTER_FILE'
STAFF_TARGETS = frozenset(t for t in EVIDENCE if t not in ('user_confirmed', 'submitted'))
_STAFF_REF_MAX = 128


def console_enabled(environ=None) -> bool:
    return (os.environ if environ is None else environ).get(FLAG) == '1'


class NotStaff(Exception):
    """403: verified App session whose subject is not on the staff roster."""


class Roster:
    """Server-side staff list: verified (issuer, subject) -> internal staff_ref.

    Loaded only from host configuration (a JSON file outside the repository in real use;
    tests use synthetic values). Duplicate subjects or staff refs refuse the whole roster.
    """

    def __init__(self, entries):
        mapping, refs = {}, set()
        for entry in entries:
            if not isinstance(entry, Mapping) or set(entry) != {'issuer', 'subject', 'staff_ref'}:
                raise ValueError('roster entry')
            issuer, subject, ref = entry['issuer'], entry['subject'], entry['staff_ref']
            for value in (issuer, subject, ref):
                if type(value) is not str or not value or len(value) > _STAFF_REF_MAX or value != value.strip():
                    raise ValueError('roster value')
            if (issuer, subject) in mapping or ref in refs:
                raise ValueError('roster duplicate')
            mapping[(issuer, subject)] = ref
            refs.add(ref)
        self._mapping = mapping

    @classmethod
    def from_file(cls, path):
        def no_duplicates(pairs):
            keys = [k for k, _ in pairs]
            if len(keys) != len(set(keys)):
                raise ValueError('duplicate key')
            return dict(pairs)
        value = json.loads(Path(path).read_text('utf-8'), object_pairs_hook=no_duplicates)
        if not isinstance(value, dict) or set(value) != {'staff'} or not isinstance(value['staff'], list):
            raise ValueError('roster file')
        return cls(value['staff'])

    @classmethod
    def from_environment(cls, environ=None):
        path = (os.environ if environ is None else environ).get(ROSTER)
        if not path:
            return cls(())
        return cls.from_file(path)

    def staff_ref(self, principal):
        ref = self._mapping.get((getattr(principal, 'issuer', None), getattr(principal, 'subject', None)))
        if ref is None:
            raise NotStaff()
        return ref

    def __len__(self):
        return len(self._mapping)


class OpsConsole:
    def __init__(self, ops_connect, runtime_connect, *, policy, flag=enabled):
        if not callable(ops_connect) or not callable(runtime_connect) or not callable(flag):
            raise Unavailable()
        self.ops_connect, self.runtime_connect, self.flag = ops_connect, runtime_connect, flag
        Repository(runtime_connect, 'validate', policy=policy, flag=flag)  # policy shape check only
        self.policy = policy

    # -- connection --------------------------------------------------------------
    def _ops(self, work):
        conn = None
        try:
            conn = self.ops_connect()
            if conn.autocommit is not False or conn.info.transaction_status != 0:
                raise Unavailable()
            cur = conn.cursor()
            cur.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
            cur.execute("SET LOCAL lock_timeout = '5s'")
            cur.execute("SET LOCAL statement_timeout = '10s'")
            result = work(cur)
            conn.commit()
            return result
        except (InvalidInput, NotFound, Unavailable):
            raise
        except BaseException:
            raise Unavailable() from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except BaseException:
                    logging.getLogger(__name__).warning('ops console connection cleanup failed')

    @staticmethod
    def _audit(cur, staff_ref, action, scope=None, request_id=None):
        if type(staff_ref) is not str or not 1 <= len(staff_ref) <= _STAFF_REF_MAX:
            raise InvalidInput('staff_ref')
        cur.execute('INSERT INTO cj_service_request_staff_audit(staff_ref,action,scope,request_id) VALUES(%s,%s,%s,%s)',
                    (staff_ref, action, scope, request_id))

    @staticmethod
    def _locate(cur, rid):
        cur.execute('SELECT scope FROM cj_service_request WHERE request_id=%s', (rid,))
        rows = cur.fetchall()
        if len(rows) != 1:
            raise NotFound()
        return rows[0][0]

    # -- reads -------------------------------------------------------------------
    def list_requests(self, staff_ref):
        def work(cur):
            self._audit(cur, staff_ref, 'list')
            cur.execute('SELECT request_id,state,' + _STAMP.format('submitted_at') + ',details->>\'service_date\','
                        "details->>'time_window' FROM cj_service_request ORDER BY submitted_at DESC,request_id")
            return [{'request_id': r, 'state': s, 'submitted_at': at, 'service_date': d, 'time_window': w}
                    for r, s, at, d, w in cur.fetchall()]
        return self._ops(work)

    def detail(self, staff_ref, request_id):
        rid = _identifier(request_id, _REQUEST_ID, NotFound())

        def work(cur):
            scope = self._locate(cur, rid)
            self._audit(cur, staff_ref, 'view', scope, rid)
            return self._detail(cur, scope, rid)
        return self._ops(work)

    @staticmethod
    def _detail(cur, scope, rid):
        cur.execute('SELECT state,details,human_service,quote,' + _STAMP.format('submitted_at') + ','
                    + _STAMP.format('note_cleared_at') + ' FROM cj_service_request WHERE scope=%s AND request_id=%s',
                    (scope, rid))
        state, details, human, quote, submitted_at, cleared = cur.fetchone()
        cur.execute('SELECT seq,from_state,to_state,' + _STAMP.format('at') + ',actor_kind,staff_ref,evidence_kind,'
                    'evidence_body FROM cj_service_request_history WHERE scope=%s AND request_id=%s ORDER BY seq',
                    (scope, rid))
        history = [{'seq': s, 'from': f, 'to': t, 'at': at, 'actor': {'kind': k, 'staff_ref': ref},
                    'evidence': {'kind': ek, 'body': body}} for s, f, t, at, k, ref, ek, body in cur.fetchall()]
        return {'request_id': rid, 'state': state, 'submitted_at': submitted_at, 'note_cleared_at': cleared,
                'details': {k: details.get(k) for k in DETAILS}, 'human_service': human, 'quote': quote,
                'history': history, 'staff_targets': sorted(_next_targets(state))}

    # -- actions -----------------------------------------------------------------
    def advance(self, staff_ref, request_id, target, evidence_body, *, quote=None, escort=None):
        """One staff state change: audit first (ops role), then the #1769 repository as runtime."""
        rid = _identifier(request_id, _REQUEST_ID, NotFound())
        if target not in STAFF_TARGETS:
            raise InvalidInput('target')

        def audit(cur):
            scope = self._locate(cur, rid)
            self._audit(cur, staff_ref, target, scope, rid)
            return scope
        scope = self._ops(audit)
        repo = Repository(self.runtime_connect, scope, policy=self.policy, flag=self.flag)
        repo.transition(rid, target, actor='staff', staff_ref=staff_ref, evidence_kind=EVIDENCE[target],
                        evidence_body=evidence_body, quote=quote, escort=escort)
        return self._ops(lambda cur: self._detail(cur, scope, rid))

    def clear_note(self, staff_ref, request_id):
        """PIPIA 7 misreceipt: erase the note (and its copy in the stored original bytes); audited."""
        rid = _identifier(request_id, _REQUEST_ID, NotFound())

        def work(cur):
            scope = self._locate(cur, rid)
            cur.execute('SELECT original_input,details FROM cj_service_request WHERE scope=%s AND request_id=%s '
                        'AND note_cleared_at IS NULL FOR UPDATE', (scope, rid))
            row = cur.fetchone()
            if row is None or not isinstance(row[1].get('note'), str):
                raise InvalidInput('no note to clear')
            original = json.loads(bytes(row[0]).decode('utf-8'))
            original['note'] = None
            redacted = json.dumps(original, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            self._audit(cur, staff_ref, 'clear_note', scope, rid)
            cur.execute("UPDATE cj_service_request SET details=details||'{\"note\":null}'::jsonb,original_input=%s,"
                        'note_cleared_at=clock_timestamp() WHERE scope=%s AND request_id=%s', (redacted, scope, rid))
            if cur.rowcount != 1:
                raise Unavailable()
            return self._detail(cur, scope, rid)
        return self._ops(work)

    # -- retention (PIPIA section 9, 统筹 2026-11-26) -----------------------------
    @staticmethod
    def purge_delinked_audit(cleanup_connect):
        """De-linked audit rows (after account erasure) end 12 months after the action."""
        conn = None
        try:
            conn = cleanup_connect()
            cur = conn.cursor()
            cur.execute("SELECT set_config('cj.cleanup_purpose','service_staff_audit_retention',true)")
            cur.execute("DELETE FROM cj_service_request_staff_audit WHERE request_id IS NULL "
                        "AND at < clock_timestamp() - interval '12 months'")
            deleted = cur.rowcount
            conn.commit()
            return deleted
        except BaseException:
            raise Unavailable() from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except BaseException:
                    pass



def _next_targets(state):
    from .contract import TRANSITIONS
    return {t for t in TRANSITIONS.get(state, ()) if t in STAFF_TARGETS}
