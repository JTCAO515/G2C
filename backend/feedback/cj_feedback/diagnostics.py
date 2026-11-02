"""FEEDBACK@1.0 protected original-action locator, no second private store."""
from dataclasses import asdict
import json
from cj_run.core import Binding
from cj_run.feedback_locator import read_locator
from .domain import ReferenceUnavailable


class DiagnosticReader:
    def __init__(self,feedback,message,resolve_run):
        if feedback.checker is not message.checker:raise ReferenceUnavailable()
        self.feedback,self.message,self.resolve_run=feedback,message,resolve_run

    def read(self,token,action_id,project):
        def original(op):
            receipt=op.query_action(action_id)
            if receipt is None:raise ReferenceUnavailable()
            source=receipt.source
            def output(locator):
                value=dict(version='FEEDBACK@1.0',action_id=receipt.action_id,input_sha256=receipt.input_sha256,
                    submitted_at=receipt.submitted_at,source_at_submit=asdict(source) if source else None,
                    current_locator=locator,external_model_version=None,rule_version=None,
                    unavailable=['external_model_version','rule_version','provider_internal_failure_stage'],
                    references_are_execution_proof=False)
                encoded=project(value)
                if type(encoded) is not bytes or len(encoded)>65536:raise ReferenceUnavailable()
                return encoded
            if source is None:return output(None)
            def locate(ctx):
                stored=ctx.query_message(source.message_id)
                if stored is None:raise ReferenceUnavailable()
                r=stored.receipt
                if (r.message_id,r.conversation_id,r.generation,r.sequence,r.run_id,r.input_sha256)!=(
                    source.message_id,source.conversation_id,source.generation,source.message_sequence,source.run_id,source.message_input_sha256):
                    raise ReferenceUnavailable()
                binding=Binding(ctx.scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
                locator=read_locator(self.resolve_run(ctx.principal,ctx.scope),binding)
                value=asdict(locator)
                value['message_version']=json.loads(stored.raw)['version']
                value['observation']='current_read; source_at_submit is the immutable original observation'
                return output(value)
            return self.message.with_history_context(token,locate)
        # Both original feedback and fully encoded source locator leave through
        # canonical fresh admission guards. No context or receipt escapes.
        return self.feedback.with_operation(token,original)
