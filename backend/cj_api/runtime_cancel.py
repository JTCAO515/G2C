"""Controlled generation and the existing source-bound original RUN cancel."""
from time import monotonic,sleep

from cj_run.cancellation import CancellationHandler,TravelCancelCommand,CancellationUnknown
from runtime_adapter.contract import decode,encode,Unavailable


class NativeCancellation:
    def __init__(self,claims,boundary,database,token_supplier,controls,originals,*,clock=monotonic):
        self.claims,self.boundary,self.database=claims,boundary,database
        self.token_supplier,self.controls,self.originals=token_supplier,controls,originals
        self.clock=clock
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
        while self.clock()<deadline:
            try:proof=decode(self.proof(request,deadline=deadline))
            except Unavailable as error:
                if str(error)!='NATIVE_CANCEL_DELIVERY_PENDING':raise
                sleep(min(.05,max(0,deadline-self.clock())))
            else:
                if proof['status']!='CANCELLED':raise Unavailable('NATIVE_CANCEL_SOURCE_CHANGED')
                return result
        raise Unavailable('NATIVE_CANCEL_DRAIN_UNCONFIRMED_QUERY_ONLY')

    def _acknowledged(self,mid,run_id):
        def read(context):
            original=self.claims.query(context,mid)
            if original is None or original.receipt.run_id!=run_id:
                raise Unavailable('NATIVE_CANCEL_SOURCE_UNAVAILABLE')
            with self.database.connect(context.scope) as db:
                db.execute('SET TRANSACTION READ ONLY')
                row=db.execute('SELECT acknowledged FROM cj_message_delivery '
                    'WHERE scope=%s AND message_id=%s AND run_id=%s',
                    (context.scope,mid,run_id)).fetchone()
            if row is None or type(row[0]) is not bool:
                raise Unavailable('NATIVE_CANCEL_DELIVERY_UNAVAILABLE')
            if self.claims.query(context,mid)!=original:
                raise Unavailable('NATIVE_CANCEL_SOURCE_CHANGED')
            return row[0]
        return self.boundary.with_history_context(self.token_supplier(),read)

    def proof(self,request,*,deadline):
        mid=self.target(request,deadline=deadline)
        inventory=decode(self.originals.inventory(self.token_supplier(),mid))
        cancelled=inventory['status']=='cancelled'
        if cancelled and not self._acknowledged(mid,inventory['run_id']):
            raise Unavailable('NATIVE_CANCEL_DELIVERY_PENDING')
        return encode(dict(version='G2C-native-cancel-original.1',action_id=request['step_id'],message_id=mid,
            run_id=inventory['run_id'],status='CANCELLED' if cancelled else 'UNKNOWN',
            original_status=inventory['status'],events=inventory['events'],
            delivery_acknowledged=True if cancelled else None))
