"""Fixed formal-data projection inside B's canonical strict read lifetime.

No alternate AUTH, SQL, resolver, dispatch, writer or publication lease. B305
runtime read/write permissions and writer-fence acceptance remain separate.
"""
from dataclasses import dataclass
from cj_needs.protected_read import ProtectedReader
from cj_needs.contract_v1 import encode_snapshot,encode_revision
from .current_read import ReadLimits,ReadWithheld,_project_current
from .formal_v1 import check_constraints,INPUT_PROFILE
from .v1 import VERSION as FACADE_VERSION

VERSION='CJ-FEASIBILITY-FORMAL-CURRENT@1'


@dataclass(frozen=True)
class FormalReadLimits:
    read: ReadLimits
    max_envelope_bytes: int

    def __post_init__(self):
        if type(self.read) is not ReadLimits:
            raise ValueError('fixed canonical read limits required')
        if type(self.max_envelope_bytes) is not int or self.max_envelope_bytes<1:
            raise ValueError('explicit positive formal envelope bound required')


@dataclass(frozen=True,repr=False)
class CurrentFormalNeedsRead:
    reader: ProtectedReader | None = None
    limits: FormalReadLimits | None = None

    def __post_init__(self):
        if self.reader is not None and type(self.reader) is not ProtectedReader:
            raise ValueError('canonical NEEDS ProtectedReader required')
        if self.limits is not None and type(self.limits) is not FormalReadLimits:
            raise ValueError('explicit fixed formal read bounds required')

    def read(self,token,needs_id):
        reader,limits=self.reader,self.limits
        if reader is None or limits is None:raise ReadWithheld('READ_UNCONFIGURED')
        def project(operation,context):
            def evaluate(snapshot,revisions):
                return check_constraints(encode_snapshot(snapshot),
                    tuple(encode_revision(revision) for revision in revisions),
                    max_revisions=limits.read.max_revisions,
                    max_input_bytes=limits.max_envelope_bytes).report
            return _project_current(operation,context,needs_id,limits=limits.read,
                evaluate_report=evaluate,wire_version=VERSION,
                facade_version=FACADE_VERSION,input_profile=INPUT_PROFILE)
        # No private encoding, DTO extraction or requester callback after this.
        return reader.read(token,project)
