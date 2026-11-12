"""Native Lio recipes over existing source-bound producers.

Unconnected recipes remain UNRUN. Dataset prose is never an administrator
instruction or an observed state, and no missing travel fact is invented.
"""
from hashlib import sha256
from pathlib import Path

from cj_message.demo_dialogue import LIO_VERSION_V2,_identity
from runtime_adapter.contract import decode,digest,encode,require,Unavailable
from .runtime_message_input import lio_input


class NativeDialogue:
    supported_tasks=frozenset({'dev-airport','dev-required-date','dev-change-mind','dev-local-edit','val-confirm-save'})
    def __init__(self,claims,boundary,database,token_supplier,wait_original,*,dataset_path,trip_boundary=None,cancellation=None,memory_setup=None,weather_fault=None):
        self.claims,self.boundary,self.database=claims,boundary,database
        self.token_supplier,self.wait_original=token_supplier,wait_original
        raw=Path(dataset_path).read_bytes()
        require(sha256(raw).hexdigest()==claims.pins.value['task_sha256'],'NATIVE_RECIPE_DATA_PIN_CHANGED')
        data=decode(raw)
        require(data['version']==claims.pins.value['task_version'],'NATIVE_RECIPE_DATA_VERSION_CHANGED')
        self.tasks={task['id']:{**{key:task[key] for key in ('id','split','trip_family','setup')},
            'variants':{locale:{key:variant[key] for key in ('turns','steps') if key in variant}
                for locale,variant in task['variants'].items()}} for task in data['tasks']}
        self.undo=None
        if trip_boundary is not None:
            from .runtime_undo import NativeUndo
            self.undo=NativeUndo(claims,boundary,trip_boundary,token_supplier)
            self.supported_tasks=self.supported_tasks|{'val-undo'}
        self.weather_fault=weather_fault
        if weather_fault is not None:self.supported_tasks=self.supported_tasks|{'dev-tool-failure'}
        self.memory_setup=memory_setup
        if memory_setup is not None:self.supported_tasks=self.supported_tasks|{'val-deleted-recall'}
        self.cancellation=cancellation
        if cancellation is not None:self.supported_tasks=self.supported_tasks|{'dev-cancel'}

    def prepare_task(self,task,language):
        if task['id'] not in self.supported_tasks:
            raise Unavailable('NATIVE_TASK_LEGAL_SETUP_NOT_CONNECTED')
        original=self.tasks[task['id']]
        expected={key:original[key] for key in ('id','split','trip_family','setup')}
        expected['variant']=original['variants'][language]
        if task!=expected:raise Unavailable('NATIVE_RECIPE_TEXT_CHANGED')
        if task['id']=='val-deleted-recall':self.memory_setup.require_available()
        if not (self.database.travel_context and self.database.needs_context and self.database.trip_context):
            raise Unavailable('NATIVE_LIO_COMPOSITION_NOT_CONNECTED')

    def _setup_task(self,request):
        payload=request['payload']
        if payload['task_id'] not in self.supported_tasks:raise Unavailable('NATIVE_TASK_LEGAL_SETUP_NOT_CONNECTED')
        task=self.tasks[payload['task_id']]
        if (payload['language'] not in ('zh','en') or
                payload['dataset_sha256']!=self.claims.pins.value['task_sha256'] or payload['setup']!=task['setup']):
            raise Unavailable('NATIVE_TASK_RECIPE_BINDING_CHANGED')
        if request['prior_step_ids']:
            raise Unavailable('NATIVE_SETUP_IS_NOT_FIRST')
        return task

    def setup(self,request,*,deadline):
        task=self._setup_task(request)
        payload=request['payload']
        if task['id']=='val-deleted-recall':return self.memory_setup.proof(request,deadline=deadline)
        # The official Lio producer creates this new chat atomically with its
        # first MESSAGE. Do not pre-create an empty chat/Trip through SQL.
        first='runtime-'+digest([self.claims.binding.scope,request['attempt_id'],1])
        cid='lio-dialogue-'+_identity(self.claims.binding.scope,'lio-new:'+first)
        def inspect(context):
            if context.scope!=self.claims.binding.scope:raise Unavailable('NATIVE_RECIPE_OWNER_CHANGED')
            original=self.claims.query(context,first)
            if original is not None and (original.receipt.conversation_id!=cid or original.receipt.sequence!=1):
                raise Unavailable('NATIVE_FRESH_DIALOGUE_BINDING_CHANGED')
            return encode(dict(version='G2C-native-dialogue-readiness.1',
                client_step_id=request['step_id'],request_sha256=digest(request),
                binding_sha256=self.claims.binding.key,recipe='fresh-public-consultation' if payload['task_id']=='dev-airport' else 'fresh-dialogue-native-inputs',
                first_message_id=first,conversation_id=cid,
                first_original=None if original is None else dict(run_id=original.receipt.run_id,
                    input_sha256=original.receipt.input_sha256,sequence=original.receipt.sequence),
                # Unknown business state is explicit; the following original
                # MESSAGE/state proof, not this readiness read, determines it.
                trip_state='UNKNOWN',authorized_write='none'))
        return self.boundary.with_history_context(self.token_supplier(),inspect)

    def dispatch(self,request,*,deadline):
        if request['kind']=='task_setup':
            if request['payload']['task_id']=='val-deleted-recall':
                self._setup_task(request)
                self.memory_setup.dispatch(request,deadline=deadline)
                return
            self.setup(request,deadline=deadline)
            return
        if request['kind']=='lio_undo_current_trip':
            if self.undo is None:raise Unavailable('NATIVE_UNDO_NOT_CONNECTED')
            return self.undo.dispatch(request,deadline=deadline)
        if request['kind']=='cancel_original_run':
            if self.cancellation is None:raise Unavailable('NATIVE_CONTROL_NOT_CONNECTED')
            return self.cancellation.dispatch(request,deadline=deadline)
        controlled=request['kind']=='start_controlled_generation'
        if request['kind'] not in ('message','new_conversation_message') and not controlled:raise Unavailable('NATIVE_DIALOGUE_ACTION_NOT_CONNECTED')
        prior=request['prior_step_ids']
        if not prior:raise Unavailable('NATIVE_DIALOGUE_RECIPE_STEP_NOT_CONNECTED')
        setup=decode(self.claims.read(prior[0],deadline=deadline))
        if setup['kind']!='task_setup':raise Unavailable('NATIVE_DIALOGUE_SETUP_UNAVAILABLE')
        task=self._setup_task(setup)
        variant=task['variants'][setup['payload']['language']]
        inputs=variant.get('steps')
        if inputs is None:inputs=[dict(text=text) for text in variant['turns']]
        index=len(prior)-1
        if index>=len(inputs) or request['payload']!=inputs[index]:
            raise Unavailable('NATIVE_RECIPE_TEXT_CHANGED')
        if controlled:
            if self.cancellation is None:raise Unavailable('NATIVE_CONTROL_NOT_CONNECTED')
            self.cancellation.prepare(request,deadline=deadline)
        raw=lio_input(self.claims.binding.scope,request,setup['payload']['language'])
        admitted=self.boundary.receive_lio(self.token_supplier(),raw,
            prepare_scope=self.database._provision_scope,version=LIO_VERSION_V2)
        receipt=self.boundary.with_history_context(self.token_supplier(),
            lambda context:self.claims.query(context,request['step_id']).receipt)
        if (receipt.run_id,receipt.conversation_id)!=(admitted.run_id,admitted.conversation_id):
            raise Unavailable('NATIVE_ORIGINAL_ADMISSION_CHANGED')
        # The ordinary original worker consumes this receipt with its already
        # installed per-RUN candidate resolver. No second execution/fee exit.
        if controlled:self.cancellation.wait_started(receipt,deadline=deadline)
        else:self.wait_original(receipt,deadline)

    def action_proof(self,request,*,deadline):
        if request['kind']=='cancel_original_run':
            if self.cancellation is None:raise Unavailable('NATIVE_CONTROL_NOT_CONNECTED')
            return self.cancellation.proof(request,deadline=deadline)
        if self.undo is None or request['kind']!='lio_undo_current_trip':
            raise Unavailable('NATIVE_ACTION_PROOF_NOT_CONNECTED')
        return self.undo.proof(request,deadline=deadline)
