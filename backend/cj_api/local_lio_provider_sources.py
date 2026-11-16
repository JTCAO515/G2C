"""Eligible provider observations from the original registered settled attempt.

No provider call, replay, financial mutation or caller-supplied record list.
Seal outside RUN/NEEDS/Trip locks. Publication reuses the actual M/Memory frame
and the existing SELECT-only usage-status reader.
"""
from contextlib import contextmanager
from dataclasses import dataclass,InitVar,replace
from datetime import datetime,timezone
from hashlib import sha256
import json
import threading

from cj_memory.runtime import RuntimeDenied,RuntimeUnknown
from cj_run.operation_usage import OperationStore
from cj_run.step_usage import ledger_scope_for
from cj_usage.read_status import ReadUnavailable
from cj_usage.postgres import CommitUnknown,RepositoryUnavailable
from cj_usage.codec import CorruptLedger
from cj_usage.core import Receipt
from psycopg import Error as DatabaseError
from cj_place.gaode_v2 import parse as parse_poi2,ReceiptMismatch
from cj_place.rich_routes import parse as parse_route
from cj_place.models import FieldState
from cj_trip.domain import packed

_FACTORY=object()
POI2_REGISTRATION='tool.lio_poi2.1'
ROUTE_REGISTRATION='tool.lio_route.1'
PROVIDER_OUTPUT_LIMIT=8192 # registered/Meter unit is Python characters, not UTF-8 bytes
STATUS_BATCH_BYTES=45*8192+44+2 # internal minimal-status array, not a provider output limit


def _receipt_identity(metadata):
    return 'live:'+sha256(packed((metadata['endpoint'],metadata['response_sha256']))).hexdigest()


@dataclass(frozen=True,repr=False)
class _Observed:
    operation:object
    reply:bytes|None=None
    metadata:bytes|None=None
    records:bytes|None=None


@dataclass(frozen=True,slots=True,repr=False)
class ProviderCapture:
    _raw:bytes
    _outcomes:bytes
    _revision:int
    _factory:InitVar[object]
    def __post_init__(self,_factory):
        if _factory is not _FACTORY:raise RuntimeDenied('issued provider capture required')
    @property
    def records(self):return json.loads(self._raw)
    @property
    def outcomes(self):return json.loads(self._outcomes)


