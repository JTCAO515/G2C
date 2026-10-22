"""Explicit local display-only composition; one existing MESSAGE authority."""
from dataclasses import dataclass
from .composition import CompositionUnavailable,_pinned_modules

@dataclass(frozen=True)
class RunDisplayWireConfiguration:
    max_message_id_bytes:int
    max_text_bytes:int
    max_response_bytes:int
    def __post_init__(self):
        if any(type(n) is not int or n<1 for n in (self.max_message_id_bytes,self.max_text_bytes,self.max_response_bytes)):
            raise CompositionUnavailable('Explicit positive display byte limits required')

def _attach_run_display(message,resolve_run,configuration):
    modules=_pinned_modules(manifest_name='run_display_pins.json')
    if (type(message) is not modules['cj_message.auth_boundary'].Boundary or not callable(resolve_run)
            or type(configuration) is not RunDisplayWireConfiguration):
        raise CompositionUnavailable('Fixed MESSAGE, trusted RUN resolver and explicit limits required')
    display=modules['cj_run.display_snapshot']
    config=display.DisplaySnapshotConfiguration(max_text_bytes=configuration.max_text_bytes,max_response_bytes=configuration.max_response_bytes)
    return display.DisplaySnapshotReader(message,resolve_run,configuration=config),modules

def build_run_display_reader(*,environment,jwt_configuration,verification_keys,access_provider,
                             resolve_message_repository,resolve_run,configuration):
    if (environment!='local' or not callable(resolve_message_repository) or not callable(resolve_run)
            or not callable(getattr(verification_keys,'resolve',None)) or not callable(getattr(access_provider,'evaluate',None))):
        raise CompositionUnavailable('Explicit local display AUTH and resolvers required')
    modules=_pinned_modules(manifest_name='run_display_pins.json');auth=modules['cj_auth.jwt_adapter']
    if not isinstance(jwt_configuration,auth.JWTConfiguration) or jwt_configuration.profile is not auth.JWTProfile.STRICT_V1:
        raise CompositionUnavailable('Fixed strict AUTH profile required')
    checker=modules['cj_auth.admission'].AdmissionChecker(auth.PyJWTVerifier(jwt_configuration,verification_keys),access_provider)
    message=modules['cj_message.auth_boundary'].Boundary(checker,resolve_message_repository,None)
    return _attach_run_display(message,resolve_run,configuration)

def create_run_display_app(*,configuration,**dependencies):
    reader,modules=build_run_display_reader(configuration=configuration,**dependencies)
    from .app import create_app
    return create_app(_run_display_reader=reader,_run_display_configuration=configuration,_run_display_modules=modules)
