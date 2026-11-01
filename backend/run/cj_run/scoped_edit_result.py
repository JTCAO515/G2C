"""Negotiated publisher2 driver; C owns explanation/preview and stored result body."""
from cj_message.edit_protocol import PreparedEdit
from cj_message.edit_result_protocol import PreparedClarification,ScopedResult
from cj_usage.local_provider_exit import BudgetExceeded
from cj_agent.draft import DraftRejected
from cj_agent.provider import ProviderFailed,ProviderUnknown
from .core import Denied


def execute(worker,receipt,binding,state,inputs,*,deadline):
    source=worker.message_context.capture(binding);publisher=worker.edit_publisher
    try:
        prepared=publisher.prepare(binding,source)
        clarification=type(prepared) is PreparedClarification
        reply=None
        if not clarification:
            if type(prepared) is not PreparedEdit or type(prepared.system) is not str or not prepared.system.strip() or len(prepared.system.encode('utf8'))>1048576:
                raise DraftRejected('bounded explicit edit prompt required')
            reply=''.join(worker._stream(binding,inputs,system=prepared.system))
            deadline=worker.budget_exit.prepare_publication(binding)
        with worker.message_context.publication(binding,source,deadline=deadline) as publication:
            publication.enter_source(worker.memory_run.hold(binding))
            publication.enter_source(publisher.hold_sources(publication,prepared))
            result=(publisher.publish_clarification_in_transaction(publication,prepared) if clarification else
                    publisher.publish_in_transaction(publication,prepared,reply))
            if type(result) is ScopedResult:
                if clarification!=(result.kind=='clarification_required'):raise Denied('publisher result phase mismatch')
                state=publication.record_result(result);proposal_id=None
            else:
                if clarification or type(result) is not str:raise Denied('clarification cannot publish a Proposal')
                publication.record_effect(result);proposal_id=result
        if proposal_id is not None:state=worker._event(binding,worker.runs.snapshot(binding),'completed')
        return worker._finish(receipt,state,proposal_id)
    except BudgetExceeded:
        state=worker._budget_rejection(binding,'draft')
        state=worker._event(binding,state,'completed')
    except ProviderUnknown:
        state=worker._event(binding,worker.runs.snapshot(binding),'unknown')
    except (DraftRejected,ProviderFailed) as exc:
        outcome='validation_failed' if isinstance(exc,DraftRejected) else 'provider_failed'
        state=worker._event(binding,worker.runs.snapshot(binding),'draft_outcome',outcome)
        state=worker._event(binding,state,'completed')
    return worker._finish(receipt,state)
