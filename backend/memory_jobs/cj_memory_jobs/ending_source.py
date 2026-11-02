"""Bounded ending segments using sequential public source reads, no new store."""
from dataclasses import asdict,dataclass,replace
import base64

from cj_message.source import SourceQuery,EndQuery
from .codec import SourceV2,encode_v2,InvalidInput
from .postgres import encode


@dataclass(frozen=True)
class EndingSegment:
    source:SourceQuery
    end:EndQuery

    def __post_init__(self):
        q,e=self.source,self.end
        if (q.mode!='conversation_end' or (q.conversation_id,q.generation,q.epoch)!=(e.conversation_id,e.generation,e.epoch)
                or q.through>e.through):
            raise InvalidInput('original ending head and contained segment required')


def read_ending_segment(boundary,token,segment,policy_for_context):
    """Source artifact only; not model data, consent or later dispatch authority.

    Verify the actual immutable end at its head using an ordinary bounded tail
    read. Then read the contained segment under the same captured outer identity
    and unchanged generation/epoch. The end cannot append; any lifecycle change
    denies the second read. Both C holders close before the next begins.
    """
    q,e=segment.source,segment.end
    def materialize(context):
        actual_end=None
        probe=replace(q,after=max(0,e.through-100),through=e.through)
        def capture(snapshot):
            nonlocal actual_end
            actual_end=snapshot.end
            return encode(asdict(actual_end))
        context.with_enabled_source(probe,policy_for_context(context),capture)
        def project(snapshot):
            source=SourceV2(snapshot.cursor,snapshot.source_version,snapshot.withdrawal_epoch)
            batch=encode_v2(source,snapshot.messages,'conversation_end')
            return encode(dict(version='CJ020-ending-segment.1',end=asdict(actual_end),
                               batch_utf8_base64=base64.b64encode(batch).decode('ascii')))
        # The purpose is explicitly a new ending-segment protocol. This maps its
        # bounded segment to the existing protected committed-range reader; it is
        # not a fallback on a failed end check or an inferred inactivity signal.
        return context.with_enabled_source(replace(q,mode='incremental'),policy_for_context(context),project)
    return boundary.with_history_context(token,materialize)
