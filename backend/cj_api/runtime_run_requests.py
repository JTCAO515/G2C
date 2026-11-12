"""Resolve candidate/reflection preparation from a claimed original MESSAGE.

The normal worker uses these callbacks before preparing registered input. An
experiment ID without its durable claim fails closed instead of using C0 or a
global last candidate. Other original messages retain their ordinary registry.
"""
import json
import re
from time import monotonic

from cj_message.auth_boundary import AccessBlocked,IdentityChanged
from cj_usage.metered_exit import BudgetUnknown
from runtime_adapter.contract import decode,digest,Invalid,Unavailable


REFLECTION_MESSAGE='Runtime reflection request.'
MESSAGE_KINDS=frozenset({'message','new_conversation_message','start_controlled_generation','reflection'})


class RunRequests:
    def __init__(self,claims,boundary,token_supplier,tools,*,profile='national.1',clock=monotonic):
        self.claims,self.boundary,self.token_supplier,self.tools=claims,boundary,token_supplier,tools
        self.clock=clock
        self.profile=profile
        self.proved={}
        self.rejected=set()

    def request(self,binding):
        if re.fullmatch(r'runtime-[a-f0-9]{64}',binding.message_id) is None:return None
        if binding.scope!=self.claims.binding.scope:
            raise Unavailable('RUNTIME_ORIGINAL_SCOPE_NOT_CONFIGURED')
        raw=self.claims.read(binding.message_id,deadline=self.clock()+30)
        request=decode(raw)
        if request['kind'] not in MESSAGE_KINDS:
            raise Unavailable('RUNTIME_ORIGINAL_ACTION_HAS_NO_MESSAGE')
        text=REFLECTION_MESSAGE if request['kind']=='reflection' else request['payload']['text']
        def original(context):
            if context.scope!=binding.scope:raise Unavailable('RUNTIME_ORIGINAL_OWNER_CHANGED')
            stored=self.claims.query(context,binding.message_id)
            if stored is None or (stored.receipt.run_id,stored.receipt.conversation_id,
                    stored.receipt.generation,stored.receipt.sequence)!=(binding.run_id,
                    binding.conversation_id,binding.generation,binding.message_sequence):
                raise Unavailable('RUNTIME_ORIGINAL_RUN_CHANGED')
            if json.loads(stored.raw)['text']!=text:
                raise Unavailable('RUNTIME_ORIGINAL_MESSAGE_CHANGED')
        self.boundary.with_history_context(self.token_supplier(),original)
        self.proved[binding]=(request['step_id'],digest(request))
        return request

    def registrations(self,binding):
        try:
            request=self.request(binding)
            return (self.tools.registrations if request is None else
                    self.tools.runtime_registrations(request['candidate'],profile=self.profile))
        except (Unavailable,Invalid,OSError,AccessBlocked,IdentityChanged,BudgetUnknown):
            # No fallback registry/candidate is ever used. The original period
            # is already resolved; an empty registry cannot dispatch anything.
            # The post-start callback below records UNKNOWN before Memory or
            # any registered operation, instead of crashing the shared worker.
            self.rejected.add(binding)
            return {}

    def reflection(self,binding):
        if binding in self.rejected:raise BudgetUnknown('original runtime request unavailable; query only')
        try:request=self.request(binding)
        except (Unavailable,Invalid,OSError,AccessBlocked,IdentityChanged):
            raise BudgetUnknown('original runtime request unavailable; query only') from None
        return request['payload'] if request is not None and request['kind']=='reflection' else None

    def selects(self,binding):
        proof=self.proved.get(binding)
        if proof is None:return False
        # Do not acquire a new MESSAGE lock inside an already owned provider
        # step. Recheck original AUTH/canonical bytes; native RUN guards retain
        # the source/cancellation/ownership leases at the actual send point.
        try:request=decode(self.claims.read(binding.message_id,deadline=self.clock()+30))
        except (Unavailable,Invalid,OSError):
            raise BudgetUnknown('original runtime capture authority unavailable') from None
        if (request['step_id'],digest(request))!=proof:
            raise BudgetUnknown('original runtime capture request changed')
        return True
