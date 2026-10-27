"""Trusted historical read assembly; creates canonical AUTH lifetime per invocation."""
from dataclasses import dataclass
from .composition import CompositionUnavailable,_internal_modules

@dataclass(frozen=True)
class UsageStatusConfiguration:
    period_start:int
    period_end:int
    max_attempt_id_bytes:int
    max_response_bytes:int
    def __post_init__(self):
        if (type(self.period_start) is not int or self.period_start<0 or type(self.period_end) is not int
                or self.period_end<=self.period_start or any(type(n) is not int or n<1 for n in (self.max_attempt_id_bytes,self.max_response_bytes))):
            raise CompositionUnavailable('Explicit historical period and positive read limits required')

def _usage_status_from_checker(checker,resolve,configuration,*,environment,issuer,audience):
    modules=_internal_modules('usage_status')
    if (environment!='local' or not isinstance(checker,modules['cj_auth.admission'].AdmissionChecker)
            or not callable(resolve) or type(configuration) is not UsageStatusConfiguration):
        raise CompositionUnavailable('Canonical checker, trusted historical resolver and explicit config required')
    source=modules['cj_usage.protected_status']
    host=source.StatusReadConfiguration(environment,issuer,audience,configuration.period_start,configuration.period_end,configuration.max_response_bytes)
    return checker,resolve,host,modules

def build_usage_status_dependencies(*,environment,jwt_configuration,verification_keys,access_provider,resolve,configuration):
    if (environment!='local' or not callable(resolve) or not callable(getattr(verification_keys,'resolve',None))
            or not callable(getattr(access_provider,'evaluate',None))):
        raise CompositionUnavailable('Explicit local read AUTH and resolver required')
    modules=_internal_modules('usage_status');auth=modules['cj_auth.jwt_adapter']
    if not isinstance(jwt_configuration,auth.JWTConfiguration) or jwt_configuration.profile is not auth.JWTProfile.STRICT_V1:
        raise CompositionUnavailable('Fixed strict AUTH profile required')
    checker=modules['cj_auth.admission'].AdmissionChecker(auth.PyJWTVerifier(jwt_configuration,verification_keys),access_provider)
    return _usage_status_from_checker(checker,resolve,configuration,environment=environment,issuer=jwt_configuration.issuer,audience=jwt_configuration.audience)

def create_usage_status_app(*,configuration,**dependencies):
    assembly=build_usage_status_dependencies(configuration=configuration,**dependencies)
    from .app import create_app
    return create_app(_usage_status_configuration=configuration,_usage_status_dependencies=assembly)
