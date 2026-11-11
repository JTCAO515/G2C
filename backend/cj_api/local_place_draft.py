"""Actual registered PLACE observations for an explicitly negotiated C producer."""
from cj_strict_json import compact
from dataclasses import dataclass,field
from datetime import timezone
import base64,hashlib
from types import MappingProxyType
from cj_place.contract_v1 import decode_query
from cj_place.local_draft_source import LocalDraftPlaceProducer
from cj_place.draft_source import ABI,TOOLS_VERSION,PlaceObservation,PlaceSourceBatch,PlaceSourceUnavailable
from cj_place.models import aware
from cj_usage.registered_exit import InvocationInput,Registration
from cj_usage.metered_exit import BudgetUnknown
from .local_tools import LocalTools,ToolInput


@dataclass(frozen=True)
class SourceToolInput(ToolInput):
    binding:object
    operation_key:str


@dataclass
class _RunSources:
    worker:object
    observations:list=field(default_factory=list)
    complete:bool=False
    batch:object=None
    last_time:object=None


class _PlaceSources:
    abi=ABI
    def __init__(self,tools,scope):self.tools,self.scope=tools,scope

    def _state(self,binding):
        if binding.scope!=self.scope:raise PlaceSourceUnavailable('original PLACE owner mismatch')
        try:state=self.tools._source_runs[binding]
        except KeyError:raise PlaceSourceUnavailable('original PLACE run unavailable') from None
        if not state.complete:raise PlaceSourceUnavailable('original tool turn not complete/settled')
        return state

    def _fresh(self,state):
        now=self.tools._tick(state)
        for observation in state.observations:
            if self.tools.place.config is not observation.config:
                raise PlaceSourceUnavailable('original PLACE config changed')
            source=observation.result.source
            started=observation.started_at if source is None else source.query_started_at
            age=(now.astimezone(timezone.utc)-started.astimezone(timezone.utc)).total_seconds()
            if not 0<=age<=observation.config.max_age_seconds:
                raise PlaceSourceUnavailable('original PLACE observation stale')

    def capture(self,binding):
        state=self._state(binding);self._fresh(state)
        if state.batch is None:state.batch=PlaceSourceBatch(binding,tuple(state.observations))
        return state.batch

    def check_data(self,binding):
        state=self._state(binding)
        if state.batch is None:raise PlaceSourceUnavailable('C producer did not capture original PLACE sources')
        self._fresh(state)

    def check(self,binding,batch):
        state=self._state(binding)
        if state.batch is not batch:raise PlaceSourceUnavailable('original issued PLACE capture required')
        check=state.worker._publication_check
        if check is None:raise PlaceSourceUnavailable('active original publication fence required')
        check()  # Original owner/MESSAGE/NEEDS/Memory/source checks and deadline last.


class LocalPlaceDraftTools(LocalTools):
    version=TOOLS_VERSION
    def __init__(self):
        super().__init__();self._source_runs={}
        original=self.place;self.place=LocalDraftPlaceProducer(original.config,clock=original.clock)
        self.registrations=MappingProxyType({**self.registrations,
            'tool.place':Registration('tool',self._source_input)})

    def source_for(self,scope):return _PlaceSources(self,scope)

    def _tick(self,state,*,floor=None):
        now=self.place.clock()
        try:aware(now)
        except (ValueError,TypeError):raise PlaceSourceUnavailable('PLACE clock unavailable') from None
        instant=now.astimezone(timezone.utc)
        if (state.last_time is not None and instant<state.last_time.astimezone(timezone.utc)) or (floor is not None and instant<floor.astimezone(timezone.utc)):
            raise PlaceSourceUnavailable('PLACE clock regressed')
        state.last_time=now
        return now

    def _tool_input(self,binding,key,query,request_ref):
        return SourceToolInput(query,request_ref,binding,key)

    def _source_input(self,argument):
        query=decode_query(argument.original_query)
        state=self._source_runs[argument.binding]
        expected='op-'+hashlib.sha256((argument.binding.run_id+'\0'+argument.operation_key).encode()).hexdigest()
        if argument.request_ref!=expected or state.complete:
            raise PlaceSourceUnavailable('original PLACE operation mismatch')
        original=compact(dict(version='PLACE-tool-input.2',operation_key=argument.operation_key,
            message_id=argument.binding.message_id,run_id=argument.binding.run_id,
            request_ref=argument.request_ref,original_query_base64=base64.b64encode(argument.original_query).decode('ascii')), ensure_ascii=True, allow_nan=True)
        def materialize():
            config=self.place.config;started=self._tick(state)
            invoke=self.place.prepare_observation(query,argument.request_ref)
            def stream():
                try:result,raw,parsed_at=invoke()
                except TimeoutError:raise BudgetUnknown('original PLACE completion unavailable') from None
                self._tick(state,floor=parsed_at)
                if result.query!=query or result.source is not None and result.source.request_ref!=argument.request_ref:
                    raise PlaceSourceUnavailable('actual PLACE result association mismatch')
                state.observations.append(PlaceObservation(argument.operation_key,argument.request_ref,
                    argument.original_query,raw,result,config,started))
                yield raw.decode('utf8')
            return stream
        return InvocationInput(original,materialize)

    def answer(self,worker,binding,messages):
        if binding in self._source_runs:raise PlaceSourceUnavailable('original PLACE turn already exists')
        state=_RunSources(worker);self._source_runs[binding]=state
        self._tick(state)
        yield from super().answer(worker,binding,messages)
        self._tick(state)
        state.complete=True
