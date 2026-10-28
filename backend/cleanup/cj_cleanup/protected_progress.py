"""Current authenticated account's existing cleanup progress; no write/wire authority."""
from dataclasses import dataclass
import re
from . import core

INTERFACE = 'CJ-CLEANUP-PROGRESS-READ@0.1.0-rc.2'

_TARGET = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,191}\Z')

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


def _project(op, max_steps):
    # op comes from Repository.query (scope + operation ID bound there). Persisted
    # fields are not validated by journal replay, so the output whitelist is checked here.
    if len(op.steps)>max_steps:
        raise ProgressUnavailable('original progress unavailable')
    # request() derives step.available as `hook_available and ...`, so a persisted
    # non-bool would either pass through (null) or be coerced (truthy string).
    if any(type(e.hook_available) is not bool for e in op.manifest.entries):
        raise ProgressUnavailable('original progress unavailable')
    steps=[]
    for index,step in enumerate(op.steps):
        if not _TARGET.fullmatch(step.target) or type(step.available) is not bool:
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


def _no_stage_check(stage=None):
    # Fresh AUTH at entry and before bytes escape is enforced by ProtectedReadBoundary.
    pass


class ProgressReader:
    def __init__(self,boundary,resolve_repository,*,configuration):
        self.boundary,self.resolve_repository,self.configuration=boundary,resolve_repository,configuration

    def read(self,token,operation_id,*,project=None):
        """Request inputs: token + original operation ID only.

        resolve_repository(principal, environment, guard) -> existing canonical PG
        Repository with derived Scope and that guard. Resolver/project are trusted
        host callbacks; project must encode the entire final response here.
        """
        core.identifier(operation_id)
        config=self.configuration

        def operation(ctx):
            principal=ctx.principal
            if principal.issuer!=config.issuer or principal.audience!=config.audience:
                raise ProgressUnavailable('host identity profile mismatch')
            scope=core.Scope.from_principal(config.environment,principal)
            repo=self.resolve_repository(principal,config.environment,_no_stage_check)
            if repo.scope!=scope:
                raise ProgressUnavailable('original scope binding required')
            op=repo.query(operation_id) # SELECT-only path: never create/recover/intent/receipt
            result=_project(op,config.max_steps)
            if project is not None:
                result=project(result) # whole BASE envelope must be encoded within ctx
            if type(result) is not bytes: raise ProgressUnavailable('final progress bytes required')
            if len(result)>config.max_response_bytes: raise ProgressUnavailable('progress response too large')
            return result

        return self.boundary.with_read_context(token,operation)


def post_logout_query(*args,**kwargs):
    raise ProgressUnavailable('post-logout progress credential contract unavailable')
