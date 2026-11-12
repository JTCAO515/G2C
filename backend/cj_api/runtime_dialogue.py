"""Native Lio dialogue recipes. No administrator setup, defaults or Trip writes.

The first supported recipe is a fresh public consultation. Other recipes stay
UNRUN until their actual legal setup is available; prose in a dataset is never
interpreted as an administrator instruction or an observed state.
"""
from hashlib import sha256
from pathlib import Path

from cj_message.demo_dialogue import LIO_VERSION_V2,_identity
from runtime_adapter.contract import decode,digest,encode,require,Unavailable


class NativeDialogue:
    def __init__(self,claims,boundary,database,token_supplier,wait_original,*,dataset_path):
        self.claims,self.boundary,self.database=claims,boundary,database
        self.token_supplier,self.wait_original=token_supplier,wait_original
        raw=Path(dataset_path).read_bytes()
        require(sha256(raw).hexdigest()==claims.pins.value['task_sha256'],'NATIVE_RECIPE_DATA_PIN_CHANGED')
        data=decode(raw)
        require(data['version']==claims.pins.value['task_version'],'NATIVE_RECIPE_DATA_VERSION_CHANGED')
        self.task=next(task for task in data['tasks'] if task['id']=='dev-airport')

    def prepare_task(self,task,language):
        if task['id']!='dev-airport':
            raise Unavailable('NATIVE_TASK_LEGAL_SETUP_NOT_CONNECTED')
        expected={key:self.task[key] for key in ('id','split','trip_family','setup')}
        expected['variant']={'turns':self.task['variants'][language]['turns']}
        if task!=expected:raise Unavailable('NATIVE_RECIPE_TEXT_CHANGED')
        if not (self.database.travel_context and self.database.needs_context and self.database.trip_context):
            raise Unavailable('NATIVE_LIO_COMPOSITION_NOT_CONNECTED')

    def setup(self,request,*,deadline):
        payload=request['payload']
        if (payload['task_id']!='dev-airport' or payload['language'] not in ('zh','en') or
                payload['dataset_sha256']!=self.claims.pins.value['task_sha256'] or payload['setup']!=self.task['setup']):
            raise Unavailable('NATIVE_TASK_RECIPE_BINDING_CHANGED')
        if request['prior_step_ids']:
            raise Unavailable('NATIVE_SETUP_IS_NOT_FIRST')
        # The official Lio producer creates this new chat atomically with its
        # first MESSAGE. Do not pre-create an empty chat/Trip through SQL.
        first='runtime-'+digest([self.claims.binding.scope,request['attempt_id'],1])
        cid='lio-dialogue-'+_identity(self.claims.binding.scope,'lio-new:'+first)
        def inspect(context):
            if context.scope!=self.claims.binding.scope:raise Unavailable('NATIVE_RECIPE_OWNER_CHANGED')
            original=context.query_message(first)
            if original is not None and (original.receipt.conversation_id!=cid or original.receipt.sequence!=1):
                raise Unavailable('NATIVE_FRESH_DIALOGUE_BINDING_CHANGED')
            return encode(dict(version='G2C-native-dialogue-readiness.1',
                client_step_id=request['step_id'],request_sha256=digest(request),
                binding_sha256=self.claims.binding.key,recipe='fresh-public-consultation',
                first_message_id=first,conversation_id=cid,
                first_original=None if original is None else dict(run_id=original.receipt.run_id,
                    input_sha256=original.receipt.input_sha256,sequence=original.receipt.sequence),
                # Unknown business state is explicit; the following original
                # MESSAGE/state proof, not this readiness read, determines it.
                trip_state='UNKNOWN',authorized_write='none'))
        return self.boundary.with_history_context(self.token_supplier(),inspect)

    def dispatch(self,request,*,deadline):
        if request['kind']=='task_setup':
            self.setup(request,deadline=deadline)
            return
        if request['kind']!='message':raise Unavailable('NATIVE_DIALOGUE_ACTION_NOT_CONNECTED')
        prior=request['prior_step_ids']
        if len(prior)!=1:raise Unavailable('NATIVE_DIALOGUE_RECIPE_STEP_NOT_CONNECTED')
        setup=decode(self.claims.read(prior[0],deadline=deadline))
        if setup['kind']!='task_setup':raise Unavailable('NATIVE_DIALOGUE_SETUP_UNAVAILABLE')
        self.setup(setup,deadline=deadline)
        if request['payload']!={'text':self.task['variants'][setup['payload']['language']]['turns'][0]}:
            raise Unavailable('NATIVE_RECIPE_TEXT_CHANGED')
        raw=encode(dict(version=LIO_VERSION_V2,message_id=request['step_id'],
            text=request['payload']['text'],locale=setup['payload']['language'],new_conversation=True))
        admitted=self.boundary.receive_lio(self.token_supplier(),raw,
            prepare_scope=self.database._provision_scope,version=LIO_VERSION_V2)
        receipt=self.boundary.with_history_context(self.token_supplier(),
            lambda context:context.query_message(request['step_id']).receipt)
        if (receipt.run_id,receipt.conversation_id)!=(admitted.run_id,admitted.conversation_id):
            raise Unavailable('NATIVE_ORIGINAL_ADMISSION_CHANGED')
        # The ordinary original worker consumes this receipt with its already
        # installed per-RUN candidate resolver. No second execution/fee exit.
        self.wait_original(receipt,deadline)
