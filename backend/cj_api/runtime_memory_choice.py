"""Explicit native Remember with retained opaque input and read-only proof."""
from runtime_adapter.contract import digest,Unavailable
from .runtime_action_input import NativeActionInputs


class NativeMemoryChoice:
    def __init__(self,claims,memory_cards,token_supplier):
        self.claims,self.cards,self.token_supplier=claims,memory_cards,token_supplier
        self.inputs=NativeActionInputs(claims)

    def remember(self,request,label,target,*,deadline):
        native=dict(version='LIO-memory-action.1',action_id='runtime-remember-'+digest([request['step_id'],label]),
            operation='remember',target=target)
        self.inputs.record(request,native,deadline=deadline,label=label)
        # Current target/candidate/source validation and explicit confirmation
        # remain in the same original Lio action service. No SQL/bootstrap or
        # alternate candidate on uncertain ACK.
        receipt=self.cards.decide(self.token_supplier(),native)
        if receipt['status']!='remembered':raise Unavailable('NATIVE_REMEMBER_NOT_CONFIRMED')
        return receipt

    def proof(self,request,label,*,deadline):
        native=self.inputs.read(request,deadline=deadline,label=label)
        receipt=self.cards.decide(self.token_supplier(),native,read_only=True)
        return dict(action_id=receipt['action_id'],status=receipt['status'])
