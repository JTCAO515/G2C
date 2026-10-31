"""B model/Meter driver; C owns preparation, scope engine and sole Trip writer."""
from cj_usage.local_provider_exit import BudgetExceeded
from .draft import DraftRejected
from .provider import ProviderFailed,ProviderUnknown


def execute(worker,receipt,binding,state,inputs):
    source=worker.message_context.capture(binding)
    publisher=worker.edit_publisher
    try:
        prepared=publisher.prepare(binding,source)
        if type(prepared.system) is not str or not prepared.system.strip() or len(prepared.system.encode('utf8'))>1048576:
            raise DraftRejected('bounded explicit edit prompt required')
        reply=''.join(worker._stream(binding,inputs,system=prepared.system))
        deadline=worker.budget_exit.prepare_publication(binding)
        with worker.message_context.publication(binding,source,deadline=deadline) as publication:
            publication.enter_source(worker.memory_run.hold(binding))
            publication.enter_source(publisher.hold_sources(publication,prepared))
            proposal_id=publisher.publish_in_transaction(publication,prepared,reply)
            # This is the original RUN state engine, on the same cursor as C's writer.
            publication.record_effect(proposal_id)
        state=worker._event(binding,worker.runs.snapshot(binding),'completed')
        return worker._finish(receipt,state,proposal_id)
    except BudgetExceeded:
        state=worker._budget_rejection(binding,'draft')
        state=worker._event(binding,state,'completed')
    except ProviderUnknown:
        state=worker._event(binding,worker.runs.snapshot(binding),'unknown')
    except (DraftRejected,ProviderFailed) as exc:
        outcome='validation_failed' if isinstance(exc,DraftRejected) else 'provider_failed' if isinstance(exc,ProviderFailed) else 'provider_unknown'
        state=worker._event(binding,worker.runs.snapshot(binding),'draft_outcome',outcome)
        state=worker._event(binding,state,'completed')
    return worker._finish(receipt,state)
