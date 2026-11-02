"""Explicit Data2 policies; never failed-parse fallback to Data1."""
from contextlib import contextmanager
from .codec import Conflict
from .processing import ProcessingSourcePolicy
from .result_policy import ResultSourcePolicy
from .publication_result import VERSION_V2
from . import model_v2


class _Filtered:
    @contextmanager
    def hold(self,principal,scope,query):
        with super().hold(principal,scope,query) as permit:
            self._snapshot=None;self._mode=None
            try:
                yield permit
                if self._snapshot is not None and self._render(self._snapshot,self._mode)!=self.original_input:
                    raise Conflict('permitted source changed before phase commit')
            finally:self._snapshot=None;self._mode=None

    def _render(self,snapshot,mode):
        raw,self.eligible_count=model_v2.prepared(self.transaction,snapshot,self.extraction,mode,max_payload_bytes=self.max_payload_bytes)
        return raw

    def _input(self,snapshot):
        row=super()._input(snapshot)
        self._snapshot=snapshot;self._mode=row[5]
        if self.eligible_count==0:raise model_v2.NoEligibleSource('no permitted original model data')
        return row

    def _entries(self,raw,messages,policy):
        return model_v2.parse_output(raw,model_v2.visible(self.transaction,messages),policy,self.repository.scope)


class ProcessingSourcePolicyV2(_Filtered,ProcessingSourcePolicy):
    pass


class ResultSourcePolicyV2(_Filtered,ResultSourcePolicy):
    result_version=VERSION_V2
