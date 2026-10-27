"""Readonly manual preview consumes existing authenticated TRIP operation only."""
from dataclasses import dataclass
from .composition import CompositionUnavailable,_internal_modules
from .trip_composition import build_trip_boundary

@dataclass(frozen=True)
class ManualPreviewConfiguration:
    max_body_bytes:int
    max_original_bytes:int
    max_field_bytes:int
    max_response_bytes:int
    def __post_init__(self):
        if any(type(v) is not int or v<1 for v in (self.max_body_bytes,self.max_original_bytes,self.max_field_bytes,self.max_response_bytes)):
            raise CompositionUnavailable('Explicit positive preview bounds required')
        if self.max_original_bytes>1_000_000:raise CompositionUnavailable('Original Trip bound exceeds producer format')

def _attach_manual_preview(boundary,configuration):
    modules=_internal_modules('manual_preview')
    if type(boundary) is not modules['cj_trip.auth_boundary'].Boundary or type(configuration) is not ManualPreviewConfiguration:
        raise CompositionUnavailable('Existing TRIP boundary and explicit preview limits required')
    return boundary,modules

def create_manual_preview_app(*,configuration,**dependencies):
    boundary,_=build_trip_boundary(**dependencies)
    boundary,modules=_attach_manual_preview(boundary,configuration)
    from .app import create_app
    return create_app(_manual_preview_boundary=boundary,_manual_preview_configuration=configuration,_manual_preview_modules=modules)
