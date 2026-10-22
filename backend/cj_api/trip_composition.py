"""Explicit local TRIP composition of existing fixed AUTH and public Boundary."""
from dataclasses import dataclass
from .composition import CompositionUnavailable, _pinned_modules


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
    if (environment!='local' or not callable(resolve)
            or not callable(getattr(verification_keys,'resolve',None))
            or not callable(getattr(access_provider,'evaluate',None))
            or confirmation_validator is not None and not callable(confirmation_validator)):
        raise CompositionUnavailable('Explicit local TRIP AUTH/resolver configuration required')
    modules=_pinned_modules(manifest_name='trip_pins.json')
    auth=modules['cj_auth.jwt_adapter']
    if (not isinstance(jwt_configuration,auth.JWTConfiguration)
            or jwt_configuration.profile is not auth.JWTProfile.STRICT_V1):
        raise CompositionUnavailable('Fixed strict AUTH profile required')
    verifier=auth.PyJWTVerifier(jwt_configuration,verification_keys)
    checker=modules['cj_auth.admission'].AdmissionChecker(verifier,access_provider)
    boundary=modules['cj_trip.auth_boundary'].Boundary(checker,resolve,confirmation_validator)
    return boundary,modules
