"""Explicitly injected CLEANUP@1.0 host. Account authorization/barriers are #27."""
from .core import Denied, digest
from .hooks import HookRequest, Selection, make_request


class Coordinator:
    def __init__(self,store,current_registry,hooks):
        self.store,self.current_registry,self.hooks=store,current_registry,hooks

    def create(self,operation_id,confirmation_digest,purpose,plan):
        """Host verified explicit confirmation of this exact registry AND selection plan."""
        manifest=self.current_registry()
        self.store.create(operation_id,confirmation_digest,manifest,purpose,tuple(self.hooks),plan)
        return self.query(operation_id)

    def query(self,operation_id):
        # Never report complete against a stale or drifted registry.
        self.store.audit(operation_id,self.current_registry())
        return self.store.query(operation_id)

    def request(self,operation_id,target,domain_scope,selection):
        manifest=self.current_registry()
        entry=next((e for e in manifest.entries if e.registry_id==target),None)
        if entry is None:raise Denied('cleanup target unavailable')
        # Stable within the original operation and target; no unknown retry IDs.
        invocation='hook-'+digest((operation_id+'\0'+target).encode('utf-8'))
        return make_request(operation_id=operation_id,invocation_id=invocation,
            subject_digest=self.store.subject_digest,registry_digest=manifest.digest,
            entry_digest=entry.version,target=target,domain_scope=domain_scope,selection=selection)

    def advance(self,request:HookRequest):
        if self.query(request.operation_id)['status']=='blocked' or request.target not in self.hooks:
            raise Denied('cleanup hook unavailable')
        if self.store.intent(request):
            # Intent COMMIT has completed. A repeat advance never redispatches.
            result=self.hooks[request.target].execute(request)
            self.store.receipt(request,result)
        return self.query(request.operation_id)

    def reconcile(self,request:HookRequest):
        if self.query(request.operation_id)['status']=='blocked' or request.target not in self.hooks:
            raise Denied('cleanup hook unavailable')
        result=self.hooks[request.target].reconcile(request)
        self.store.receipt(request,result)
        return self.query(request.operation_id)
