"""Native reflection host over original MESSAGE, RUN, Meter and financial exit.

B composition supplies the running worker/source fence and original worker wait.
This does not start a second worker, change its registry globally, or activate a
live experiment. Dialogue task recipes are not yet admitted by this slice.
"""
import sqlite3

from cj_usage.metered_exit import BudgetUnknown
from cj_message.auth_boundary import AccessBlocked,IdentityChanged
from cj_message.domain import CommitUnknown,Unavailable as MessageUnavailable,InvalidInput,InputConflict
from runtime_adapter.contract import decode,Unavailable


class NativeRuntimeBackend:
    def __init__(self,authority,claims,collector,boundary,token_supplier,*,
                 require_worker,wait_original,admit_reflection,dialogue=None):
        self.authority,self.claims,self.collector=authority,claims,collector
        self.boundary,self.token_supplier=boundary,token_supplier
        self.require_worker,self.wait_original=require_worker,wait_original
        self.admit_reflection=admit_reflection
        self.dialogue=dialogue

    def binding(self):return self.authority.binding()

    def pins(self):return self.authority.pins()

    def require(self,**arguments):
        try:self.authority.require(**arguments)
        except (BudgetUnknown,sqlite3.Error):
            raise Unavailable('ORIGINAL_FINANCIAL_AUTHORITY_UNAVAILABLE') from None
        if not arguments['read_only']:
            self.require_worker(self.claims.binding,self.claims.pins,arguments['deadline'])

    def prepare_task(self,task,language):
        # Whole-task preflight precedes any canonical claim or paid setup. A
        # reflection host alone cannot invent legal Trip/Memory/cancel fixtures.
        if self.dialogue is None:raise Unavailable('NATIVE_DIALOGUE_TASK_RECIPES_NOT_CONNECTED')
        self.dialogue.prepare_task(task,language)

    def claim(self,request,*,deadline):
        value=decode(request)
        if type(value) is not dict or (value.get('kind')!='reflection' and
                (self.dialogue is None or value.get('kind') not in ('task_setup','message','new_conversation_message','lio_undo_current_trip','start_controlled_generation','cancel_original_run'))):
            raise Unavailable('NATIVE_ACTION_NOT_CONNECTED')
        self.require_worker(self.claims.binding,self.claims.pins,deadline)
        return self.claims.claim(request,deadline=deadline)

    def dispatch(self,request,*,capability,deadline):
        try:return self._dispatch(request,capability=capability,deadline=deadline)
        except (AccessBlocked,IdentityChanged):
            raise Unavailable('ORIGINAL_AUTH_UNAVAILABLE') from None
        except CommitUnknown:
            raise Unavailable('NATIVE_ADMISSION_ACK_UNCERTAIN') from None
        except (MessageUnavailable,InvalidInput,InputConflict):
            raise Unavailable('NATIVE_ORIGINAL_ACTION_UNAVAILABLE') from None

    def _dispatch(self,request,*,capability,deadline):
        original=self.claims.consume(request,capability,deadline=deadline)
        self.require(binding=self.claims.binding,pins_sha256=self.claims.pins.key,
            purpose='cancel_original' if original['kind']=='cancel_original_run' else 'reflection',
            deadline=deadline,read_only=False)
        if original['kind']!='reflection':
            if self.dialogue is None:raise Unavailable('NATIVE_ACTION_NOT_CONNECTED')
            self.dialogue.dispatch(original,deadline=deadline)
            return
        receipt=self.admit_reflection(original['step_id'])
        # This waits on the *same* original receipt using B's preconfigured
        # worker; it must never resend or select another account/provider/ID.
        self.wait_original(receipt,deadline)

    def inspect(self,attempt_id,step_id,*,deadline):
        return self.collector.inspect(attempt_id,step_id,deadline=deadline)

    def original(self,reference,*,deadline):
        return self.collector.original(reference,deadline=deadline)
