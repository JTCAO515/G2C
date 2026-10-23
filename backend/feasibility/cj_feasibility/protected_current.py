"""Explicit host-only NEEDS current evaluator using the fixed strict producer seam.

No root registration, resolver, alternative AUTH, SQL or caller-selected projector.
"""
from dataclasses import dataclass
from cj_needs.protected_read import ProtectedReader
from .current_read import ReadLimits, ReadWithheld, project_current

VERSION = 'CJ-FEASIBILITY-PROTECTED-CURRENT@0.1.0-rc.1'
NEEDS_COMMIT = '4cc9c815293a4e03225b26adfa228fdd0b50b2e7'


@dataclass(frozen=True, repr=False)
class CurrentNeedsRead:
    """Immutable trusted-host composition. Request only selects token + needs_id."""
    reader: ProtectedReader | None = None
    limits: ReadLimits | None = None

    def __post_init__(self):
        if self.reader is not None and type(self.reader) is not ProtectedReader:
            raise ValueError('canonical NEEDS ProtectedReader required')
        if self.limits is not None and type(self.limits) is not ReadLimits:
            raise ValueError('explicit fixed ReadLimits required')

    def read(self, token: str, needs_id: str) -> bytes:
        reader, limits = self.reader, self.limits
        if reader is None or limits is None:
            raise ReadWithheld('READ_UNCONFIGURED')
        # Projection + all private encoding stay in the producer's strict lifetime.
        # read() itself settles close/current resolver binding and final AUTH before
        # returning the original exact bytes. No encoding or callback follows it.
        return reader.read(token, lambda operation, context:
                           project_current(operation, context, needs_id, limits=limits))
