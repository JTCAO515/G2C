"""Explicit source2 assembly over C's actual factory, with a required context."""
from cj_draft.needs_context import publisher as context_publisher,ContextPublisher
from cj_agent.draft import DraftRejected


class CurrentTripPublisher(ContextPublisher):
    def sources_for(self,binding):
        captured=super().sources_for(binding)
        if self.source.contexts[binding] is None:
            raise DraftRejected('explicit current Trip required for source2 replanning')
        return captured


def publisher(database,checker,message_context,token_supplier,scope):
    original=context_publisher(database,checker,message_context,token_supplier,scope)
    return CurrentTripPublisher(original.repository,original.source,clock=original.clock)
