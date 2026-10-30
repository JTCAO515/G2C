"""Current manual-source lease over the original B readonly runtime/fence."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import base64
import threading
from cj_auth.interfaces import AdmissionStatus
from cj_api.local_app import scope_for
from cj_message.needs_binding import needs_scope_for
from cj_needs.runtime import ReadOnlyRuntimeRepository
from cj_needs.contract_v1 import encode_snapshot,encode_revision,decode_snapshot,decode_revision
from cj_needs.domain import Denied
from .domain import packed


@dataclass(frozen=True,repr=False)
class CurrentSource:
    raw:bytes
    def records(self):
        data=json.loads(self.raw)
        return decode_snapshot(base64.b64decode(data['snapshot'])),tuple(decode_revision(base64.b64decode(r)) for r in data['revisions'])


class CurrentNeedsSource:
    def __init__(self,database,checker,token,reader):
        self.database,self.checker,self.token,self.reader=database,checker,token,reader
        self.issued=None;self.active=None
    def admit(self):
        result=self.checker.check(self.token)
        if result.status is not AdmissionStatus.ALLOWED:raise Denied('current source admission unavailable')
        return result.principal
    def capture(self,needs_id,expected_version):
        principal=self.admit();owner=scope_for(principal.issuer,principal.subject)
        def project(operation,context):
            if operation.metadata.principal!=principal or context.principal!=principal or operation.metadata.scope!=needs_scope_for(owner):
                raise Denied('current source owner mismatch')
            snapshot=operation.detail(needs_id)
            if snapshot is None or snapshot.version!=expected_version:raise Denied('explicit current source changed')
            if not 1<=snapshot.version<=128:raise Denied('source history bound exceeded')
            revisions=[];size=len(snapshot.content)
            for version in range(1,snapshot.version+1):
                revision=operation.revision(needs_id,version)
                if revision is None:raise Denied('full source history required')
                size+=len(revision.content)+len(revision.original_input)
                if size>4_000_000:raise Denied('source byte bound exceeded')
                revisions.append(revision)
            from cj_feasibility.v1 import check_constraints
            if check_constraints(snapshot,tuple(revisions)).status=='INVALID':raise Denied('source history invalid')
            raw=packed(dict(version='TRIP-CURRENT-NEEDS@1',snapshot=base64.b64encode(encode_snapshot(snapshot)).decode(),
                revisions=[base64.b64encode(encode_revision(r)).decode() for r in revisions]))
            if operation.detail(needs_id)!=snapshot:raise Denied('source changed while reading')
            return raw
        source=CurrentSource(self.reader.read(self.token,project));self.issued=source;return source
    @contextmanager
    def hold(self,source):
        if source is not self.issued:raise Denied('issued current source required')
        principal=self.admit();owner=scope_for(principal.issuer,principal.subject)
        def guard(stage):
            if self.admit()!=principal:raise Denied('current source identity changed')
        repository=ReadOnlyRuntimeRepository(lambda:self.database.connect(owner),needs_scope_for(owner),guard,strict_close=True)
        snapshot,_=source.records()
        with repository.transaction() as cursor:
            def check():
                guard('source')
                current=repository._snapshot(cursor,snapshot.needs_id)
                if current!=snapshot:raise Denied('current source changed')
            self.active=(source,check,threading.get_ident())
            try:check();yield check;check()
            finally:self.active=None
