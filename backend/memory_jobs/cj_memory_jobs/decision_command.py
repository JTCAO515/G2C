"""Unpublished original command data; parsing grants no decision/source permit."""
from dataclasses import dataclass,replace

from cj_message.source import SourceQuery,EndQuery
from cj_memory.domain import strict_object,InvalidInput as MemoryInvalid
from cj_trip.decision_source import DecisionQuery
from .codec import InvalidInput
from .consent import EnqueueCommand
from .ending import EndingCommand
from .postgres import encode

VERSION='MEMORY-DECISION-JOBS-DRAFT@1'


@dataclass(frozen=True,repr=False)
class DecisionCommand:
    job_id:str
    attempt_id:str
    query:SourceQuery
    decision:DecisionQuery
    end:EndQuery|None
    raw:bytes

    @property
    def reader_query(self):return self.query if self.end is None else replace(self.query,mode='incremental')

    @classmethod
    def parse(cls,raw):
        if type(raw) is not bytes or not 0<len(raw)<=32768:raise InvalidInput('bounded original decision command required')
        try:
            value=strict_object(raw)
            if (type(value) is not dict or set(value)!={'version','job_id','attempt_id','source','decision','end'}
                    or value['version']!=VERSION):raise InvalidInput('exact decision command fields required')
            decision=value['decision']
            if type(decision) is not dict or set(decision)!={'trip_id','expected_version','content_sha256'}:
                raise InvalidInput('exact accepted decision comparison required')
            selected=DecisionQuery(**decision)
            common=dict(job_id=value['job_id'],attempt_id=value['attempt_id'],source=value['source'])
            if value['end'] is None:
                command=EnqueueCommand.parse(encode(dict(version='MEMORY-JOBS@1',**common)))
                if command.query.mode!='incremental':raise InvalidInput('actual ending head comparison required')
                end=None
            else:
                command=EndingCommand.parse(encode(dict(version='MEMORY-END-JOBS@1',end=value['end'],**common)))
                end=command.segment.end
            return cls(command.job_id,command.attempt_id,command.query,selected,end,raw)
        except (MemoryInvalid,ValueError,TypeError,KeyError,RecursionError) as error:
            raise InvalidInput('original decision command unavailable') from error
