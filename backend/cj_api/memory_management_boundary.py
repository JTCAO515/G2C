"""Candidate restricted lifecycle consumer; reuse the existing root MEMORY guard."""
from dataclasses import dataclass
from .composition import CompositionUnavailable, _internal_modules
from .memory_boundary import MemoryBoundary

@dataclass(frozen=True)
class MemoryManagementConfiguration:
    max_body_bytes: int
    max_private_response_bytes: int
    def __post_init__(self):
        for value, cap in ((self.max_body_bytes,32768),(self.max_private_response_bytes,65536)):
            if type(value) is not int or not 1 <= value <= cap:
                raise CompositionUnavailable('Explicit bounded lifecycle configuration required')

class MemoryManagementBoundary(MemoryBoundary):
    def _service_type(self):
        return self.modules['cj_memory_management.guarded'].GuardedService
    def _command(self, kind, argument):
        return self.modules['cj_memory_management.domain'].Action.parse(argument) if kind=='save' else None
    def _context_value(self, context, kind, argument):
        if kind=='save':return context.apply(argument)
        if kind=='query':return context.query(argument)
        raise ValueError('Restricted pause/resume/query only')

# This neutral adapter adds no source approval: the fixed lifecycle provider alone
# checks existing source bytes/revisions/expiry. It exposes no manual/save context.
def _existing_source_only(*args):return True

def _candidate_boundary_from_checker(*,environment,checker,resolve_binding):
    """Internal review harness assembly only; not an enabled application factory."""
    modules=_internal_modules('memory_management')
    if environment!='local' or not isinstance(checker,modules['cj_auth.admission'].AdmissionChecker) or not callable(resolve_binding):
        raise CompositionUnavailable('Canonical checker and existing trusted MEMORY binding required')
    return MemoryManagementBoundary(checker,resolve_binding,_existing_source_only,modules)

def create_memory_management_app(*,configuration,environment,jwt_configuration,verification_keys,access_provider,resolve_binding):
    # No wire flag, host boolean, environment variable or checker can bypass pending gates.
    raise CompositionUnavailable('CJ019 a7 / CJ011 0045 independent gates pending; lifecycle factory closed')
