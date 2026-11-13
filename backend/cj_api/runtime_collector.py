"""G evidence projections from canonical claims and original protected sources.

No expected task state enters this collector. Recomputing a descriptor always
repeats native source reads; saved reference descriptors contain no user bytes.
"""
from hashlib import sha256
from time import monotonic

from runtime_adapter.contract import VERSION,decode,digest,encode,Invalid,Unavailable

from .runtime_original_refs import OriginalReferences
from .runtime_preparation_input import preparatory_message


class RuntimeCollector:
    def __init__(self,originals,claims,run_requests,token_supplier,pins,directory,*,
                 guard,state_reader,model_reader,dialogue=None,clock=monotonic):
        self.originals,self.claims,self.run_requests=originals,claims,run_requests
        self.token_supplier,self.pins=token_supplier,pins
        self.guard,self.state_reader,self.model_reader,self.clock=guard,state_reader,model_reader,clock
        self.binding=claims.binding
        self.dialogue=dialogue
        self.refs=OriginalReferences(directory,self.binding,self,guard=guard)

    def inventory(self,token,mid):return self.originals.inventory(token,mid)
    def input(self,token,mid,op):return self.originals.input(token,mid,op)
    def meter(self,token,mid,op):return self.originals.meter(token,mid,op)
    def fee(self,token,mid,op):return self.originals.fee(token,mid,op)
    def artifact(self,token,mid,op,*,wire_input=False):
        return self.originals.artifact(token,mid,op,wire_input=wire_input)

    def _ref(self,token,kind,mid,op=None):
        return self.refs.issue(token,kind=kind,message_id=mid,operation_id=op)

    def _source(self,token,mid):
        request=decode(self.claims.read(mid,deadline=self.clock()+30))
        prepared=preparatory_message(request)
        if not prepared and request['kind'] in ('task_setup','lio_undo_current_trip'):
            if self.dialogue is None:raise Unavailable('NATIVE_DIALOGUE_TASK_RECIPES_NOT_CONNECTED')
            if request['kind']=='task_setup':self.dialogue.setup(request,deadline=self.clock()+30)
            else:self.dialogue.action_proof(request,deadline=self.clock()+30)
            return request,None
        if not prepared and request['kind'] not in ('message','new_conversation_message','start_controlled_generation','reflection'):
            raise Unavailable('RUNTIME_COLLECTOR_ACTION_NOT_CONNECTED')
        inventory=decode(self.originals.inventory(token,mid))
        # Resolve the native binding and verify its original message content
        # against the already admitted canonical action, rather than building a
        # proof from fields supplied in the envelope being checked.
        def binding(context):
            stored=self.claims.query(context,mid)
            if stored is None:raise Unavailable('ORIGINAL_MESSAGE_UNAVAILABLE')
            from cj_run.core import Binding
            r=stored.receipt
            return Binding(context.scope,r.conversation_id,r.generation,mid,r.run_id,r.sequence)
        native=self.originals.boundary.with_history_context(token,binding)
        if self.run_requests.request(native)!=request or inventory['run_id']!=native.run_id:
            raise Unavailable('RUNTIME_COLLECTOR_CANONICAL_BINDING_CHANGED')
        return request,inventory

    def _fee(self,token,mid,op):
        try:return decode(self.originals.fee(token,mid,op))
        except Unavailable as error:
            if str(error)!='ORIGINAL_FINANCIAL_ATTEMPT_UNAVAILABLE':raise
            return None

    def _output(self,token,mid,op):
        # Only a complete, hash-verified original has an output reference.
        # Partial streams retain their INTENT/wire artifact without inventing a
        # final output. A corrupted existing artifact is not treated as absent.
        try:return decode(self.originals.artifact(token,mid,op))['result_utf8'].encode()
        except FileNotFoundError:return None

    def _operation(self,token,mid,inventory,entry):
        op=entry['operation_id']
        def available(read):
            # A missing/bad component cannot hide other original operations or
            # their fee receipts. Null becomes a per-field UNKNOWN in G. Native
            # AUTH revocation/identity exceptions are deliberately not caught.
            try:return read()
            except (Unavailable,Invalid,OSError):return None
        try:fee=self._fee(token,mid,op)
        except (Unavailable,Invalid,OSError):fee=None;sent='UNKNOWN'
        else:sent='NOT_SENT' if fee is None else fee['state']
        meter=available(lambda:decode(self.originals.meter(token,mid,op)))
        output=available(lambda:self._output(token,mid,op))
        return dict(operation_id=op,attempt_id=entry['attempt_id'],run_id=inventory['run_id'],
            registration_id=entry['registration_id'],kind=entry['kind'],
            input=available(lambda:self._ref(token,'input',mid,op)),
            output=None if output is None else available(lambda:self._ref(token,'output',mid,op)),
            meter=available(lambda:self._ref(token,'meter_link',mid,op)),
            provider=available(lambda:self._ref(token,'provider',mid,op)) if sent=='RECEIVED' else None,
            fee=None if fee is None else self._ref(token,'fee',mid,op),
            provider_state=sent,fee_state=sent,meter_state='UNKNOWN' if meter is None else meter['state'].upper(),
            model=available(lambda:self.model_reader(token,mid,op)) if entry['kind'] in ('model','memory') else None)

    def projection(self,token,kind,mid,op):
        request,inventory=self._source(token,mid)
        if inventory is None:
            if kind in ('state','result'):
                return (self.dialogue.setup(request,deadline=self.clock()+30) if request['kind']=='task_setup' else
                    self.dialogue.action_proof(request,deadline=self.clock()+30))
            association=dict(binding_sha256=self.binding.key,client_step_id=mid,
                request_sha256=digest(request),message_id=None,action_id=mid,run_ids=[])
            if kind=='protected_inventory':return encode(dict(**association,operation_ids=[]))
            if kind!='action':raise Unavailable('NATIVE_SETUP_HAS_NO_PROVIDER_OPERATION')
            status='PASS' if request['kind']=='task_setup' else decode(self.dialogue.action_proof(request,deadline=self.clock()+30))['status']
            return encode(dict(**association,status=status,inventory=self._ref(token,'protected_inventory',mid),
                result=self._ref(token,'result',mid) if status=='PASS' else None,state_evidence=[self._ref(token,'state',mid)]))
        if kind in ('output','meter_link','provider'):
            entry=next((e for e in inventory['operations'] if e['operation_id']==op),None)
            if entry is None:raise Unavailable('ORIGINAL_OPERATION_UNAVAILABLE')
            if kind=='output':
                raw=self._output(token,mid,op)
                if raw is None:raise Unavailable('ORIGINAL_COMPLETE_OUTPUT_UNAVAILABLE')
                return raw
            if kind=='meter_link':
                meter=decode(self.originals.meter(token,mid,op));command=meter['command']
                try:output=self._output(token,mid,op)
                except Unavailable as error:
                    if str(error)!='ORIGINAL_PAYLOAD_ERASED':raise
                    output=None
                return encode(dict(attempt_id=entry['attempt_id'],operation_id=op,run_id=inventory['run_id'],
                    registration_id=entry['registration_id'],kind=entry['kind'],
                    input_sha256=command['input_digest'],output_sha256=None if output is None else sha256(output).hexdigest(),
                    binding_sha256=self.binding.key,status=meter['state'].upper(),original_meter=meter))
            fee=self._fee(token,mid,op)
            if fee is None or fee['state']!='RECEIVED':raise Unavailable('ORIGINAL_PROVIDER_RECEIPT_UNAVAILABLE')
            # OriginalReader checks the actual wire hash and output against the
            # same fee receipt, preserving logical input != HTTP body hash.
            artifact=decode(self.originals.artifact(token,mid,op))
            result=dict(attempt_id=entry['attempt_id'],input_sha256=artifact['input_sha256'],
                response_sha256=artifact['response_sha256'],original_receipt=artifact['receipt'])
            if entry['kind'] in ('model','memory'):
                wire=decode(self.originals.artifact(token,mid,op,wire_input=True))
                result.update(model=self.model_reader(token,mid,op),
                    actual_wire_input_sha256=wire['wire_input_sha256'],wire_input=self._ref(token,'wire_input',mid,op))
            return encode(result)
        association=dict(binding_sha256=self.binding.key,client_step_id=mid,
            request_sha256=digest(request),message_id=mid,action_id=None,run_ids=[inventory['run_id']])
        if kind=='protected_inventory':
            return encode(dict(**association,operation_ids=[e['operation_id'] for e in inventory['operations']]))
        if kind in ('state','result') and any(e['input_erased'] for e in inventory['operations']):
            raise Unavailable('ORIGINAL_PAYLOAD_ERASED')
        if kind=='state':return self.state_reader(token,mid)
        if kind=='result':
            if preparatory_message(request):return self.dialogue.setup(request,deadline=self.clock()+30)
            if request['kind']=='reflection':
                if len(inventory['operations'])!=1:raise Unavailable('REFLECTION_ORIGINAL_COUNT')
                entry,=inventory['operations']
                if (entry['kind'],entry['registration_id'])!=('model','model.runtime_reflection.1'):
                    raise Unavailable('REFLECTION_ORIGINAL_REGISTRATION')
                output=self._output(token,mid,entry['operation_id'])
                if output is None:raise Unavailable('ORIGINAL_COMPLETE_OUTPUT_UNAVAILABLE')
                return output
            return self.state_reader(token,mid)
        if kind!='action':raise Unavailable('RUNTIME_COLLECTOR_PROJECTION_NOT_CONNECTED')
        status={'completed':'PASS','failed':'FAIL','cancelled':'CANCELLED','running':'RUNNING',
                'queued':'RUNNING','context_invalid':'FAIL','unknown':'UNKNOWN'}.get(inventory['status'],'UNKNOWN')
        if status=='PASS' and preparatory_message(request):
            if any(entry['input_erased'] for entry in inventory['operations']):status='UNKNOWN'
            else:
                try:status=decode(self.dialogue.setup(request,deadline=self.clock()+30))['status']
                except (Unavailable,Invalid,OSError):status='UNKNOWN'
        result=None
        if status=='PASS':
            try:result=self._ref(token,'result',mid)
            except (Unavailable,Invalid,OSError):status='UNKNOWN'
        try:state_evidence=[self._ref(token,'state',mid)]
        except (Unavailable,Invalid,OSError):
            status='UNKNOWN';state_evidence=[]
        for entry in inventory['operations']:
            if entry['registration_id']=='tool.weather':
                try:
                    record=decode(self.originals.artifact(token,mid,entry['operation_id']))
                    if record['version']=='G2C-runtime-weather-fault.1':
                        state_evidence.append(self._ref(token,'artifact',mid,entry['operation_id']))
                except (Unavailable,Invalid,OSError):pass
        return encode(dict(**association,status=status,inventory=self._ref(token,'protected_inventory',mid),
            result=result,state_evidence=state_evidence))

    def inspect(self,attempt_id,step_id,*,deadline):
        self.guard(read_only=True)
        if self.clock()>=deadline:raise Unavailable('DEADLINE_REACHED')
        token=self.token_supplier();request,inventory=self._source(token,step_id)
        if request['attempt_id']!=attempt_id:raise Unavailable('RUNTIME_COLLECTOR_ATTEMPT_CHANGED')
        action=decode(self.projection(token,'action',step_id,None))
        operations=[] if inventory is None else [self._operation(token,step_id,inventory,e) for e in inventory['operations']]
        body=encode(dict(version=VERSION,attempt_id=attempt_id,step_id=step_id,
            request_sha256=digest(request),binding_sha256=self.binding.key,pins_sha256=self.pins.key,
            status=action['status'],message_id=action['message_id'],run_ids=action['run_ids'],action_id=action['action_id'],
            action=self._ref(token,'action',step_id),inventory=action['inventory'],operations=operations,
            result=action['result'],state_evidence=action['state_evidence']))
        if inventory is not None and decode(self.originals.inventory(token,step_id))!=inventory:
            raise Unavailable('ORIGINAL_SNAPSHOT_CHANGED')
        self.guard(read_only=True)
        if self.clock()>=deadline:raise Unavailable('DEADLINE_REACHED')
        return body

    def original(self,reference,*,deadline):
        if self.clock()>=deadline:raise Unavailable('DEADLINE_REACHED')
        body=self.refs.resolve(self.token_supplier(),reference)
        if self.clock()>=deadline:raise Unavailable('DEADLINE_REACHED')
        return body
