"""Readonly original association consumes actual MESSAGE and strict canonical RUN."""
from dataclasses import dataclass
from .composition import CompositionUnavailable,_internal_modules

@dataclass(frozen=True)
class OriginalUsageWireConfiguration:
    max_message_id_bytes:int
    max_response_bytes:int
    def __post_init__(self):
        if any(type(n) is not int or n<1 for n in (self.max_message_id_bytes,self.max_response_bytes)):
            raise CompositionUnavailable('Explicit positive association byte limits required')

def _attach_original_usage(message,resolve_run,configuration):
    modules=_internal_modules('original_usage')
    if type(message) is not modules['cj_message.auth_boundary'].Boundary or resolve_run is None or type(configuration) is not OriginalUsageWireConfiguration:
        raise CompositionUnavailable('Fixed MESSAGE, canonical resolver and explicit limits required')
    source=modules['cj_run.original_usage_read']
    return source.OriginalUsageAssociationReader(message,resolve_run,configuration=source.UsageAssociationReadConfiguration(configuration.max_response_bytes)),modules

def create_original_usage_app(*,configuration,environment,jwt_configuration,verification_keys,access_provider,resolve_message_repository,resolve_run):
    if environment!='local' or None in (resolve_message_repository,resolve_run,verification_keys,access_provider):
        raise CompositionUnavailable('Explicit local association AUTH/resolvers required')
    modules=_internal_modules('original_usage');auth=modules['cj_auth.jwt_adapter']
    if not isinstance(jwt_configuration,auth.JWTConfiguration) or jwt_configuration.profile is not auth.JWTProfile.STRICT_V1:
        raise CompositionUnavailable('Fixed strict AUTH profile required')
    checker=modules['cj_auth.admission'].AdmissionChecker(auth.PyJWTVerifier(jwt_configuration,verification_keys),access_provider)
    message=modules['cj_message.auth_boundary'].Boundary(checker,resolve_message_repository,None)
    reader,modules=_attach_original_usage(message,resolve_run,configuration)
    from .app import create_app
    return create_app(_original_usage_reader=reader,_original_usage_configuration=configuration,_original_usage_modules=modules)
