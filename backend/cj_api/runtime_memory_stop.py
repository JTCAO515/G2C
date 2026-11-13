"""Original typed STOP-USE, with exact target persistence and no model calls."""
from cj_memory_management.typed_guarded import execute,query
from cj_memory_management.typed import TypedStopUse
from cj_memory.operation import OperationWithheld
from cj_memory.domain import Conflict,Unavailable as MemoryUnavailable
from runtime_adapter.contract import digest,encode,decode,Unavailable

from .runtime_action_input import NativeActionInputs


class NativeMemoryStop:
    def __init__(self,claims,repository,policy,guard,authority):
        self.inputs=NativeActionInputs(claims)
        self.repository,self.policy,self.guard,self.authority=repository,policy,guard,authority

    @staticmethod
    def _native(operation):
        try:return decode(operation())
        except OperationWithheld:
            raise Unavailable('NATIVE_STOP_USE_ACK_UNCERTAIN_QUERY_ONLY') from None
        except (Conflict,MemoryUnavailable):
            raise Unavailable('NATIVE_STOP_USE_ORIGINAL_UNAVAILABLE') from None

    @staticmethod
    def _receipt(value):
        return encode(dict(action_id=value.operation_id,item_id=value.item_id,version=value.version,
            status=value.status,input_sha256=value.input_sha256))

    def stop(self,request,label,item,*,deadline):
        command=item.command
        native=dict(version='MEMORY-STOP-USE@2',action_id='runtime-stop-'+digest([request['step_id'],label]),
            operation='withdraw',item_id=command.item_id,expected_version=item.version,
            source_id=command.source_id,expected_source_version=command.source_version)
        raw=encode(native);TypedStopUse.parse(raw)
        self.inputs.record(request,native,deadline=deadline,label=label)
        result=self._native(lambda:execute(self.repository,self.policy,self.guard,self.authority,raw,self._receipt))
        if result['status']!='withdrawn':raise Unavailable('NATIVE_STOP_USE_NOT_CONFIRMED')
        return result

    def proof(self,request,label,*,deadline):
        native=self.inputs.read(request,deadline=deadline,label=label)
        return self._native(lambda:query(self.repository,self.policy,self.guard,native['action_id'],
            lambda receipt:encode(None) if receipt is None else self._receipt(receipt)))
