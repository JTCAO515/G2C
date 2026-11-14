"""Actual plan-trigger/profile capture for the explicit rich publisher.

This joins existing MESSAGE and Memory leases; descriptors alone grant no write.
No model or provider operation belongs inside these methods.
"""
from contextlib import contextmanager
from dataclasses import dataclass,InitVar
from hashlib import sha256
import json
from pathlib import Path
import threading

from cj_memory.runtime import RuntimeDenied
from cj_message.demo_dialogue import LIO_VERSION_V4
from cj_message.lio_wire import exploration_original_protocol
from cj_needs.domain import decode
from cj_trip.domain import packed

from . import lio_exploration_factors,lio_exploration_profile
from .lio_exploration_profile import (CONTEXT,POLICY,decode_context,restore_context,
    default_proposals,snapshot)
from .local_lio_exploration_profile import ProfileContext

PLAN_NOW='lio_plan_now.1:'
_FACTORY=object()


def policy_descriptor():
    """The installed code policy, independently pinned by the source bundle."""
    sources={name:sha256(Path(module.__file__).read_bytes()).hexdigest()for name,module in (
        ('factors',lio_exploration_factors),('profile',lio_exploration_profile))}
    return dict(id=POLICY,sha256=sha256(packed(sources)).hexdigest())


@dataclass(frozen=True,slots=True,repr=False)
class PlanCapture:
    _raw:bytes
    _factory:InitVar[object]

    def __post_init__(self,_factory):
        if _factory is not _FACTORY:raise RuntimeDenied('issued plan capture required')

    @property
    def original(self):return json.loads(self._raw)['original']
    @property
    def plan_now(self):return json.loads(self._raw)['plan_now']
    @property
    def policy(self):return json.loads(self._raw)['policy']
    @property
    def profile_states(self):return json.loads(self._raw)['profile_states']
    @property
    def profile(self):return json.loads(self._raw)['profile']
    @property
    def memory_epoch(self):return self.profile['memory_epoch']


@dataclass(frozen=True)
class _Issued:
    capture:PlanCapture
    worker:object
    context:bytes
    marker:bytes
    memory_owner:object
    memory_snapshot:object
    memory_payload:bytes


