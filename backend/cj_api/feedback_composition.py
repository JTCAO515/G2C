"""Fixed FEEDBACK + optional concrete MESSAGE/RUN reads, one canonical checker."""
from dataclasses import dataclass
from .composition import CompositionUnavailable,_pinned_modules

@dataclass(frozen=True)
class FeedbackWireConfiguration:
    max_body_bytes:int
    max_private_response_bytes:int
    def __post_init__(self):
        for value,maximum in [(self.max_body_bytes,16384),(self.max_private_response_bytes,(1<<31)-1)]:
            if type(value) is not int or not 1<=value<=maximum:raise CompositionUnavailable('Explicit bounded FEEDBACK limits required')

def _feedback_with_shared_message(message,resolve,resolve_run=None):
    """Internal same-app assembly. The existing MESSAGE checker is reused exactly."""
    modules=_pinned_modules(manifest_name='feedback_pins.json')
    if type(message) is not modules['cj_message.auth_boundary'].Boundary or not callable(resolve):
        raise CompositionUnavailable('Trusted shared MESSAGE boundary and feedback resolver required')
    if resolve_run is not None and not callable(resolve_run):raise CompositionUnavailable('Explicit RUN resolver required')
    sources=None if resolve_run is None else modules['cj_feedback.sources'].Sources(message,resolve_run)
    return modules['cj_feedback.boundary'].Boundary(message.checker,resolve,sources=sources),modules

def build_feedback_boundary(*,environment,jwt_configuration,verification_keys,access_provider,resolve,
                            resolve_message_repository=None,resolve_run=None):
    if (environment!='local' or not callable(resolve) or not callable(getattr(verification_keys,'resolve',None))
            or not callable(getattr(access_provider,'evaluate',None))):
        raise CompositionUnavailable('Explicit local FEEDBACK AUTH/resolver required')
    modules=_pinned_modules(manifest_name='feedback_pins.json');auth=modules['cj_auth.jwt_adapter']
    if not isinstance(jwt_configuration,auth.JWTConfiguration) or jwt_configuration.profile is not auth.JWTProfile.STRICT_V1:
        raise CompositionUnavailable('Fixed strict AUTH profile required')
    checker=modules['cj_auth.admission'].AdmissionChecker(auth.PyJWTVerifier(jwt_configuration,verification_keys),access_provider)
    sources=None
    if resolve_message_repository is not None or resolve_run is not None:
        if not callable(resolve_message_repository) or not callable(resolve_run):
            raise CompositionUnavailable('Both explicit MESSAGE and RUN resolvers required for references')
        # Public read context does not create a RUN: no write ID factory is supplied.
        message=modules['cj_message.auth_boundary'].Boundary(checker,resolve_message_repository,None)
        sources=modules['cj_feedback.sources'].Sources(message,resolve_run)
    return modules['cj_feedback.boundary'].Boundary(checker,resolve,sources=sources),modules

def create_feedback_composed_app(*,configuration,**dependencies):
    if type(configuration) is not FeedbackWireConfiguration:raise CompositionUnavailable('Explicit FEEDBACK wire configuration required')
    boundary,modules=build_feedback_boundary(**dependencies)
    from .app import create_app
    return create_app(_feedback_boundary=boundary,_feedback_configuration=configuration,_feedback_modules=modules)
