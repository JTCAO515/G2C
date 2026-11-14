"""Explicit native4 POI2 registration; composes the existing single spending exit.

The pipeline must install this registration on the server. No route or old
national tool list installs it merely by importing this module.
"""
from dataclasses import asdict,dataclass
import json
from datetime import datetime,timezone

from cj_message.lio_wire import ExplorationOrigin
from cj_place.gaode import Config,_binding_json
from cj_place.gaode_v2 import TextSearch,Nearby,POIDetail,prepare
from cj_place.https_transport import ProviderCredentials,poi2_candidate_stream,POI2_REQUEST_SENT
from cj_usage.registered_exit import Registration,InvocationInput
from cj_usage.metered_exit import BudgetUnknown
from cj_trip.domain import identifier

from .local_app import ISSUER,scope_for
from .local_lio_provider_sources import RegisteredProviderSources


@dataclass(frozen=True,repr=False)
class POI2Input:
    query:TextSearch|Nearby|POIDetail
    request_ref:str
    origin:ExplorationOrigin
    sources:RegisteredProviderSources
    targets:tuple[str,...]=()


def registration(services):
    def require_scope(scope):
        services.require_scope(scope)
        if scope not in {scope_for(ISSUER,subject)for subject in services.national_subjects}:
            raise BudgetUnknown('native4 POI2 original subject is not selected')

    def prepare_input(argument):
        if (type(argument)is not POI2Input or type(argument.origin)is not ExplorationOrigin or
                type(argument.sources)is not RegisteredProviderSources or
                type(argument.query)not in (TextSearch,Nearby,POIDetail) or
                argument.sources.binding!=argument.origin.binding):
            raise BudgetUnknown('explicit source-bound native4 POI2 input required')
        binding=argument.origin.binding
        if (type(argument.targets)is not tuple or len(argument.targets)>60 or
                len(set(argument.targets))!=len(argument.targets)):
            raise BudgetUnknown('bounded code-owned lookup target set required')
        for target in argument.targets:identifier(target)
        require_scope(binding.scope);argument.origin.check(binding)
        original=json.dumps(dict(version='LIO-poi2-input.1',query_type=type(argument.query).__name__,
            query=asdict(argument.query),request_ref=argument.request_ref,origin=argument.origin.descriptor(),
            targets=argument.targets,synthetic_only=True),ensure_ascii=False,sort_keys=True,separators=(',',':'),default=_binding_json).encode()
        def bind(operation,guard):
            argument.origin.check(operation.binding);require_scope(operation.binding.scope)
            argument.sources.begin(operation)
            def checked():
                if guard()is not True:return False
                require_scope(operation.binding.scope);argument.origin.check(operation.binding)
                return True
            def invoke():
                if checked()is not True:raise BudgetUnknown('original POI2 authority unavailable')
                budget=services.model.authorization
                budget.begin(operation.command.attempt_id,'place',original);budget.check_date()
                config=Config('https://restapi.amap.com',8192,65536,20,60)
                request=prepare(config,argument.query,argument.request_ref,datetime.now(timezone.utc))
                events=poi2_candidate_stream(config,request,ProviderCredentials(services.amap_key,budget.deadline),before_send=checked)
                try:
                    for event in events:
                        if event is POI2_REQUEST_SENT:
                            # First advance is the original one send; return to
                            # Worker before draining the response off its locks.
                            yield ''
                            continue
                        if event.state!='received':raise BudgetUnknown('original POI2 transport outcome unknown')
                        if checked()is not True:raise BudgetUnknown('original POI2 authority changed')
                        raw,metadata=argument.sources.observe_poi2(operation,config,request,event.response)
                        budget.finish(operation.command.attempt_id,metadata)
                        yield raw.decode()
                finally:events.close()
            return invoke
        return InvocationInput(original,None,bind,argument.sources.receipt)
    return Registration('tool',prepare_input)
