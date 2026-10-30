"""Original accepted user text → one metered model → unconfirmed NEEDS preview."""
from types import MappingProxyType
from cj_agent.provider import FakeProvider,ProviderUnknown
from cj_needs.domain import InvalidInput
from cj_needs.preview import preview,synthetic_extract
from cj_usage.registered_exit import MODEL_REGISTRY

SYSTEM='NEEDS-EXTRACTION@1 synthetic data only; never manual confirmation, Memory or execution authority.'


class LocalNeedsPreview:
    version='CJ-LOCAL-NEEDS-PREVIEW@1'
    registrations=MappingProxyType({**MODEL_REGISTRY,'model.needs_preview':MODEL_REGISTRY['model.answer']})

    def answer(self,worker,binding,messages):
        # RunWorker supplies the original accepted text as its last user input.
        source=messages[-1]['content']
        raw=''.join(worker._registered_stream(binding,'model.needs_preview.0','model.needs_preview',
                                              (messages,SYSTEM,worker.provider)))
        try:body=preview(raw.encode('utf8'),message_id=binding.message_id,run_id=binding.run_id,source_text=source)
        except (InvalidInput,UnicodeError):raise ProviderUnknown('NEEDS extraction unavailable') from None
        yield body.decode('utf8')+'\n'


class SyntheticNeedsModel(FakeProvider):
    def stream(self,messages,system=None):
        if system!=SYSTEM:
            yield from super().stream(messages,system=system);return
        self.calls+=1
        yield synthetic_extract(messages[-1]['content']).decode('utf8')
