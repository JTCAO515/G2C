"""TRIP-NEEDS-SOURCE@1: actual B source capture and canonical final lease.

The retained bytes are data. Only an active issued publication lease can release
an effect; no DTO/hash/version or caller callback is accepted as authority.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
import base64
import json
import threading

from cj_needs.contract_v1 import encode_snapshot,encode_revision,decode_snapshot,decode_revision
from cj_needs.revision_lease import RevisionLease,LeaseUnavailable
from cj_message.domain import Command
from cj_message.needs_binding import needs_scope_for
from cj_run.core import Denied
from .domain import packed

_FACTORY=object()


@dataclass(frozen=True,repr=False,init=False)
class CapturedNeeds:
    binding: object
    raw: bytes
    def __init__(self,binding,raw,*,_factory=None):
        if _factory is not _FACTORY:raise TypeError('canonical capture required')
        object.__setattr__(self,'binding',binding);object.__setattr__(self,'raw',raw)
    def records(self):
        value=json.loads(self.raw)
        return decode_snapshot(base64.b64decode(value['snapshot'])),tuple(
            decode_revision(base64.b64decode(raw)) for raw in value['revisions'])


class NeedsSourceAuthority:
    def __init__(self,reader,message_context,revision_lease,token_supplier,*,max_revisions,max_bytes):
        if any(type(v) is not int or v<1 for v in (max_revisions,max_bytes)):
            raise ValueError('explicit positive source bounds required')
        self.reader,self.message_context,self.revision_lease=reader,message_context,revision_lease
        self.token_supplier=token_supplier
        self.max_revisions,self.max_bytes=max_revisions,max_bytes
        self._captures={}
        self._active=ContextVar('trip_needs_publication',default=None)

    def capture(self,binding):
        token=self.token_supplier()
        with self.message_context.hold_for_effect(binding) as lease:
            principal=self.message_context.admit()
            stored=lease.original_message()
            command=Command.parse_v2(stored.raw)
            if command.needs_reference is None:raise Denied('explicit original NEEDS reference required')
            needs_id,revision=command.needs_reference
            reference=lease.reference.public_value()
            def project(operation,context):
                identity=lambda value:(value.issuer,value.subject,value.audience)
                if identity(operation.metadata.principal)!=identity(principal) or identity(context.principal)!=identity(principal):
                    raise Denied('original source principal mismatch')
                if operation.metadata.scope!=needs_scope_for(binding.scope):
                    raise Denied('original source namespace mismatch')
                snapshot=operation.detail(needs_id)
                if snapshot is None or snapshot.version!=revision:raise Denied('original NEEDS revision changed')
                if not 1<=revision<=self.max_revisions:raise Denied('source revision bound exceeded')
                revisions=[];consumed=len(snapshot.content)
                for version in range(1,revision+1):
                    item=operation.revision(needs_id,version)
                    if item is None:raise Denied('complete original source history required')
                    consumed+=len(item.original_input)+len(item.content)
                    if consumed>self.max_bytes:raise Denied('source input bound exceeded')
                    revisions.append(item)
                from cj_feasibility.v1 import check_constraints
                report=check_constraints(snapshot,tuple(revisions)).report
                if report.status=='INVALID':raise Denied('original source history invalid')
                raw=packed(dict(version='TRIP-NEEDS-SOURCE@1',reference=reference,
                    needs_scope=operation.metadata.scope,needs_id=needs_id,revision=revision,
                    content_sha256=sha256(snapshot.content).hexdigest(),
                    snapshot=base64.b64encode(encode_snapshot(snapshot)).decode(),
                    revisions=[base64.b64encode(encode_revision(r)).decode() for r in revisions]))
                if len(raw)>self.max_bytes:raise Denied('source envelope bound exceeded')
                if operation.detail(needs_id)!=snapshot:raise Denied('source changed during capture')
                return raw
            raw=self.reader.read(token,project)
            lease.check(binding)
        capture=CapturedNeeds(binding,raw,_factory=_FACTORY)
        self._captures[binding]=capture
        return capture

    @contextmanager
    def hold_for_publication(self,binding):
        capture=self._captures.get(binding)
        if capture is None:raise Denied('original capture unavailable')
        token=self.token_supplier()
        with self.message_context.hold_for_effect(binding) as message, self.revision_lease.hold(token,binding) as check:
            state=(binding,capture,check,threading.get_ident(),message)
            active=self._active.set(state)
            try:
                check()
                yield lambda:self.check(binding,capture)
                self.check(binding,capture)
            finally:self._active.reset(active)

    def check(self,binding,capture):
        state=self._active.get()
        if (state is None or state[0]!=binding or state[1] is not capture
                or self._captures.get(binding) is not capture or state[3]!=threading.get_ident()):
            raise LeaseUnavailable('canonical source publication lease unavailable')
        state[4].check(binding)
        state[2]()
        return True
