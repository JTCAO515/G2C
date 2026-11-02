"""CLEANUP-API@1. HTTP-facing orchestration over explicit trusted host bindings."""
from dataclasses import dataclass
import json
from cj_auth.interfaces import AdmissionStatus
from .core import Denied,Conflict,digest
from .coordinator import Coordinator
from .gateway_store import GatewayStore
from .device_bridge import DeviceBridge

VERSION='CLEANUP-API@1'


@dataclass(frozen=True,repr=False)
class Binding:
    store:object
    owner_scope:str
    namespaces:tuple[str,...]
    plan:dict
    hooks:dict
    stop_tasks:object


class Gateway:
    def __init__(self,*,checker,resolve_principal,resolve_subject,resolve_original,current_registry,issuer,clock):
        self.checker,self.resolve_principal,self.resolve_subject=checker,resolve_principal,resolve_subject
        self.current_registry,self.issuer,self.clock=current_registry,issuer,clock
        self.resolve_original=resolve_original

    def _ordinary(self,token):
        decision=self.checker.check(token)
        if decision.status is not AdmissionStatus.ALLOWED:raise Denied('ordinary account access unavailable')
        return decision.principal,self.resolve_principal(decision.principal)

    def _same(self,token,principal):
        current=self.checker.check(token)
        if current.status is not AdmissionStatus.ALLOWED or current.principal!=principal:
            raise Denied('ordinary account access unavailable')

    def register_device(self,token,action_id,input_digest,device_id,state_ref,project):
        principal,binding=self._ordinary(token)
        metadata=GatewayStore(binding.store)
        result=metadata.register_device(action_id,input_digest,device_id,state_ref)
        result.update(version='CLEANUP-DEVICE@1',device_token=self.issuer.issue(subject_digest=binding.store.subject_digest,
            operation_id=result['binding_id'],binding_id=result['binding_id'],purpose='device'),
            server_time=int(self.clock()),business_access='not_granted')
        encoded=project(result);self._same(token,principal)
        return encoded

    def prepare(self,token,action_id,input_digest,binding_id,project):
        principal,binding=self._ordinary(token)
        manifest=self.current_registry()
        prepared=GatewayStore(binding.store).prepare(action_id,input_digest,manifest,binding.plan,binding_id)
        result=dict(version=VERSION,operation_id=prepared.operation_id,phase=prepared.phase,
            registry_digest=digest(prepared.registry_bytes),plan_digest=prepared.plan_digest,binding_id=prepared.binding_id,
            revision=prepared.revision,confirmation='DELETE_ACCOUNT',
            progress_token=self.issuer.issue(subject_digest=binding.store.subject_digest,
                operation_id=prepared.operation_id,binding_id=prepared.binding_id,purpose='progress'))
        encoded=project(result);self._same(token,principal)
        return encoded

    def preparation(self,token,action_id,project):
        principal,binding=self._ordinary(token)
        prepared=GatewayStore(binding.store).by_action(action_id)
        result=None if prepared is None else dict(operation_id=prepared.operation_id,phase=prepared.phase,
            registry_digest=digest(prepared.registry_bytes),plan_digest=prepared.plan_digest,binding_id=prepared.binding_id,
            progress_token=self.issuer.issue(subject_digest=binding.store.subject_digest,operation_id=prepared.operation_id,
                binding_id=prepared.binding_id,purpose='progress'),revision=prepared.revision)
        encoded=project(dict(version=VERSION,preparation=result));self._same(token,principal)
        return encoded

    def confirm(self,token,operation_id,registry_digest,confirmation,input_digest,project):
        principal,binding=self._ordinary(token)
        if confirmation!='DELETE_ACCOUNT':raise Denied('explicit account confirmation required')
        metadata=GatewayStore(binding.store);prepared=metadata.query(operation_id)
        current=self.current_registry()
        if digest(prepared.registry_bytes)!=registry_digest or current.raw!=prepared.registry_bytes:
            raise Conflict('cleanup scope changed; confirm a new explicit preparation')
        if prepared.plan_bytes is None:raise Denied('original confirmed plan unavailable')
        plan=json.loads(prepared.plan_bytes)
        coordinator=Coordinator(binding.store,self.current_registry,binding.hooks)
        progress=coordinator.create(operation_id,input_digest,'account',plan)
        if progress['status']=='blocked':
            # Readiness failure is not account revocation or deletion success.
            return project(dict(version=VERSION,operation_id=operation_id,phase='prepared',status='blocked',
                steps=progress['steps'],reason='domain_hooks_unavailable',business_access='unchanged'))
        metadata.confirm(operation_id,input_digest,current,owner_scope=binding.owner_scope,namespaces=binding.namespaces,
                         check_admission=lambda:self._same(token,principal))
        # From here only this captured original cleanup context may continue.
        self._continue_original(binding,operation_id,plan,current)
        DeviceBridge(metadata,self.issuer).call(prepared.binding_id,'account_cleanup',operation_id=operation_id)
        return project(self._progress(binding,operation_id))

    def _continue_original(self,binding,operation_id,plan,current):
        # Every execution/resumption entrance passes the same preflight. In
        # particular, a device report is never authority to erase a live worker
        # or its unresolved accounting evidence.
        metadata=GatewayStore(binding.store)
        if binding.stop_tasks(operation_id) is not True:
            metadata.record_gate(operation_id,'original_tasks_not_yet_stopped')
            return
        if 'business/usage' in plan:
            try:binding.hooks['business/usage'].require_settled(operation_id)
            except Denied:
                metadata.record_gate(operation_id,'original_usage_outcome_unresolved')
                return
        metadata.record_gate(operation_id,None)
        self._run_original(binding,operation_id,plan,current)

    def resume(self,subject_digest,operation_id):
        """Trusted host job only: re-open the captured original, never fresh AUTH.

        HTTP progress remains observational. Pending intents may dispatch once;
        committed/unknown intents only reconcile their original result.
        """
        binding=self.resolve_original(subject_digest,operation_id)
        metadata=GatewayStore(binding.store)
        if metadata.active_operation()!=operation_id:raise Denied('original active operation required')
        prepared=metadata.query(operation_id)
        if prepared.plan_bytes is not None:
            self._continue_original(binding,operation_id,json.loads(prepared.plan_bytes),self.current_registry())
        return self._progress(binding,operation_id)

    def _run_original(self,binding,operation_id,plan,current):
        coordinator=Coordinator(binding.store,self.current_registry,binding.hooks)
        order=('memory-derived','business/memory-management-actions','business/memory-authoritative',
               'business/trip-authoritative','checkpoints/run','business/message','business/needs-current-planning','business/usage')
        targets=sorted(plan,key=lambda t:order.index(t) if t in order else len(order))
        if 'business/cleanup-metadata' in targets:
            targets.remove('business/cleanup-metadata');targets.append('business/cleanup-metadata')
        for target in targets:
            selected=plan[target]
            from .store import CODECS
            entry=next(e for e in current.entries if e.registry_id==target)
            request=coordinator.request(operation_id,target,selected['domain_scope'],
                CODECS[entry.protocol].Selection.from_dict(selected['selection']))
            observed=coordinator.query(operation_id)
            state=next(s['state'] for s in observed['steps'] if s['target']==target)
            if state=='confirmed':continue
            result=coordinator.advance(request) if state=='pending' else coordinator.reconcile(request)
            if next(s['state'] for s in result['steps'] if s['target']==target)!='confirmed':return

    def _progress(self,binding,operation_id):
        metadata=GatewayStore(binding.store);active=metadata.active_operation()
        if active is not None and active!=operation_id:raise Denied('query original operation only')
        prepared=metadata.query(operation_id)
        if prepared.phase=='prepared':
            return dict(version=VERSION,operation_id=operation_id,phase='prepared',status='awaiting_confirmation',revision=prepared.revision,steps=[])
        Coordinator(binding.store,self.current_registry,binding.hooks).query(operation_id)
        prepared,progress,devices,reason=metadata.snapshot(operation_id)
        # No online-domain result is relabelled as backup/all-device erasure.
        aggregate=progress['status'] if progress['status'] in ('blocked','unknown','failed') else 'unknown' if reason else 'in_progress'
        result=dict(version=VERSION,operation_id=operation_id,phase=prepared.phase,status=aggregate,online_status=progress['status'],
            revision=prepared.revision,steps=progress['steps'],devices=devices,
            obligations=dict(backups='unverified_30_day_rolling',other_devices='pending_actual_receipts',external='unverified'),
            complete_scope='frozen_online_domains_only',business_access='revoked')
        if reason is not None:result['reason']=reason
        return result

    def progress(self,capability,operation_id,project):
        claims=self.issuer.verify(capability,purpose='progress',operation_id=operation_id)
        binding=self.resolve_subject(claims.subject_digest)
        prepared=GatewayStore(binding.store).query(operation_id)
        if prepared.binding_id!=claims.binding_id:raise Denied('original progress credential required')
        return project(self._progress(binding,operation_id))

    def device_call(self,capability,binding_id,reason,project):
        claims=self.issuer.verify(capability,purpose='device',operation_id=binding_id,binding_id=binding_id)
        binding=self.resolve_subject(claims.subject_digest)
        return project(DeviceBridge(GatewayStore(binding.store),self.issuer).call(binding_id,reason))

    def device_receipt(self,capability,action_id,operation_id,invocation_id,binding_id,request_digest,outcome,raw,project):
        claims=self.issuer.verify(capability,purpose='device_receipt',operation_id=operation_id,
            invocation_id=invocation_id,binding_id=binding_id)
        binding=self.resolve_subject(claims.subject_digest)
        bridge=DeviceBridge(GatewayStore(binding.store),self.issuer)
        report=bridge.receipt(claims,action_id,request_digest,outcome,raw)
        metadata=GatewayStore(binding.store)
        if metadata.active_operation()==operation_id:
            original=self.resolve_original(claims.subject_digest,operation_id)
            prepared=metadata.query(operation_id)
            if prepared.plan_bytes is not None:
                self._continue_original(original,operation_id,json.loads(prepared.plan_bytes),self.current_registry())
        return project(report)

    def device_query(self,capability,invocation_id,project):
        claims=self.issuer.verify(capability,purpose='device')
        if claims.operation_id!=claims.binding_id:raise Denied('original device credential required')
        binding=self.resolve_subject(claims.subject_digest)
        return project(DeviceBridge(GatewayStore(binding.store),self.issuer).query(invocation_id,claims.binding_id))
