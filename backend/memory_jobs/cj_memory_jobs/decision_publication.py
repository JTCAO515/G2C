"""Accepted-decision identities and origins, on the real canonical transaction."""
from hashlib import sha256
import json
from .postgres import encode
from .publication import build_command
from .publication_store import PublicationTransaction
from .codec import Conflict
from .extraction import PublicationIdentity,publication_identity


def command_for(scope,entry,messages,context,decision_digest,from_decision):
    context_key=None if context is None else ('travel',context.id)
    key=dict(version='MEMORY-DECISION-PUBLICATION@1',scope_digest=sha256(scope.encode()).hexdigest(),
        decision_source_sha256=decision_digest,subject=entry.subject,slot=entry.slot,extent=entry.extent,
        context=context_key,message_source=None if from_decision else publication_identity(scope,entry,messages,context_key).source_id)
    digest=sha256(encode(key)).hexdigest()
    return build_command(scope,entry,messages,context,identities=PublicationIdentity(
        'trip-history-op-v1:'+digest,'trip-history-item-v1:'+digest,'trip-history-v1:'+digest))


class DecisionTransaction(PublicationTransaction):
    def command(self,parsed,messages,context):
        return command_for(self.scope,parsed.entry,messages,context,parsed.decision_source_sha256,parsed.decision_evidence)

    def record_origin(self,command,job_id,attempt_id,messages,parsed):
        digest=parsed.decision_source_sha256
        # The accepted choice, not the message that happens to reference it, is
        # the logical source. Keep the first real review producer and references.
        self.cur.execute('SELECT item_id,decision_source_sha256,origin_refs FROM cj_memory_history_origin WHERE scope=%s AND source_id=%s',
                         (self.scope,command.source_id))
        old=self.cur.fetchone()
        if old is not None:
            if old[:2]!=(command.item_id,digest):raise Conflict('original decision provenance differs')
            by_id={m.receipt.message_id:m.receipt for m in messages}
            refs={encode(ref):ref for ref in old[2]}
            for evidence in parsed.entry.evidence:
                r=by_id[evidence.message_id]
                value=dict(conversation_id=r.conversation_id,generation=r.generation,sequence=r.sequence,
                           message_id=r.message_id,input_sha256=r.input_sha256)
                refs[encode(value)]=value
            updated=sorted(refs.values(),key=lambda r:(r['conversation_id'],r['generation'],r['sequence'],r['message_id'],r['input_sha256']))
            if updated!=old[2]:self.cur.execute('UPDATE cj_memory_history_origin SET origin_refs=%s::jsonb WHERE scope=%s AND source_id=%s',
                                               (json.dumps(updated),self.scope,command.source_id))
            return
        self.origin(command,job_id,attempt_id,messages,parsed.entry.evidence,decision_digest=digest)
