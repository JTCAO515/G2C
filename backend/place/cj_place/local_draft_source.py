"""Append-only synthetic producer interface returning the original typed parse."""
from cj_strict_json import compact
from .local_source import LocalPlaceProducer
from .gaode import prepare,PreparationError,Response,parse_response
from .contract_v1 import encode_result
from .models import Result,Outcome


class LocalDraftPlaceProducer(LocalPlaceProducer):
    version='PLACE-SYNTHETIC-DRAFT@1'
    def prepare_observation(self,query,request_ref):
        config=self.config;started=self.clock()
        try:request=prepare(config,query,request_ref,started)
        except PreparationError as error:
            result=Result(Outcome.UNSUPPORTED,query,str(error))
            def unsupported():
                self.invocations+=1
                return result,encode_result(result,evidence_kind='synthetic'),started
            return unsupported
        def invoke():
            self.invocations+=1;self.transport_calls+=1
            status,payload=self._response(query)
            raw=payload if type(payload) is bytes else compact(payload, allow_nan=True)
            response=Response(request.binding_digest,request.origin,request.path,status,raw,self.clock())
            parsed_at=self.clock()
            result=parse_response(config,request,response,now=parsed_at,evidence='synthetic')
            return result,encode_result(result,evidence_kind='synthetic'),parsed_at
        return invoke
