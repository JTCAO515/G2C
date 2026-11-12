"""Original typed STOP-USE, with exact target persistence and no model calls."""
from cj_memory_management.typed_guarded import execute,query
from cj_memory_management.typed import TypedStopUse
from runtime_adapter.contract import digest,encode,Unavailable

from .runtime_action_input import NativeActionInputs


class NativeMemoryStop:
    def __init__(self,claims,repository,policy,guard,authority):
        self.inputs=NativeActionInputs(claims)
        self.repository,self.policy,self.guard,self.authority=repository,policy,guard,authority

    @staticmethod
    def _receipt(value):
        return dict(action_id=value.operation_id,item_id=value.item_id,version=value.version,
            status=value.status,input_sha256=value.input_sha256)

    def stop(self,request,label,item,*,deadline):
        command=item.command
        native=dict(version='MEMORY-STOP-USE@2',action_id='runtime-stop-'+digest([request['step_id'],label]),
            operation='withdraw',item_id=command.item_id,expected_version=item.version,
            source_id=command.source_id,expected_source_version=command.source_version)
        raw=encode(native);TypedStopUse.parse(raw)
        self.inputs.record(request,native,deadline=deadline,label=label)
        result=execute(self.repository,self.policy,self.guard,self.authority,raw,self._receipt)
        if result['status']!='withdrawn':raise Unavailable('NATIVE_STOP_USE_NOT_CONFIRMED')
        return result

    def proof(self,request,label,*,deadline):
        native=self.inputs.read(request,deadline=deadline,label=label)
        return query(self.repository,self.policy,self.guard,native['action_id'],
            lambda receipt:None if receipt is None else self._receipt(receipt))
