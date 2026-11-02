"""Publication additions on the original held C/MEMORY transaction; no dispatch."""
from hashlib import sha256
import json

from .candidate import CandidateAction
from .codec import Conflict, Unavailable
from .postgres import Transaction, encode
from .extraction import parse_output
from .publication import build_command,publish_command
from cj_memory.domain import InvalidInput as MemoryInvalidInput,strict_object


class PublicationTransaction(Transaction):
    def output(self,job_id,attempt_id):
        row=self.job(job_id,attempt_id)
        self.cur.execute('SELECT result_bytes FROM cj_memory_history_job WHERE scope=%s AND job_id=%s',
                         (self.scope,job_id))
        value=self.cur.fetchone()[0]
        return row,bytes(value) if value is not None else None

    def checkpoint_output(self,job_id,attempt_id,raw):
        if type(raw) is not bytes or not 0<len(raw)<=16384:
            raise ValueError('bounded original model output bytes required')
        row,old=self.output(job_id,attempt_id)
        if old is not None:
            if old!=raw:raise Conflict('original model output differs')
            return old
        if row[0].state not in ('inflight','unknown') or row[7]!=self.epoch:
            raise Conflict('original extraction attempt or Memory basis changed')
        self.cur.execute('UPDATE cj_memory_history_job SET result_bytes=%s WHERE scope=%s AND job_id=%s',
                         (raw,self.scope,job_id))
        return raw

    def origin(self,command,job_id,attempt_id,messages,evidence):
        by_id={m.receipt.message_id:m.receipt for m in messages}
        refs=[dict(conversation_id=by_id[e.message_id].conversation_id,
                   generation=by_id[e.message_id].generation,sequence=by_id[e.message_id].sequence,
                   message_id=e.message_id,input_sha256=by_id[e.message_id].input_sha256) for e in evidence]
        refs.sort(key=lambda r:(r['conversation_id'],r['generation'],r['sequence'],r['message_id'],r['input_sha256']))
        self.cur.execute('''INSERT INTO cj_memory_history_origin
            (scope,source_id,item_id,job_id,attempt_id,origin_refs) VALUES(%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT(scope,source_id) DO NOTHING''',
            (self.scope,command.source_id,command.item_id,job_id,attempt_id,json.dumps(refs)))
        self.cur.execute('SELECT item_id,job_id,attempt_id,origin_refs FROM cj_memory_history_origin '
                         'WHERE scope=%s AND source_id=%s',(self.scope,command.source_id))
        old=self.cur.fetchone()
        # A replay from another authorized job may share the immutable logical
        # source, but it cannot change the original item/evidence association.
        if old is None or old[0]!=command.item_id or old[3]!=refs:
            raise Conflict('original source origin differs')

    def decision(self,action_id):
        self.cur.execute('SELECT original_input,receipt,candidate_id FROM cj_memory_history_candidate_action '
                         'WHERE scope=%s AND action_id=%s',(self.scope,action_id))
        row=self.cur.fetchone()
        if row is None:return None
        original,receipt=bytes(row[0]),bytes(row[1])
        action=CandidateAction.parse(original)
        if action.action_id!=action_id or action.candidate_id!=row[2]:
            raise Unavailable('stored candidate decision unavailable')
        try:value=strict_object(receipt)
        except (MemoryInvalidInput,RecursionError):
            raise Unavailable('stored candidate receipt unavailable') from None
        if (type(value) is not dict or set(value)!={'version','action_id','candidate_id','receipt','input_sha256'}
                or value['version']!='MEMORY-CANDIDATE-result@1' or value['action_id']!=action_id
                or value['candidate_id']!=action.candidate_id
                or value['input_sha256']!=sha256(original).hexdigest()):
            raise Unavailable('stored candidate receipt unavailable')
        result=value['receipt']
        if (type(result) is not dict or result.get('item_id')!=action.candidate_id
                or result.get('version')!=action.expected_candidate_version+1
                or result.get('status')!=('active' if action.operation=='confirm' else 'rejected')):
            raise Unavailable('stored candidate result unavailable')
        return original,receipt

    def decided(self,candidate_id):
        self.cur.execute('SELECT action_id FROM cj_memory_history_candidate_action '
                         'WHERE scope=%s AND candidate_id=%s',(self.scope,candidate_id))
        return self.cur.fetchone() is not None

    def record_decision(self,action,receipt,previous_source,new_source):
        if self.decided(action.candidate_id):raise Conflict('candidate already decided')
        encoded=encode(dict(version='MEMORY-CANDIDATE-result@1',action_id=action.action_id,
            candidate_id=action.candidate_id,receipt=receipt,input_sha256=sha256(action.raw).hexdigest()))
        self.cur.execute('''INSERT INTO cj_memory_history_candidate_action
            (scope,action_id,candidate_id,job_id,attempt_id,operation,original_input,receipt,previous_source_id,new_source_id)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (self.scope,action.action_id,action.candidate_id,action.job_id,action.attempt_id,
             action.operation,action.raw,encoded,previous_source,new_source))
        return self.decision(action.action_id)[1]

    def publish_output(self,job_id,attempt_id,messages,extraction_policy,memory_policy,context_for,*,completion=None,decoder=None):
        row,raw=self.output(job_id,attempt_id)
        if raw is None:raise Unavailable('original extraction output unavailable')
        entries=(parse_output if decoder is None else decoder)(raw,messages,extraction_policy)
        if row[0].state!='completed' and (row[0].state not in ('inflight','unknown') or row[7]!=self.epoch):
            raise Conflict('original extraction attempt or Memory basis changed')
        receipts=[]
        for parsed in entries:
            context,lease=context_for(parsed.entry)
            command=build_command(self.scope,parsed.entry,messages,context)
            if row[0].state!='completed' and self.decided(command.item_id):
                raise Conflict('original candidate has an explicit user decision')
            if row[0].state=='completed':
                previous=self.memory.operation(command.operation_id)
                if previous is None or previous[0]!=command.raw:
                    raise Unavailable('original publication receipt unavailable')
                receipt=previous[1]
            else:
                receipt=publish_command(self.memory,command,memory_policy,
                    direct_statement=parsed.direct_statement,context_lease=lease)
                self.origin(command,job_id,attempt_id,messages,parsed.entry.evidence)
            receipts.append(dict(operation_id=receipt.operation_id,item_id=receipt.item_id,
                version=receipt.version,status=receipt.status,input_sha256=receipt.input_sha256))
        if row[0].state!='completed':
            candidate=raw if completion is None else completion(tuple(receipts))
            self.transition(job_id,attempt_id,'completed',candidate=candidate)
        return tuple(receipts)

    def apply_decision(self,action,memory_policy,*,context_lease=None):
        old=self.decision(action.action_id)
        if old is not None:
            if old[0]!=action.raw:raise Conflict('original candidate action differs')
            return old[1]
        if self.decided(action.candidate_id):raise Conflict('candidate already decided')
        if action.expected_memory_epoch!=self.epoch:
            raise Conflict('candidate review basis changed')
        item=self.memory.detail(action.candidate_id)
        if item is None:raise Unavailable('candidate unavailable')
        if item.status!='candidate' or item.version!=action.expected_candidate_version:
            raise Conflict('candidate version or state changed')
        self.cur.execute('SELECT origin_refs,job_id,attempt_id FROM cj_memory_history_origin WHERE scope=%s AND source_id=%s '
                         'AND item_id=%s',(self.scope,item.command.source_id,action.candidate_id))
        origin=self.cur.fetchone()
        if origin is None:raise Unavailable('candidate origin unavailable')
        if origin[1:]!=(action.job_id,action.attempt_id):
            raise Conflict('candidate original task differs')
        previous=item.command.source_id
        if action.operation=='reject':
            self.cur.execute('UPDATE cj_memory_source SET active=false WHERE scope=%s AND source_id=%s',
                             (self.scope,previous))
            self.cur.execute("UPDATE cj_memory_item SET status='withdrawn',version=version+1 WHERE scope=%s AND item_id=%s RETURNING version",
                             (self.scope,action.candidate_id))
            version=self.cur.fetchone()[0]
            self.cur.execute('UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope=%s',(self.scope,))
            return self.record_decision(action,dict(item_id=action.candidate_id,version=version,status='rejected'),previous,None)
        self.memory.source(item.command)  # Confirmation needs a current, byte-exact unconfirmed source.
        from cj_memory.typed import STORED_VERSION,TypedCommand,packed
        if action.extent!=item.command.extent:
            raise Conflict('confirmation cannot retarget candidate extent')
        if action.extent=='current':
            if (action.context is None or item.command.context_kind!='travel'
                    or action.context.id!=item.command.context_id or context_lease is None
                    or context_lease.context!=action.context):
                raise Unavailable('original current candidate scope required')
            context_lease.check()
        value=json.loads(item.command.raw)
        suffix=sha256(action.raw).hexdigest()
        value.update(version=STORED_VERSION,operation_id='candidate-op-v1:'+suffix,
            source_id='candidate-confirm-v1:'+suffix,source_version=1,kind=action.kind,text=action.text,
            occurred_at=action.occurred_at,context_kind=item.command.context_kind,
            context_version=action.context.expected_version if action.context is not None else None)
        command=TypedCommand.parse(packed(value))
        if memory_policy.evaluate(command,action.raw) is not True:
            raise Unavailable('reviewed canonical collection unresolved')
        self.cur.execute('''SELECT item_id FROM cj_memory_item WHERE scope=%s AND subject=%s AND slot=%s
            AND extent=%s AND context_id=%s AND context_kind=%s AND status='active' AND item_id<>%s''',
            (self.scope,command.subject,command.slot,command.extent,command.context_id or '',command.context_kind,command.item_id))
        if self.cur.fetchone() is not None:
            raise Conflict('canonical slot already has a current value; review that item')
        self.memory.create_manual_source(command,True,memory_policy.expires_at)
        if self.memory.source(command) is not True:raise Unavailable('reviewed source unavailable')
        self.cur.execute('UPDATE cj_memory_source SET active=false WHERE scope=%s AND source_id=%s',
                         (self.scope,previous))
        # Canonical active-slot uniqueness is retained; a user correction is never overwritten.
        self.cur.execute("UPDATE cj_memory_item SET original_input=%s,source_id=%s,source_version=1,status='active',version=version+1 "
                         'WHERE scope=%s AND item_id=%s RETURNING version',
                         (command.raw,command.source_id,self.scope,command.item_id))
        version=self.cur.fetchone()[0]
        self.cur.execute('UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope=%s',(self.scope,))
        self.cur.execute('''INSERT INTO cj_memory_history_origin(scope,source_id,item_id,job_id,attempt_id,origin_refs)
            VALUES(%s,%s,%s,%s,%s,%s::jsonb)''',(self.scope,command.source_id,command.item_id,action.job_id,action.attempt_id,json.dumps(origin[0])))
        if action.extent=='current':context_lease.check()
        return self.record_decision(action,dict(item_id=command.item_id,version=version,status='active',
            source_id=command.source_id,source_version=1),previous,command.source_id)
