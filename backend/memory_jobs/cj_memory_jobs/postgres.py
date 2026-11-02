"""C-owned SQL on an already-bound canonical MEMORY transaction.

No identity resolver, alternate AUTH, role switch, model call or automatic retry.
Schema/registry/cleanup/runtime integration remain unactivated until their PR.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from .codec import Conflict, Unavailable, decode_v2, encode_v2, job_identity
from .consent import VERSION


def encode(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':')).encode('ascii')


def stream_key(source, mode):
    value = asdict(source)
    value['cursor'].pop('after')
    value['cursor'].pop('through')
    return sha256(encode(dict(source=value, mode=mode))).hexdigest()


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    attempt_id: str
    state: str
    processed_through: int
    input_sha256: str

    def encode(self):
        return encode(dict(version='MEMORY-JOBS@1', **asdict(self)))


class Transaction:
    def __init__(self, memory_transaction):
        self.memory = memory_transaction
        self.cur, self.scope = memory_transaction.cur, memory_transaction.scope
        self.scope_digest = sha256(self.scope.encode('utf-8')).hexdigest()

    def require_live(self, *, initialize=False):
        if initialize:
            self.cur.execute('INSERT INTO cj_memory_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',
                             (self.scope,))
        self.epoch = self.memory.lock_scope()
        if initialize:
            self.cur.execute('INSERT INTO cj_memory_history_fence(scope_digest) VALUES(%s) ON CONFLICT DO NOTHING',
                             (self.scope_digest,))
        self.cur.execute('SELECT erased FROM cj_memory_history_fence WHERE scope_digest=%s FOR UPDATE',
                         (self.scope_digest,))
        if self.cur.fetchone() != (False,):
            raise Unavailable('history unavailable')

    def action(self, action_id):
        self.cur.execute('SELECT original_input,receipt FROM cj_memory_history_action '
                         'WHERE scope=%s AND action_id=%s', (self.scope, action_id))
        row = self.cur.fetchone()
        return (bytes(row[0]), bytes(row[1])) if row else None

    def consent(self, conversation_id):
        self.cur.execute('SELECT generation,message_epoch,enabled,source_version,withdrawal_epoch '
                         'FROM cj_memory_history_consent WHERE scope=%s AND conversation_id=%s',
                         (self.scope, conversation_id))
        return self.cur.fetchone()

    def settings(self, conversation_id, head):
        self.cur.execute('SELECT active FROM cj_memory_scope WHERE scope=%s FOR SHARE',(self.scope,))
        scope = self.cur.fetchone()
        if scope == (False,):
            raise Unavailable('history unavailable')
        self.cur.execute('SELECT erased FROM cj_memory_history_fence WHERE scope_digest=%s',(self.scope_digest,))
        if self.cur.fetchone() == (True,):
            raise Unavailable('history unavailable')
        current = self.consent(conversation_id) if scope is not None else None
        enabled = (current is not None and current[:3] == (head.generation,head.epoch,True))
        return encode(dict(version=VERSION,conversation_id=conversation_id,
            generation=head.generation,epoch=head.epoch,enabled=enabled,
            source_version=current[3] if current else 0,
            withdrawal_epoch=current[4] if current else 1))

    def apply_consent(self, action, head):
        old = self.action(action.action_id)
        if old is not None:
            if old[0] != action.raw:
                raise Conflict('original history action differs')
            return old[1]
        if (head.generation, head.epoch) != (action.expected_generation, action.expected_epoch):
            raise Conflict('conversation generation or epoch changed')
        current = self.consent(action.conversation_id)
        version = current[3] if current else 0
        if version != action.expected_source_version or version == 2**63-1:
            raise Conflict('history source version changed')
        withdrawal = current[4] if current else 1
        version += 1
        enabled = action.operation == 'enable'
        self.cur.execute('''INSERT INTO cj_memory_history_consent
            (scope,conversation_id,generation,message_epoch,enabled,source_version,withdrawal_epoch)
            VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(scope,conversation_id) DO UPDATE SET
            generation=EXCLUDED.generation,message_epoch=EXCLUDED.message_epoch,
            enabled=EXCLUDED.enabled,source_version=EXCLUDED.source_version,
            withdrawal_epoch=EXCLUDED.withdrawal_epoch''',
            (self.scope,action.conversation_id,head.generation,head.epoch,enabled,version,withdrawal))
        receipt = encode(dict(version=VERSION, action_id=action.action_id,
            conversation_id=action.conversation_id,generation=head.generation,
            epoch=head.epoch,enabled=enabled,source_version=version,withdrawal_epoch=withdrawal,
            input_sha256=sha256(action.raw).hexdigest()))
        self.cur.execute('INSERT INTO cj_memory_history_action VALUES(%s,%s,%s,%s)',
                         (self.scope,action.action_id,action.raw,receipt))
        return receipt

    def require_source(self, query):
        current = self.consent(query.conversation_id)
        if current != (query.generation,query.epoch,True,query.source_version,query.withdrawal_epoch):
            raise Unavailable('history source unavailable')

    def current_unresolved(self):
        """Original work still able to publish at this locked Memory basis.

        Old source versions remain queryable history but cannot block another
        explicitly enabled source once their grant has been withdrawn.
        """
        self.cur.execute('''SELECT j.job_id,j.attempt_id FROM cj_memory_history_job j
            JOIN cj_memory_history_consent c ON c.scope=j.scope AND c.enabled
             AND c.conversation_id=convert_from(j.batch,'UTF8')::jsonb#>>'{source,cursor,conversation_id}'
             AND c.generation=convert_from(j.batch,'UTF8')::jsonb#>>'{source,cursor,generation}'
             AND c.message_epoch=(convert_from(j.batch,'UTF8')::jsonb#>>'{source,cursor,epoch}')::bigint
             AND c.source_version=(convert_from(j.batch,'UTF8')::jsonb#>>'{source,source_version}')::bigint
             AND c.withdrawal_epoch=(convert_from(j.batch,'UTF8')::jsonb#>>'{source,withdrawal_epoch}')::bigint
            WHERE j.scope=%s AND j.memory_epoch=%s AND j.state IN ('pending','inflight','unknown')
            ORDER BY j.job_id''',(self.scope,self.epoch))
        return tuple(self.job(jid,attempt) for jid,attempt in self.cur.fetchall())

    def _job(self, row):
        if row is None:
            return None
        job_id, attempt_id, source_key, stored_stream, original, batch, state, processed, candidate, memory_epoch = row
        job_identity(job_id); job_identity(attempt_id)
        batch, original = bytes(batch), bytes(original)
        source, rows, mode = decode_v2(batch)
        if (source.cursor.scope != self.scope or sha256(batch).hexdigest() != source_key
                or stream_key(source,mode) != stored_stream):
            raise Unavailable('stored history binding unavailable')
        if ((state == 'completed') != (candidate is not None)
                or processed != (source.cursor.through if state == 'completed' else source.cursor.after)):
            raise Unavailable('stored history progress unavailable')
        status = JobStatus(job_id,attempt_id,state,processed,sha256(original).hexdigest())
        return status, original, batch, source, rows, mode, bytes(candidate) if candidate is not None else None, memory_epoch

    def job(self, job_id, attempt_id):
        self.cur.execute('''SELECT job_id,attempt_id,source_key,stream_key,original_input,batch,state,processed,candidate,memory_epoch
            FROM cj_memory_history_job WHERE scope=%s AND job_id=%s''', (self.scope,job_id))
        row = self._job(self.cur.fetchone())
        if row is None:
            raise Unavailable('original job unavailable; absence does not authorize resend')
        if row[0].attempt_id != attempt_id:
            raise Conflict('original history attempt differs')
        return row

    def enqueue(self, source, rows, mode, job_id, attempt_id, original):
        batch = encode_v2(source, rows, mode)
        key = sha256(batch).hexdigest()
        self.cur.execute('''SELECT job_id,attempt_id,source_key,stream_key,original_input,batch,state,processed,candidate,memory_epoch
            FROM cj_memory_history_job WHERE scope=%s AND (job_id=%s OR attempt_id=%s OR source_key=%s)''',
            (self.scope,job_id,attempt_id,key))
        old = self.cur.fetchall()
        if old:
            if len(old) != 1:
                raise Conflict('history task identity conflict')
            stored = self._job(old[0])
            if (stored[0].job_id,stored[0].attempt_id,stored[1],stored[2]) != (job_id,attempt_id,original,batch):
                raise Conflict('original history task differs')
            return stored[0]
        stream = stream_key(source,mode)
        self.cur.execute('SELECT processed FROM cj_memory_history_cursor WHERE scope=%s AND stream_key=%s',
                         (self.scope,stream))
        previous = self.cur.fetchone()
        if source.cursor.after != (previous[0] if previous else 0):
            raise Conflict('history processing gap or overlap')
        self.cur.execute('SELECT 1 FROM cj_memory_history_job WHERE scope=%s AND stream_key=%s '
                         "AND state IN ('pending','inflight','unknown')", (self.scope,stream))
        if self.cur.fetchone() is not None:
            raise Conflict('original history interval is unresolved')
        self.cur.execute('''INSERT INTO cj_memory_history_job
            (scope,job_id,attempt_id,source_key,stream_key,original_input,batch,memory_epoch,state,processed)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s)''',
            (self.scope,job_id,attempt_id,key,stream,original,batch,self.epoch,source.cursor.after))
        return self.job(job_id,attempt_id)[0]

    def transition(self, job_id, attempt_id, target, *, candidate=None):
        status, _, _, source, _, mode, old_candidate, memory_epoch = self.job(job_id,attempt_id)
        state = status.state
        if target in ('inflight','completed') and self.epoch != memory_epoch:
            raise Conflict('original Memory basis changed')
        if target == 'inflight' and state != 'pending':
            raise Conflict('original attempt already started; reconcile only')
        if target == 'unknown' and state not in ('inflight','unknown'):
            raise Conflict('no original in-flight attempt')
        if target == 'cancelled' and state not in ('pending','inflight','unknown','cancelled'):
            raise Conflict('original history result is terminal')
        if target == 'failed' and state not in ('inflight','failed'):
            raise Conflict('no original failed attempt')
        if target == 'completed':
            if state == 'completed':
                if candidate != old_candidate:
                    raise Conflict('original history output differs')
                return status
            if state not in ('inflight','unknown'):
                raise Conflict('original history attempt not running')
            if type(candidate) is not bytes or not 1 <= len(candidate) <= 16384:
                raise ValueError('bounded original candidate bytes required')
            candidate.decode('utf-8')
        elif target not in ('inflight','unknown','cancelled','failed'):
            raise ValueError('unsupported history transition')
        processed = source.cursor.through if target == 'completed' else source.cursor.after
        self.cur.execute('UPDATE cj_memory_history_job SET state=%s,processed=%s,candidate=%s '
                         'WHERE scope=%s AND job_id=%s',
                         (target,processed,candidate,self.scope,job_id))
        if target == 'completed':
            self.cur.execute('''INSERT INTO cj_memory_history_cursor VALUES(%s,%s,%s)
                ON CONFLICT(scope,stream_key) DO UPDATE SET processed=EXCLUDED.processed''',
                (self.scope,stream_key(source,mode),processed))
        return self.job(job_id,attempt_id)[0]
