"""Injected fresh DB-API connections. Scope is server-resolved, never request data."""
from contextlib import contextmanager
from dataclasses import asdict
import json
import logging
from .domain import Action, Receipt, Conflict, InvalidInput, Unavailable, ReferenceUnavailable, CommitUnknown, SourceReference, identifier


class Repository:
    def __init__(self, connect, scope, guard, *, sources=None, token=None, principal=None):
        if connect is None or not callable(guard) or type(scope) is not str or not scope:
            raise Unavailable()
        self.connect, self.scope, self.guard = connect, scope, guard
        self.sources, self.token, self.principal = sources, token, principal
        self.publication = None

    @contextmanager
    def transaction(self, aid, *, writing=False, before_commit=None):
        conn = None
        accepted = committed = commit_started = False
        try:
            conn = self.connect()
            if (conn.autocommit is not False or conn.closed is not False
                    or conn.info.transaction_status != 0): raise Unavailable()
            accepted = True
            cur = conn.cursor()
            cur.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
            cur.execute("SET LOCAL lock_timeout = '5s'")
            cur.execute("SET LOCAL statement_timeout = '10s'")
            # Collisions only serialize unrelated actions; primary key remains exact.
            cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                        (json.dumps([self.scope, 'submit', aid]),))
            self.guard('transaction')
            yield cur
            self.guard('commit')
            if before_commit is not None: before_commit()
            self.guard('source_return')
            commit_started = True
            conn.commit()
            committed = True
            self.guard('return')
        except BaseException as exc:
            if writing and commit_started:
                raise CommitUnknown() from None
            if isinstance(exc, (InvalidInput, Conflict, Unavailable)):
                raise
            raise Unavailable() from None
        finally:
            if conn is not None and accepted:
                # Never retry an uncertain commit or claim rollback undid it.
                if accepted and not commit_started:
                    try: conn.rollback()
                    except BaseException: self._cleanup_warning()
                try: conn.close()
                except BaseException:
                    self._cleanup_warning()
                    # An interrupt during successful close still withholds publication.
                    if committed and writing: raise CommitUnknown() from None
                    if committed: raise Unavailable() from None

    @staticmethod
    def _cleanup_warning():
        try: logging.getLogger(__name__).warning("feedback connection cleanup failed")
        except BaseException: pass

    def _find(self, cur, aid):
        cur.execute("SELECT original_input,input_sha256,source_reference,to_char(submitted_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') FROM cj_feedback_action WHERE scope=%s AND operation='submit' AND action_id=%s", (self.scope, aid))
        row = cur.fetchone()
        if row is None: return None
        raw, digest, source, stamp = row
        action = Action(bytes(raw))
        if action.action_id != aid or action.digest != digest: raise Unavailable()
        if source is not None:
            try: source = SourceReference(**source)
            except (TypeError, ValueError): raise Unavailable() from None
        refs = {r['kind']:r['id'] for r in action.fields()['references']}
        if bool(refs) != (source is not None): raise Unavailable()
        if source is not None and (refs['message'] != source.message_id or ('run' in refs and refs['run'] != source.run_id)):
            raise Unavailable()
        return action.original, Receipt(aid, digest, stamp, source=source)

    def submit(self, action):
        if type(action) is not Action: raise InvalidInput()
        fields = action.fields()
        source = None
        def verify_source():
            if source is not None:
                self.sources.verify(self.token, self.principal, self.scope, fields['references'], source)
        with self.transaction(action.action_id, writing=True, before_commit=verify_source) as cur:
            old = self._find(cur, action.action_id)
            if old:
                if old[0] != action.original: raise Conflict()
                return old[1]
            if fields['references']:
                from .sources import Sources
                if type(self.sources) is not Sources: raise ReferenceUnavailable()
                source = self.sources.read(self.token, self.principal, self.scope, fields['references'])
            cur.execute("INSERT INTO cj_feedback_action(scope,operation,action_id,original_input,input_sha256,source_reference) VALUES (%s,'submit',%s,%s,%s,%s::jsonb)",
                        (self.scope, action.action_id, action.original, action.digest, json.dumps(asdict(source)) if source else None))
            if source is not None: self.publication = (fields['references'], source)
            return self._find(cur, action.action_id)[1]

    def query_action(self, action_id):
        aid = identifier(action_id)
        with self.transaction(aid) as cur:
            row = self._find(cur, aid)
            return row[1] if row else None

    def finish_projection(self, encoded):
        if self.publication is None: return encoded
        refs, source = self.publication
        return self.sources.publish(self.token, self.principal, self.scope, refs, source, encoded)
