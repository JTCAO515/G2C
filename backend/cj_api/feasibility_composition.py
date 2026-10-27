"""Closed candidate composition on canonical NEEDS/AUTH and fixed source projector."""
from dataclasses import dataclass
from .composition import CompositionUnavailable,_internal_modules

@dataclass(frozen=True)
class FeasibilityConfiguration:
    max_revisions:int
    max_input_bytes:int
    max_report_bytes:int
    max_response_bytes:int
    def __post_init__(self):
        for value,cap in [(self.max_revisions,128),(self.max_input_bytes,1048576),(self.max_report_bytes,1048576),(self.max_response_bytes,1048576)]:
            if type(value) is not int or not 1<=value<=cap:
                raise CompositionUnavailable('Explicit bounded history/input/report/final limits required')

@dataclass(frozen=True)
class CandidateDependencies:
    checker:object
    resolve:object
    configuration:FeasibilityConfiguration
    host:object
    limits:object
    modules:dict

def _candidate_dependencies(*,environment,checker,resolve,configuration,issuer,audience):
    modules=_internal_modules('feasibility')
    if environment!='local' or not isinstance(checker,modules['cj_auth.admission'].AdmissionChecker) or not callable(resolve) or type(configuration) is not FeasibilityConfiguration:
        raise CompositionUnavailable('Existing canonical checker and explicit trusted read host required')
    host=modules['cj_needs.protected_read'].ReadConfiguration(environment,issuer,audience,configuration.max_response_bytes)
    limits=modules['cj_feasibility.current_read'].ReadLimits(configuration.max_revisions,configuration.max_input_bytes,configuration.max_report_bytes)
    return CandidateDependencies(checker,resolve,configuration,host,limits,modules)

def create_feasibility_app(*,configuration,environment,jwt_configuration,verification_keys,access_provider,resolve):
    raise CompositionUnavailable('CJ035 protected-current consumer gates pending; feasibility factory closed')
