"""Explicit native4 city route registration, one original request/receipt each.

This component does not install itself or select a mode/retry. The code pipeline
must supply observed endpoints and count any walking/transit/taxi alternative
as a separate registered attempt under its existing plan/account limits.
"""
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
import json

from cj_message.lio_wire import ExplorationOrigin
from cj_place.gaode import Config,_binding_json
from cj_place.rich_routes import CityRoute,prepare
from cj_place.https_transport import ProviderCredentials,route_candidate_stream,ROUTE_REQUEST_SENT
from cj_trip.domain import identifier
from cj_usage.registered_exit import Registration,InvocationInput
from cj_usage.metered_exit import BudgetUnknown, GuardedWireWrite, UNLOCKED_WIRE_START

from .local_app import ISSUER,scope_for
from .local_lio_provider_sources import RegisteredProviderSources,PROVIDER_OUTPUT_LIMIT


@dataclass(frozen=True,repr=False)
class RouteInput:
    query:CityRoute
    request_ref:str
    origin:ExplorationOrigin
    sources:RegisteredProviderSources
    target:str


def registration(services):
    def require_scope(scope):
        services.require_scope(scope)
        if scope not in {scope_for(ISSUER,subject)for subject in services.national_subjects}:
            raise BudgetUnknown('native4 route original subject is not selected')

    def prepare_input(argument):
        if (type(argument)is not RouteInput or type(argument.query)is not CityRoute or
                type(argument.origin)is not ExplorationOrigin or type(argument.sources)is not RegisteredProviderSources
                or argument.sources.binding!=argument.origin.binding):
            raise BudgetUnknown('explicit source-bound native4 route input required')
        identifier(argument.target)
        binding=argument.origin.binding
        require_scope(binding.scope);argument.origin.check(binding)
        original=json.dumps(dict(version='LIO-route-input.1',query_type='CityRoute',query=asdict(argument.query),
            request_ref=argument.request_ref,origin=argument.origin.descriptor(),targets=[argument.target],synthetic_only=True),
            ensure_ascii=False,sort_keys=True,separators=(',',':'),default=_binding_json).encode()
        def bind(operation,guard):
            argument.origin.check(operation.binding);require_scope(operation.binding.scope)
            argument.sources.begin(operation)
            def checked():
                if guard()is not True:return False
                require_scope(operation.binding.scope);argument.origin.check(operation.binding)
                return True
            def invoke():
                if checked()is not True:raise BudgetUnknown('original route authority unavailable')
                budget=services.model.authorization
                budget.begin(operation.command.attempt_id,'route',original);budget.check_date()
                config=Config('https://restapi.amap.com',8192,65536,20,60)
                request=prepare(config,argument.query,argument.request_ref,datetime.now(timezone.utc))
                events=route_candidate_stream(config,request,ProviderCredentials(services.amap_key,budget.deadline),
                                              before_send=checked,defer_write=GuardedWireWrite)
                yield UNLOCKED_WIRE_START
                try:
                    for event in events:
                        if isinstance(event,GuardedWireWrite):
                            yield event
                            continue
                        if event is ROUTE_REQUEST_SENT:
                            yield ''
                            continue
                        if event.state!='received':raise BudgetUnknown('original route transport outcome unknown')
                        if checked()is not True:raise BudgetUnknown('original route authority changed')
                        raw,metadata=argument.sources.observe_route(operation,config,request,event.response)
                        budget.finish(operation.command.attempt_id,metadata)
                        yield raw.decode()
                finally:events.close()
            return invoke
        return InvocationInput(original,None,bind,argument.sources.receipt,tool_output_limit=PROVIDER_OUTPUT_LIMIT)
    return Registration('tool',prepare_input)
