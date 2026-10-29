"""Explicit local NEEDS factory; existing AUTH and producer public lifetime only."""
from dataclasses import dataclass
from .composition import CompositionUnavailable,_internal_modules

@dataclass(frozen=True)
class NeedsWireConfiguration:
    max_body_bytes: int
    max_private_response_bytes: int
    def __post_init__(self):
        for value,maximum in [(self.max_body_bytes,131072),(self.max_private_response_bytes,(1<<31)-1)]:
            if type(value) is not int or not 1<=value<=maximum:
                raise CompositionUnavailable('Explicit bounded NEEDS limits required')

def build_needs_boundary(*,environment,jwt_configuration,verification_keys,access_provider,resolve):
    if environment!='local' or None in (resolve,verification_keys,access_provider):
        raise CompositionUnavailable('Explicit local NEEDS AUTH and trusted resolver required')
    modules=_internal_modules('needs');auth=modules['cj_auth.jwt_adapter']
    if not isinstance(jwt_configuration,auth.JWTConfiguration) or jwt_configuration.profile is not auth.JWTProfile.STRICT_V1:
        raise CompositionUnavailable('Fixed strict AUTH profile required')
    checker=modules['cj_auth.admission'].AdmissionChecker(auth.PyJWTVerifier(jwt_configuration,verification_keys),access_provider)
    return modules['cj_needs.boundary'].Boundary(checker,resolve),modules

def create_needs_composed_app(*,configuration,**dependencies):
    if type(configuration) is not NeedsWireConfiguration:raise CompositionUnavailable('Explicit NEEDS wire configuration required')
    boundary,modules=build_needs_boundary(**dependencies)
    from .app import create_app
    return create_app(_needs_boundary=boundary,_needs_configuration=configuration,_needs_modules=modules)