class RichProfileSource:
    def __init__(self,database):
        self.database=database
        self.contexts=ProfileContext(database)
        self._issued={}

    def _effect(self,binding,prefix):
        with self.database.connect(binding.scope)as db:
            row=db.execute('SELECT e.value FROM cj_run_event e JOIN cj_run_record r USING(scope,run_id) '
                "WHERE e.scope=%s AND e.run_id=%s AND r.status='running' AND e.kind='effect_committed' "
                'AND e.value LIKE %s ORDER BY e.sequence DESC LIMIT 1',
                (binding.scope,binding.run_id,prefix+'%')).fetchone()
        if row is None:raise RuntimeDenied('current committed planning source unavailable')
        return row[0].removeprefix(prefix).encode()

    def _read(self,worker,binding,stored):
        if stored is None:raise RuntimeDenied('actual planning original unavailable')
        with self.database.connect(binding.scope)as db:
            exploration_original_protocol(db.cursor(),binding,stored)
            row=db.execute('SELECT demo_question_day FROM cj_message_receipt WHERE scope=%s AND message_id=%s AND run_id=%s',
                (binding.scope,binding.message_id,binding.run_id)).fetchone()
        text=json.loads(stored.raw)['text']
        if row is None or row[0] is None or text.strip().casefold()not in ('直接出方案','plan now'):
            raise RuntimeDenied('actual native4 plan-now original required')
        memory=worker.memory_run
        if memory is None:raise RuntimeDenied('actual current Memory capture required')
        raw=self._effect(binding,CONTEXT);saved=decode_context(raw.decode())
        if saved.memory_epoch!=memory.snapshot.epoch:
            raise RuntimeDenied('profile and Memory scope versions differ')
        view=self.contexts.read(worker,binding)
        profile=restore_context(saved,view.originals,memory,registered_city_terms=view.city_terms)
        profile.update({fact.key:fact for fact in default_proposals(profile,view.originals[-1])})
        if packed(snapshot(profile,memory_epoch=memory.snapshot.epoch))!=packed(decode(raw)):
            raise RuntimeDenied('actual accepted planning profile differs')
        original=dict(protocol=LIO_VERSION_V4,message_id=binding.message_id,run_id=binding.run_id,
            input_sha256=stored.receipt.input_sha256,question_day=row[0].isoformat())
        return original,profile,raw

    def record_plan_now(self,worker,binding,state):
        """Commit code provenance only for a literal admitted plan trigger.

        Call after ProfileContext.accept has committed the actual plan defaults.
        Existing WP4 outlines have no marker and cannot become formal authority.
        """
        original,profile,context=self._read(worker,binding,worker.messages.query(binding.message_id))
        marker=packed(dict(version='LIO-plan-now.1',original=original,policy=policy_descriptor(),
                           profile_sha256=sha256(context).hexdigest()))
        def check(_cursor):
            current=worker.message_context.active_original(binding)
            checked,_,actual=self._read(worker,binding,current)
            if checked!=original or actual!=context or decode(marker)['policy']!=policy_descriptor():
                raise RuntimeDenied('plan trigger changed before provenance commit')
        return worker._event(binding,state,'effect_committed',PLAN_NOW+marker.decode(),mutation=check)

    def capture_for_plan(self,worker,binding,message,*,expected_profile):
        message.check(binding)
        memory=worker.memory_run
        if memory is None:raise RuntimeDenied('actual held Memory source required')
        memory.check()
        original,profile,raw=self._read(worker,binding,message.original_message())
        if snapshot(profile)!=snapshot(expected_profile):raise RuntimeDenied('expected profile differs from committed source')
        marker=self._effect(binding,PLAN_NOW);value=decode(marker)
        policy=policy_descriptor()
        expected=dict(version='LIO-plan-now.1',original=original,policy=policy,profile_sha256=sha256(raw).hexdigest())
        if value!=expected:raise RuntimeDenied('actual code plan provenance differs')
        data=packed(dict(original=original,plan_now=dict(kind='plan_now',original=original,policy=policy),
            policy=policy,profile_states={key:fact.state for key,fact in profile.items()},
            profile=snapshot(profile,memory_epoch=memory.snapshot.epoch)))
        capture=PlanCapture(data,_factory=_FACTORY)
        self._issued[binding]=_Issued(capture,worker,raw,marker,memory.owner,memory.snapshot,memory.payload)
        message.check(binding);memory.check()
        return capture

    @contextmanager
    def hold_for_plan(self,worker,binding,capture,message):
        issued=self._issued.get(binding)
        if issued is None or issued.capture is not capture or issued.worker is not worker:
            raise RuntimeDenied('same-instance issued plan capture required')
        active=True;thread=threading.get_ident()
        def check():
            if not active or threading.get_ident()!=thread:raise RuntimeDenied('rich profile source lease expired')
            message.check(binding)
            memory=worker.memory_run
            if memory is None or memory.owner is not issued.memory_owner or memory.snapshot!=issued.memory_snapshot or memory.payload!=issued.memory_payload:
                raise RuntimeDenied('captured Memory source changed')
            memory.check()
            original,profile,raw=self._read(worker,binding,message.original_message())
            if (raw!=issued.context or self._effect(binding,PLAN_NOW)!=issued.marker or
                    original!=capture.original or policy_descriptor()!=capture.policy or
                    packed(snapshot(profile,memory_epoch=memory.snapshot.epoch))!=packed(capture.profile)):
                raise RuntimeDenied('captured planning provenance changed')
        held=_HeldPlan(check)
        try:
            held.check();yield held;held.check()
        finally:active=False


class _HeldPlan:
    def __init__(self,check):self._check=check
    def check(self):self._check()
