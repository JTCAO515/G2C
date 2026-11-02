"""Explicit local-only CLEANUP API composition. No cloud/key/account defaults."""
from dataclasses import dataclass,asdict,replace
from hashlib import sha256
import json,os,stat,time
from pathlib import Path
import psycopg
from cj_auth.interfaces import Fact
from cj_auth.admission import AdmissionChecker
from cj_auth.jwt_adapter import PyJWTVerifier
from cj_auth.account_revocation import AccountRevocationAccess
from cj_cleanup.core import Scope,encode,digest,Denied
from cj_cleanup.capabilities import Issuer
from cj_cleanup.registry import freeze
from cj_cleanup.store import Store
from cj_cleanup.gateway import Gateway,Binding
from cj_cleanup.gateway_store import GatewayStore
from cj_cleanup.account_hooks import DomainHook,UsageHook,MESSAGE,RUN,NEEDS
from cj_cleanup.device_bridge import DeviceHook
from cj_cleanup.metadata_hook import MetadataHook
from cj_feedback.lifecycle import FeedbackHook
from cj_message.needs_binding import needs_scope_for
from cj_agent.draft import trip_scope_for
from cj_run.step_usage import ledger_scope_for
from cj_run.account_stop import stop_scope


@dataclass(frozen=True,repr=False)
class Configuration:
    keys:dict
    key_id:str
    lifetime_seconds:int
    inventory:tuple[str,...]
    registry_path:Path
    clock:object=time.time
    extra_hooks:object=None


def load_configuration(path):
    value=json.loads(Path(path).read_text())
    if set(value)!={'version','key_file','key_id','lifetime_seconds','inventory'} or value['version']!='CJ-LOCAL-CLEANUP@1':
        raise ValueError('explicit local cleanup configuration required')
    fd=os.open(value['key_file'],os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError('private local cleanup key file required')
        key=os.read(fd,4097)
    finally:os.close(fd)
    if len(key)!=32:raise ValueError('32-byte local cleanup key required')
    return Configuration({value['key_id']:key},value['key_id'],value['lifetime_seconds'],tuple(value['inventory']),
                         Path(__file__).resolve().parents[1]/'storage-registry.json')


class Runtime:
    def __init__(self,database,configuration,scope_for):
        self.database,self.configuration,self.scope_for=database,configuration,scope_for
        self.issuer=Issuer(keys=configuration.keys,active_key_id=configuration.key_id,
                           lifetime_seconds=configuration.lifetime_seconds,clock=configuration.clock)

    def registry(self):
        return freeze(self.configuration.registry_path.read_bytes(),self.configuration.inventory,
                      versions=('CLEANUP@1.0','CLEANUP@1.1'))

    def connect(self):
        options=dict(self.database.conninfo,user='cj_local_cleanup')
        return psycopg.connect(**options)

    def subject(self,principal):return digest(encode(asdict(Scope.from_principal('local',principal))))

    def retired(self,principal):
        subject=self.subject(principal)
        with self.connect() as conn:
            conn.execute("SELECT set_config('cj.cleanup_subject',%s,true)",(subject,))
            row=conn.execute('SELECT 1 FROM cj_account_fence WHERE subject_digest=%s',(subject,)).fetchone()
        return Fact.YES if row is not None else Fact.NO

    def bind(self,principal):
        binding=self._binding(self.subject(principal),self.scope_for(principal.issuer,principal.subject))
        def erase_http_plan(cur,request):
            suffix='' if request.selection.kind=='account' else ' AND operation_id=%s'
            values=(request.subject_digest,) if not suffix else (request.subject_digest,request.operation_id)
            cur.execute('UPDATE cj_cleanup_request SET plan_bytes=NULL WHERE subject_digest=%s'+suffix,values)
        binding.hooks['business/cleanup-metadata']=MetadataHook(binding.store,encode(asdict(Scope.from_principal('local',principal))),
            additional_erasure=erase_http_plan)
        return binding

    def by_subject(self,subject):
        # Restricted progress needs no plaintext identity after metadata erasure.
        store=Store(self.connect,subject,lambda stage:None)
        return Binding(store,'',(),{}, {},lambda operation:False)

    def original(self,subject,operation_id):
        from .local_app import ISSUER,AUDIENCE
        metadata=GatewayStore(Store(self.connect,subject,lambda stage:None))
        prepared=metadata.query(operation_id)
        if prepared.plan_bytes is None:return self.by_subject(subject)
        plan=json.loads(prepared.plan_bytes)
        candidates=[v['domain_scope'] for k,v in plan.items() if k in ('business/message','checkpoints/run','business/feedback-private-actions')]
        if not candidates or len(set(candidates))!=1:raise Denied('original owner namespace unavailable')
        owner=candidates[0]
        prefix='local:'+ISSUER+':'
        if not owner.startswith(prefix):raise Denied('original local namespace unavailable')
        legacy=encode(asdict(Scope('local',ISSUER,owner.removeprefix(prefix),AUDIENCE)))
        if digest(legacy)!=subject:raise Denied('original principal scope mismatch')
        binding=self._binding(subject,owner)
        def erase(cur,request):cur.execute('UPDATE cj_cleanup_request SET plan_bytes=NULL WHERE subject_digest=%s',(subject,))
        binding.hooks['business/cleanup-metadata']=MetadataHook(binding.store,legacy,additional_erasure=erase)
        return replace(binding,plan=plan)

    def _binding(self,subject,owner):
        # Authority came from the caller's canonical verified principal. The
        # dedicated store's guard covers only this captured cleanup context.
        store=Store(self.connect,subject,lambda stage:None)
        needs=needs_scope_for(owner);trip=trip_scope_for(owner)
        profiles=() if self.database.run_context is None else self.database.run_context.profiles
        ledgers=tuple(ledger_scope_for(owner,p.meter) for p in profiles)
        namespaces=(owner,needs,trip,*ledgers)
        hooks={'business/message':DomainHook(store,owner,MESSAGE),'checkpoints/run':DomainHook(store,owner,RUN),
               'business/needs-current-planning':DomainHook(store,needs,NEEDS),
               'business/usage':UsageHook(store,owner,ledgers),
               'business/feedback-private-actions':FeedbackHook(store,owner)}
        from cj_memory_jobs.cleanup import CleanupHook
        hooks['memory-derived']=CleanupHook(store,owner)
        devices=DeviceHook(GatewayStore(store),self.issuer)
        plan={}
        for target in self.configuration.inventory:
            scope=trip if target=='business/trip-authoritative' else needs if target=='business/needs-current-planning' else subject if target=='business/cleanup-metadata' or target.startswith('device-cache/') or target=='external-processing' else owner
            plan[target]={'domain_scope':scope,'selection':{'kind':'account'}}
            if target.startswith('device-cache/'):hooks[target]=devices
        if self.configuration.extra_hooks is not None:hooks.update(self.configuration.extra_hooks(store,owner))
        def stop(operation):
            with store.transaction(operation) as cur:
                cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",(owner,))
                return stop_scope(cur,owner)
        return Binding(store,owner,namespaces,plan,hooks,stop)

    def gateway(self,jwt_configuration,verification_keys,access):
        checker=AdmissionChecker(PyJWTVerifier(jwt_configuration,verification_keys),AccountRevocationAccess(access,self.retired))
        return self.host_gateway(checker)

    def host_gateway(self,checker):
        """Explicit local host composition, also used by the original-op worker."""
        return Gateway(checker=checker,resolve_principal=self.bind,resolve_subject=self.by_subject,resolve_original=self.original,
                       current_registry=self.registry,issuer=self.issuer,clock=self.configuration.clock)