class RegisteredProviderSources:
    def __init__(self,worker,binding):
        self.worker,self.binding=worker,binding
        self.exit=worker.budget_exit
        self.store=OperationStore(worker.runs,self.exit.config)
        self._observed={};self._revision=0;self._issued=None

    def begin(self,operation):
        if (operation.binding!=self.binding or operation.registration_id not in (POI2_REGISTRATION,ROUTE_REGISTRATION) or
                operation.command.kind!='tool' or operation.command.operation_id in self._observed):
            raise RuntimeDenied('new original registered place/route operation required')
        self._observed[operation.command.operation_id]=_Observed(operation)
        self._revision+=1

    def observe_poi2(self,operation,config,request,response):
        """Called only by the code producer with its complete bounded receipt.

        The reply/receipt identity is generated here, not accepted from a model.
        A complete unusable provider payload contributes no eligible place facts.
        Transport/financial UNKNOWN must never call this completion method.
        """
        key=operation.command.operation_id
        prior=self._observed.get(key)
        if prior is None or prior.operation!=operation or prior.reply is not None:
            raise RuntimeDenied('original pending provider operation required')
        endpoint=request.origin+request.path;records=[];items=[]
        try:result=parse_poi2(config,request,response,datetime.now(timezone.utc))
        except ReceiptMismatch as error:
            raise RuntimeUnknown('provider receipt is not bound to the original query') from error
        except (ValueError,UnicodeError):
            result=None
        if result is not None:
            for poi in result.pois:
                role='entrance'if poi.entrance.state is FieldState.PRESENT else'poi_center'
                projection=poi.place_projection(role)
                reference=None
                if projection is not None:
                    reference=dict(provider='amap',kind='place',reference=key+':poi:'+poi.provider_id,
                                   sha256=sha256(packed(projection)).hexdigest())
                    records.append(dict(reference,payload=projection))
                def opening(value):return dict(state=value.state.value,value=value.value)
                items.append(dict(amap_id=poi.provider_id,name_zh=poi.name_zh,place=projection,source=reference,
                    opening_today=opening(poi.opening_today),opening_week=opening(poi.opening_week)))
        value=dict(version='LIO-poi2-result.1',status='unavailable'if result is None else'ok',
            request_ref=request.request_ref,request_binding_sha256=request.binding_digest,
            raw_response_sha256=sha256(response.body).hexdigest(),observed_at=response.received_at.isoformat(),items=items)
        reply=packed(value);reason=None
        if len(reply.decode())>PROVIDER_OUTPUT_LIMIT:
            # The complete page is unusable for this registered profile. Never
            # trim optional fields or retain only the first matching records.
            # The original paid attempt still settles with its real receipt;
            # its raw hash remains available and no place fact is eligible.
            records=[];reason='normalized_output_limit'
            value=dict(value,status='unavailable',items=[]);reply=packed(value)
        metadata=packed(dict(endpoint=endpoint,response_sha256=sha256(reply).hexdigest(),region='China',
            result_status=value['status'],actual_cost_cny='UNKNOWN',
            **({}if reason is None else dict(unavailable_reason=reason))))
        self._observed[key]=replace(prior,reply=reply,metadata=metadata,records=packed(records))
        self._revision+=1
        return reply,json.loads(metadata)

    def observe_route(self,operation,config,request,response):
        """Project only the original query's observed route estimate."""
        key=operation.command.operation_id
        prior=self._observed.get(key)
        if prior is None or prior.operation!=operation or prior.reply is not None:
            raise RuntimeDenied('original pending route operation required')
        records=[];items=[]
        try:estimate=parse_route(config,request,response,datetime.now(timezone.utc))
        except ReceiptMismatch as error:
            raise RuntimeUnknown('route receipt is not bound to the original endpoints')from error
        except (ValueError,UnicodeError):estimate=None
        if estimate is not None:
            query=request.query
            def coordinate(point):
                return dict(raw=point.raw,longitude=str(point.longitude),latitude=str(point.latitude),crs='GCJ-02')
            def number(value):return int(value)if value==value.to_integral_value()else float(value)
            payload=dict(from_amap_id=query.origin.provider_id,to_amap_id=query.destination.provider_id,
                from_coordinate=coordinate(query.origin.coordinate),to_coordinate=coordinate(query.destination.coordinate),
                from_coordinate_role=query.origin.coordinate_role,to_coordinate_role=query.destination.coordinate_role,
                mode=query.mode,duration_seconds=number(estimate.duration_seconds),distance_m=number(estimate.distance_m))
            reference=dict(provider='amap',kind='route',reference=key+':route',sha256=sha256(packed(payload)).hexdigest())
            records.append(dict(reference,payload=payload));items.append(dict(route=payload,source=reference))
        reply=packed(dict(version='LIO-route-result.1',status='ok'if estimate is not None else'unavailable',
            request_ref=request.request_ref,request_binding_sha256=request.binding_digest,
            raw_response_sha256=sha256(response.body).hexdigest(),observed_at=response.received_at.isoformat(),items=items))
        metadata=packed(dict(endpoint=request.origin+request.path,response_sha256=sha256(reply).hexdigest(),region='China',
            result_status='ok'if estimate is not None else'unavailable',actual_cost_cny='UNKNOWN'))
        self._observed[key]=replace(prior,reply=reply,metadata=metadata,records=packed(records))
        self._revision+=1
        return reply,json.loads(metadata)

    def receipt(self,attempt,unit,output):
        """The original Meter callback, only for a complete observed reply."""
        for observed in self._observed.values():
            if observed.operation.command.attempt_id!=attempt:continue
            if observed.reply is None or output!=len(observed.reply.decode()):
                raise RuntimeUnknown('original provider completion is unavailable')
            return Receipt(attempt,_receipt_identity(json.loads(observed.metadata)),unit,1,output)
        raise RuntimeUnknown('original provider attempt is unavailable')

    def _statuses(self,observed,guard):
        if not observed:return
        if any(value.reply is None for value in observed):
            raise RuntimeUnknown('original provider outcome is unresolved')
        periods={value.operation.period for value in observed}
        if len(periods)!=1:raise RuntimeUnknown('original provider periods differ')
        account=ledger_scope_for(self.binding.scope,self.exit.config)
        meter=self.exit.resolve_meter(self.binding,account)
        try:
            raw=meter.repo.read_status_many(tuple(value.operation.command.attempt_id for value in observed),
                guard=guard,max_response_bytes=STATUS_BATCH_BYTES,expected_period=periods.pop())
        except (ReadUnavailable,CommitUnknown,RepositoryUnavailable,CorruptLedger,DatabaseError)as error:
            raise RuntimeUnknown('original provider receipt read unavailable')from error
        for value,status in zip(observed,json.loads(raw),strict=True):
            self._check_status(value,status)

    def _check_status(self,observed,status):
        operation=observed.operation;metadata=json.loads(observed.metadata)
        receipt=_receipt_identity(metadata)
        expected=(operation.command.attempt_id,operation.command.operation_id,self.binding.run_id,
                  'settled','provider_call',1,len(observed.reply.decode()),receipt,False,False)
        actual=tuple(status[key]for key in ('attempt_id','operation_id','run_id','status','unit',
            'confirmed_units','confirmed_output','receipt_id','cancelled','exceeded'))
        if actual!=expected:raise RuntimeUnknown('original settled provider receipt differs')

    def capture(self,binding):
        if binding!=self.binding:raise RuntimeDenied('provider capture belongs to another original RUN')
        # read_original acquires its own RUN lock, so this materialization must
        # finish before the publication step starts holding RUN/M/Memory/N/Trip.
        def current():
            if self.worker.budget_exit is not self.exit or self.worker.runs.valid(binding)is not True:
                raise RuntimeDenied('original provider source no longer current')
        current();records=[];outcomes=[]
        observations=tuple(self._observed.values())
        for observed in observations:
            operation=observed.operation
            actual=self.store.read_original(binding,operation.operation_key)
            if actual!=operation:raise RuntimeDenied('original registered provider input differs')
        self._statuses(observations,current)
        for observed in observations:
            operation=observed.operation
            records.extend(json.loads(observed.records))
            reply=json.loads(observed.reply)
            original=json.loads(operation.original.input_bytes)
            outcomes.append(dict(version='LIO-provider-outcome.1',attempt_id=operation.command.attempt_id,
                operation_id=operation.command.operation_id,registration=operation.registration_id,
                input_sha256=operation.command.input_digest,reply_sha256=sha256(observed.reply).hexdigest(),
                request_ref=reply['request_ref'],status=reply['status'],item_count=len(reply['items']),
                targets=original['targets'],query_type=original['query_type'],query=original['query']))
        if len(records)>256:raise RuntimeDenied('eligible provider source bound exceeded')
        current()
        result=ProviderCapture(packed(records),packed(outcomes),self._revision,_factory=_FACTORY)
        self._issued=result
        return result

    @contextmanager
    def hold(self,binding,capture,message):
        if binding!=self.binding or capture is not self._issued:
            raise RuntimeDenied('same-instance original provider capture required')
        active=True;thread=threading.get_ident()
        def guard():
            if not active or threading.get_ident()!=thread or self._revision!=capture._revision:
                raise RuntimeDenied('provider source frame changed or expired')
            if self.worker.budget_exit is not self.exit:raise RuntimeDenied('provider configuration changed')
            message.check(binding)
            if self.worker.memory_run is None:raise RuntimeDenied('actual held Memory source required')
            self.worker.memory_run.check()
        def check():
            guard()
            self._statuses(tuple(self._observed.values()),guard)
            guard()
        held=_HeldProvider(check)
        try:
            held.check();yield held;held.check()
        finally:active=False


class _HeldProvider:
    def __init__(self,check):self._check=check
    def check(self):self._check()
