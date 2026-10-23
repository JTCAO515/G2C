"""Current authenticated account's existing cleanup progress; no write/wire authority."""
from dataclasses import dataclass, asdict
import inspect
import re
from cj_auth.read_context import (READ_CONTEXT_VERSION, ProtectedReadBoundary,
                                  ProtectedReadContext)
from . import core
from .postgres import Repository

INTERFACE = 'CJ-CLEANUP-PROGRESS-READ@0.1.0-rc.1'
AUTH_READ = 'CJ-AUTH-READ-CONTEXT@0.1.0-rc.1'
_TARGET = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,191}\Z')
_STATUS = ('blocked','unknown','failed','complete','awaiting_revocation','in_progress')

class ProgressUnavailable(Exception): pass

@dataclass(frozen=True)
class Configuration:
    environment: str
    issuer: str
    audience: str
    max_steps: int
    max_response_bytes: int

    def __post_init__(self):
        core.identifier(self.environment)
        for value in (self.issuer,self.audience):
            if type(value) is not str or not value or len(value)>2048:
                raise ProgressUnavailable('explicit host configuration required')
        if (type(self.max_steps) is not int or not 1 <= self.max_steps <= 128
                or type(self.max_response_bytes) is not int or not 1 <= self.max_response_bytes <= 65536):
            raise ProgressUnavailable('explicit bounded projection required')


def _configuration(config):
    return (config.environment,config.issuer,config.audience,config.max_steps,config.max_response_bytes)


def _project(op, scope, operation_id, max_steps):
    if (type(op) is not core.Operation or op.scope != scope or op.operation_id != operation_id
            or type(op.revision) is not int or op.revision<0 or op.status not in _STATUS
            or not op.steps or len(op.steps)>max_steps):
        raise ProgressUnavailable('original progress unavailable')
    steps=[]
    for index,step in enumerate(op.steps):
        if (type(step) is not core.Step or type(step.target) is not str or not _TARGET.fullmatch(step.target)
                or step.state not in core.STATES or type(step.available) is not bool):
            raise ProgressUnavailable('original progress unavailable')
        if step.state=='confirmed': reason='original_result_confirmed'
        elif step.state=='unknown': reason='original_result_unknown'
        elif step.state=='failed': reason='original_result_failed'
        elif not step.available: reason='hook_unavailable'
        elif step.state=='in_progress': reason='original_call_in_progress'
        elif index>0 and op.steps[0].state!='confirmed': reason='revocation_unconfirmed'
        elif index>=len(core.BARRIERS) and op.steps[1].state!='confirmed': reason='task_stop_unconfirmed'
        else: reason='pending_original_result'
        steps.append(dict(target=step.target,state=step.state,reason=reason))
    reasons=[]
    # Never echo free-form gap details from metadata or infer missing hooks as zero.
    if op.manifest.gaps: reasons.append('coverage_incomplete')
    if op.gaps: reasons.append('registry_review_required')
    if any(not s.available for s in op.steps): reasons.append('hook_unavailable')
    if any(s.state=='unknown' for s in op.steps): reasons.append('original_result_unknown')
    if any(s.state=='failed' for s in op.steps): reasons.append('original_result_failed')
    return core.encode(dict(operation_id=op.operation_id,revision=op.revision,status=op.status,
                            steps=steps,reasons=reasons))


class ProgressReader:
    def __init__(self,boundary,resolve_repository,*,configuration):
        if (READ_CONTEXT_VERSION != AUTH_READ or type(boundary) is not ProtectedReadBoundary
                or not callable(resolve_repository) or type(configuration) is not Configuration):
            raise ProgressUnavailable('canonical AUTH and explicit host composition required')
        self.boundary,self.resolve_repository,self.configuration=boundary,resolve_repository,configuration

    def read(self,token,operation_id,*,project=None):
        """Request inputs: token + original operation ID only.

        resolve_repository(principal, environment, guard) -> existing canonical PG
        Repository with derived Scope and that exact guard. Resolver/project are
        trusted host callbacks; project must encode the entire final response here.
        """
        core.identifier(operation_id)
        if project is not None and (not callable(project) or inspect.iscoroutinefunction(project)):
            raise ProgressUnavailable('synchronous final projection required')
        boundary,resolver,config=self.boundary,self.resolve_repository,self.configuration
        config_values=_configuration(config)
        completed=None

        def frozen_binding():
            # No external callbacks, context access, checks, project or IO here.
            if (self.boundary is not boundary or self.resolve_repository is not resolver
                    or self.configuration is not config or _configuration(config)!=config_values):
                raise ProgressUnavailable('progress host binding changed')
            if completed is not None:
                repo,scope,connect,guard,scope_bytes=completed
                if (repo.scope!=scope or repo.connect is not connect or repo.guard is not guard
                        or repo._scope_bytes!=scope_bytes):
                    raise ProgressUnavailable('progress repository binding changed')

        def operation(ctx):
            nonlocal completed
            if type(ctx) is not ProtectedReadContext: raise ProgressUnavailable('canonical context required')
            principal=ctx.principal
            if principal.issuer!=config.issuer or principal.audience!=config.audience:
                raise ProgressUnavailable('host identity profile mismatch')
            scope=core.Scope.from_principal(config.environment,principal)

            def guard(stage=None):
                ctx.require_current()
                frozen_binding() # after every canonical AUTH provider callback

            guard()
            repo=resolver(principal,config.environment,guard)
            guard()
            if type(repo) is not Repository:
                if inspect.iscoroutine(repo): repo.close()
                raise ProgressUnavailable('canonical progress repository required')
            if repo.scope!=scope or repo.guard is not guard or repo._scope_bytes!=core.encode(asdict(scope)):
                raise ProgressUnavailable('original scope binding required')
            completed=(repo,scope,repo.connect,repo.guard,repo._scope_bytes)
            op=repo.query(operation_id) # SELECT-only path: never create/recover/intent/receipt
            guard() # query has already completed external close/its final guard
            result=_project(op,scope,operation_id,config.max_steps)
            if project is not None:
                result=project(result) # whole BASE envelope must be encoded within ctx
            if type(result) is not bytes:
                if inspect.iscoroutine(result): result.close()
                raise ProgressUnavailable('final progress bytes required')
            if len(result)>config.max_response_bytes: raise ProgressUnavailable('progress response too large')
            guard() # projection callback can revoke/swap binding too
            return result

        result=boundary.with_read_context(token,operation)
        # Last AUTH callback can change host/repository despite returning ALLOWED.
        # Context is now retired; only inspect captured plain canonical fields.
        if completed is None: raise ProgressUnavailable('original progress binding unavailable')
        frozen_binding()
        return result


def post_logout_query(*args,**kwargs):
    raise ProgressUnavailable('post-logout progress credential contract unavailable')
