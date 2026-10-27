"""Current-account read assembly; no destructive factory or credential recovery."""
from dataclasses import dataclass
from .composition import CompositionUnavailable,_internal_modules

@dataclass(frozen=True)
class CleanupProgressConfiguration:
    max_steps:int
    max_response_bytes:int
    def __post_init__(self):
        if type(self.max_steps) is not int or not 1<=self.max_steps<=128 or type(self.max_response_bytes) is not int or not 1<=self.max_response_bytes<=65536:
            raise CompositionUnavailable('Explicit bounded cleanup read limits required')

def _cleanup_progress_from_checker(checker,resolve,configuration,*,environment,issuer,audience):
    modules=_internal_modules('cleanup_progress')
    if environment!='local' or not isinstance(checker,modules['cj_auth.admission'].AdmissionChecker) or not callable(resolve) or type(configuration) is not CleanupProgressConfiguration:
        raise CompositionUnavailable('Canonical checker/trusted current-account resolver/config required')
    host=modules['cj_cleanup.protected_progress'].Configuration(environment,issuer,audience,configuration.max_steps,configuration.max_response_bytes)
    return checker,resolve,host,modules

def create_cleanup_progress_app(*,configuration,environment,jwt_configuration,verification_keys,access_provider,resolve):
    if environment!='local' or not callable(resolve) or not callable(getattr(verification_keys,'resolve',None)) or not callable(getattr(access_provider,'evaluate',None)):
        raise CompositionUnavailable('Explicit local cleanup progress AUTH/resolver required')
    modules=_internal_modules('cleanup_progress');auth=modules['cj_auth.jwt_adapter']
    if not isinstance(jwt_configuration,auth.JWTConfiguration) or jwt_configuration.profile is not auth.JWTProfile.STRICT_V1:
        raise CompositionUnavailable('Fixed strict AUTH profile required')
    checker=modules['cj_auth.admission'].AdmissionChecker(auth.PyJWTVerifier(jwt_configuration,verification_keys),access_provider)
    deps=_cleanup_progress_from_checker(checker,resolve,configuration,environment=environment,issuer=jwt_configuration.issuer,audience=jwt_configuration.audience)
    from .app import create_app
    return create_app(_cleanup_progress_configuration=configuration,_cleanup_progress_dependencies=deps)
