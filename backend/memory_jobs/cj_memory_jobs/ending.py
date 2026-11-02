"""Explicit segmented ending jobs over the original queue, consent and receipts."""
from dataclasses import dataclass,replace

from cj_message.source import SourceQuery,EndQuery
from cj_message.domain import InvalidInput as MessageInvalidInput
from cj_memory.domain import strict_object,InvalidInput as MemoryInvalidInput
from .codec import InvalidInput,Conflict,Unavailable,job_identity
from .ending_source import EndingSegment,with_ending_source

VERSION='MEMORY-END-JOBS@1'


@dataclass(frozen=True,repr=False)
class EndingCommand:
    job_id:str
    attempt_id:str
    segment:EndingSegment
    raw:bytes

    @property
    def query(self):return self.segment.source

    @classmethod
    def parse(cls,raw):
        if type(raw) is not bytes or not 0<len(raw)<=32768:
            raise InvalidInput('bounded original ending command required')
        try:
            value=strict_object(raw)
            if (type(value) is not dict or set(value)!={'version','job_id','attempt_id','source','end'}
                    or value['version']!=VERSION):
                raise InvalidInput('explicit ending job fields required')
            source=value['source'];end=value['end']
            if (type(source) is not dict or set(source)!={'conversation_id','generation','epoch','after','through',
                    'source_version','withdrawal_epoch','mode'} or type(end) is not dict
                    or set(end)!={'conversation_id','generation','epoch','through'}):
                raise InvalidInput('exact ending source and actual head comparison required')
            return cls(job_identity(value['job_id']),job_identity(value['attempt_id']),
                EndingSegment(SourceQuery(**source),EndQuery(**end)),raw)
        except (MemoryInvalidInput,MessageInvalidInput,RecursionError):
            raise InvalidInput('invalid original ending command') from None


def with_original_source(context,row,policy,project,*,probe_policy):
    """Dispatch by the explicit original version, never by a failed parser."""
    try:value=strict_object(row[1])
    except (MemoryInvalidInput,RecursionError):
        raise Unavailable('stored original source command unavailable') from None
    if type(value) is not dict or value.get('version') not in (VERSION,'MEMORY-JOBS@1'):
        raise Unavailable('stored original source version unavailable')
    if value['version']==VERSION:
        command=EndingCommand.parse(row[1])
        return with_ending_source(context,command.segment,policy,project,probe_policy=probe_policy)
    source,mode=row[3],row[5];c=source.cursor
    query=SourceQuery(c.conversation_id,c.generation,c.epoch,c.after,c.through,
                      source.source_version,source.withdrawal_epoch,mode)
    return context.with_enabled_source(query,policy,project)


def checked_end(context,segment,policy):
    """Return only B's genuine end after its bounded, protected head read."""
    actual=[]
    def project(snapshot):
        actual.append(snapshot.end)
        return b'actual-immutable-ending-head'
    q,e=segment.source,segment.end
    context.with_enabled_source(replace(q,after=max(0,e.through-100),through=e.through),policy,project)
    return actual[0]


class _Ending:
    def __init__(self,*args,ending_command,actual_end,**kwargs):
        super().__init__(*args,**kwargs)
        self.ending_command,self.actual_end=ending_command,actual_end

    def _bound(self,query):
        expected=replace(self.ending_command.query,mode='incremental')
        if query!=expected:raise Conflict('original ending segment differs')
        row,output=super()._bound(self.ending_command.query)
        if row[1]!=self.ending_command.raw:
            raise Conflict('original ending head differs')
        return row,output

    def _input(self,snapshot):
        return super()._input(replace(snapshot,end=self.actual_end))


from .policy_v2 import ProcessingSourcePolicyV2,ResultSourcePolicyV2


class EndingProcessingPolicy(_Ending,ProcessingSourcePolicyV2):
    pass


class EndingPublicationPolicy(_Ending,ResultSourcePolicyV2):
    pass


class EndingCollectionAdapter:
    """Explicit B bridge; its request uses the protected incremental reader.

    Logical purpose/end head remain in the original C job. Data2/output2 and
    original publication2 grammar stay unchanged. No provider/Meter lives here.
    """
    from .model_v2 import NoEligibleSource as no_eligible_error

    def __init__(self,collection):self.collection=collection

    def processing_policy(self,*args,**kwargs):
        return self.collection.ending_processing_policy(*args,**kwargs)

    def publication_policy(self,*args,**kwargs):
        return self.collection.ending_publication_policy(*args,**kwargs)

    def query_publication_in_context(self,*args,**kwargs):
        return self.collection.query_publication_v2_in_context(*args,**kwargs)

    def transition_original_in_context(self,*args,**kwargs):
        return self.collection.transition_original_in_context(*args,**kwargs)
