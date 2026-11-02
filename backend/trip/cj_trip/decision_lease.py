"""Owned accepted-decision lease for bounded C source/Memory composition."""
from contextlib import contextmanager
from contextvars import ContextVar
from threading import get_ident

from .decision_source import current
from .domain import Denied
from .manual_origin import MAX_BYTES

_active=ContextVar('accepted_trip_decision',default=None)
_factory=object()


class DecisionLease:
    def __init__(self,value,principal,scope,guard,*,factory):
        if factory is not _factory:raise TypeError('actual Trip decision issuer required')
        self._value,self._principal,self._scope,self._guard=value,principal,scope,guard
        self._thread=get_ident();self._live=True

    def check(self):
        if not self._live or _active.get() is not self or self._thread!=get_ident():
            raise Denied('Trip decision lease unavailable')
        try:self._guard('decision_lease')
        except BaseException:
            self._live=False
            raise

    @property
    def decision(self):self.check();return self._value

    @property
    def principal(self):self.check();return self._principal

    @property
    def scope(self):self.check();return self._scope


class DecisionAuthority:
    """Trusted Boundary/token composition, never a client DTO or provider grant."""
    def __init__(self,boundary,token):self.boundary,self.token=boundary,token

    @contextmanager
    def hold(self,expected_principal,query,*,max_source_bytes):
        if type(max_source_bytes) is not int or not 1<=max_source_bytes<=MAX_BYTES:
            raise ValueError('explicit bounded accepted decision required')
        if _active.get() is not None:raise Denied('nested Trip decision lease unavailable')
        sentinel=_active.set(_factory);lease=None
        try:
            repository,principal,guard=self.boundary._bind(self.token)
            if principal!=expected_principal:raise Denied('Trip decision identity differs')
            # Existing Repository.transaction owns the real Trip scope row lock,
            # original role/binding, fresh admission and precommit/return guards.
            with repository.transaction() as cursor:
                value=current(repository,cursor,query,max_source_bytes)
                lease=DecisionLease(value,principal,repository.scope,guard,factory=_factory)
                _active.set(lease)
                lease.check()
                yield lease
                lease.check()
        finally:
            if lease is not None:lease._live=False
            _active.reset(sentinel)
