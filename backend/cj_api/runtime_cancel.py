"""Controlled generation and the existing source-bound original RUN cancel."""
from cj_run.cancellation import CancellationHandler,TravelCancelCommand,CancellationUnknown
from runtime_adapter.contract import decode,encode,Unavailable


class NativeCancellation:
    def __init__(self,claims,boundary,database,token_supplier,controls,originals):
        self.claims,self.boundary,self.database=claims,boundary,database
        self.token_supplier,self.controls,self.originals=token_supplier,controls,originals
        self.handler=CancellationHandler(boundary,lambda principal,scope:database.run_repository(scope))

    def prepare(self,request,*,deadline):
        if request['kind']!='start_controlled_generation':raise Unavailable('NATIVE_CONTROL_ACTION_CHANGED')
        setup=decode(self.claims.read(request['prior_step_ids'][0],deadline=deadline))
        if setup['kind']!='task_setup' or setup['payload']['task_id']!='dev-cancel':
            raise Unavailable('NATIVE_CONTROL_RECIPE_CHANGED')
        self.controls.prepare(request['step_id'],deadline)

    def wait_started(self,receipt,*,deadline):
        binding=self.controls.wait_started(receipt.message_id,deadline)
        if binding.scope!=self.claims.binding.scope or binding.run_id!=receipt.run_id:
            raise Unavailable('NATIVE_CONTROL_ORIGINAL_CHANGED')
        original=decode(self.originals.inventory(self.token_supplier(),receipt.message_id))
        if original['status']!='running':raise Unavailable('NATIVE_CONTROL_NOT_RUNNING')

    def target(self,request,*,deadline):
        if request['kind']!='cancel_original_run' or len(request['prior_step_ids'])!=2:
            raise Unavailable('NATIVE_CANCEL_RECIPE_STEP_CHANGED')
        started=decode(self.claims.read(request['prior_step_ids'][-1],deadline=deadline))
        if started['kind']!='start_controlled_generation':raise Unavailable('NATIVE_CANCEL_TARGET_CHANGED')
        return started['step_id']

    def dispatch(self,request,*,deadline):
        mid=self.target(request,deadline=deadline)
        command=TravelCancelCommand.parse(encode(dict(version='RUN-cancel.2',message_id=mid)))
        def project(state,reference):
            return encode(dict(version='G2C-native-cancel-original.1',message_id=mid,run_id=state.binding.run_id,
                status=state.status,event_highwater=state.sequence,reference=reference.public_value()))
        try:result=self.handler.cancel_travel_projected(self.token_supplier(),command,project)
        except CancellationUnknown:
            # Read the same original once; never resend cancellation. Without
            # proof of cancellation, the pause expires closed as UNKNOWN rather
            # than releasing the worker to publish an unconfirmed late result.
            original=decode(self.originals.inventory(self.token_supplier(),mid))
            if original['status']=='cancelled':self.controls.release(mid)
            raise Unavailable('NATIVE_CANCEL_ACK_UNCERTAIN_QUERY_ONLY') from None
        if decode(result)['status']!='cancelled':raise Unavailable('ORIGINAL_CANCEL_NOT_CONFIRMED')
        self.controls.release(mid)
        return result

    def proof(self,request,*,deadline):
        mid=self.target(request,deadline=deadline)
        inventory=decode(self.originals.inventory(self.token_supplier(),mid))
        return encode(dict(version='G2C-native-cancel-original.1',action_id=request['step_id'],message_id=mid,
            run_id=inventory['run_id'],status='CANCELLED' if inventory['status']=='cancelled' else 'UNKNOWN',
            original_status=inventory['status'],events=inventory['events']))
