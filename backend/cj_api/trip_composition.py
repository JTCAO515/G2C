"""Explicit local TRIP composition of existing fixed AUTH and public Boundary."""
from dataclasses import dataclass
from .composition import CompositionUnavailable, _internal_modules


@dataclass(frozen=True)
class TripWireConfiguration:
    max_action_bytes: int
    max_page_limit: int
    max_private_response_bytes: int

    def __post_init__(self):
        for value,maximum in ((self.max_action_bytes,(1<<31)-1),(self.max_page_limit,100),
                              (self.max_private_response_bytes,(1<<31)-1)):
            if type(value) is not int or not 1<=value<=maximum:
                raise CompositionUnavailable('Explicit bounded TRIP wire limits required')


def build_trip_boundary(*,environment,jwt_configuration,verification_keys,access_provider,
                        resolve,confirmation_validator=None):
    """Resolver and validator are server configuration, never request owner/viewed.

    An absent validator remains absent: public producer denies fresh actions.
    This constructs a Boundary only; routes require the public projection seam.
    """
    if environment!='local' or None in (resolve,verification_keys,access_provider):
        raise CompositionUnavailable('Explicit local TRIP AUTH/resolver configuration required')
    modules=_internal_modules('trip')
    auth=modules['cj_auth.jwt_adapter']
    if (not isinstance(jwt_configuration,auth.JWTConfiguration)
            or jwt_configuration.profile is not auth.JWTProfile.STRICT_V1):
        raise CompositionUnavailable('Fixed strict AUTH profile required')
    verifier=auth.PyJWTVerifier(jwt_configuration,verification_keys)
    checker=modules['cj_auth.admission'].AdmissionChecker(verifier,access_provider)
    boundary=modules['cj_trip.auth_boundary'].Boundary(checker,resolve,confirmation_validator)
    return boundary,modules


def create_trip_composed_app(*,configuration,manual_preview_configuration=None,**dependencies):
    if type(configuration) is not TripWireConfiguration:
        raise CompositionUnavailable('Explicit TRIP wire configuration required')
    boundary,modules=build_trip_boundary(**dependencies)
    preview_boundary = preview_modules = None
    if manual_preview_configuration is not None:
        from .manual_preview_composition import _attach_manual_preview
        preview_boundary,preview_modules = _attach_manual_preview(boundary,manual_preview_configuration)
    from .app import create_app
    return create_app(_trip_boundary=boundary,_trip_configuration=configuration,_trip_modules=modules,
        _manual_preview_boundary=preview_boundary,_manual_preview_configuration=manual_preview_configuration,_manual_preview_modules=preview_modules)
