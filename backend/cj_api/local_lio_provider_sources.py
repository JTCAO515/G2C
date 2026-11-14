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
from cj_place.models import FieldState
from cj_trip.domain import packed

_FACTORY=object()
POI2_REGISTRATION='tool.lio_poi2.1'


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
    _revision:int
    _factory:InitVar[object]
    def __post_init__(self,_factory):
        if _factory is not _FACTORY:raise RuntimeDenied('issued provider capture required')
    @property
    def records(self):return json.loads(self._raw)


class RegisteredProviderSources:
    def __init__(self,worker,binding):
        self.worker,self.binding=worker,binding
        self.exit=worker.budget_exit
        self.store=OperationStore(worker.runs,self.exit.config)
        self._observed={};self._revision=0;self._issued=None

    def begin(self,operation):
        if (operation.binding!=self.binding or operation.registration_id!=POI2_REGISTRATION or
                operation.command.kind!='tool' or operation.command.operation_id in self._observed):
            raise RuntimeDenied('new original registered POI2 operation required')
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
        reply=packed(dict(version='LIO-poi2-result.1',status='unavailable'if result is None else'ok',
            request_ref=request.request_ref,request_binding_sha256=request.binding_digest,
            raw_response_sha256=sha256(response.body).hexdigest(),observed_at=response.received_at.isoformat(),items=items))
        metadata=packed(dict(endpoint=endpoint,response_sha256=sha256(reply).hexdigest(),region='China',
                             result_status='unavailable'if result is None else'ok',actual_cost_cny='UNKNOWN'))
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

    def _status(self,observed,guard):
        operation=observed.operation
        if observed.reply is None:raise RuntimeUnknown('original provider outcome is unresolved')
        account=ledger_scope_for(self.binding.scope,self.exit.config)
        meter=self.exit.resolve_meter(self.binding,account)
        try:
            raw=meter.repo.read_status(operation.command.attempt_id,guard=guard,max_response_bytes=8192,
                                       expected_period=operation.period)
        except (ReadUnavailable,CommitUnknown,RepositoryUnavailable,CorruptLedger,DatabaseError)as error:
            raise RuntimeUnknown('original provider receipt read unavailable')from error
        status=json.loads(raw);metadata=json.loads(observed.metadata)
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
        current();records=[]
        for observed in self._observed.values():
            operation=observed.operation
            actual=self.store.read_original(binding,operation.operation_key)
            if actual!=operation:raise RuntimeDenied('original registered provider input differs')
            self._status(observed,current)
            records.extend(json.loads(observed.records))
        if len(records)>256:raise RuntimeDenied('eligible provider source bound exceeded')
        current()
        result=ProviderCapture(packed(records),self._revision,_factory=_FACTORY)
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
            for observed in self._observed.values():self._status(observed,guard)
            guard()
        held=_HeldProvider(check)
        try:
            held.check();yield held;held.check()
        finally:active=False


class _HeldProvider:
    def __init__(self,check):self._check=check
    def check(self):self._check()
