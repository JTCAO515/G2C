"""RUN-MEMORY-HISTORY@1: current original input plus genuine formal decisions.

The host collects coordinates, never client/model text as authority. The actual
C runtime keeps the original Memory/reference locks and checks at every effect.
"""
import json

from cj_memory.runtime import RuntimeDenied

FENCE='MEMORY-HISTORY-ERASURE-FENCE@1'


class HistoryMemory:
    def __init__(self,memory,collect):
        self.memory,self.collect=memory,collect

    def capture(self,binding):
        messages,decisions=self.collect(binding)
        run=self.memory.capture_history(binding,messages,decision_source_sha256s=decisions)
        if run.erasure_protocol!=FENCE:raise RuntimeDenied('explicit original-history erasure fence required')
        return run


class OriginalHistory:
    def __init__(self,messages,decision_refs):
        self.messages,self.decision_refs=messages,decision_refs

    def __call__(self,binding):
        stored=self.messages.query(binding.message_id)
        if stored is None:raise RuntimeDenied('original model input unavailable')
        receipt=stored.receipt
        if (self.messages.repository.scope!=binding.scope or
            (receipt.message_id,receipt.conversation_id,receipt.generation,receipt.run_id,receipt.sequence)!=
            (binding.message_id,binding.conversation_id,binding.generation,binding.run_id,binding.message_sequence)):
            raise RuntimeDenied('original model history binding changed')
        refs=[dict(conversation_id=receipt.conversation_id,generation=receipt.generation,
                   sequence=receipt.sequence,message_id=receipt.message_id,input_sha256=receipt.input_sha256)]
        # MESSAGE1/2's answer prompt contains current input plus C Memory only.
        # Formal3/4 additionally contains genuine Trip bytes; its trusted host
        # must collect the corresponding C digest, never substitute an empty set.
        command=json.loads(stored.raw)
        decisions=self.decision_refs(binding) if command.get('version') in ('MESSAGE-send.3','MESSAGE-send.4') else []
        return refs,decisions
