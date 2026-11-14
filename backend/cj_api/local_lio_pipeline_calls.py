"""Bounded fan-out over the existing registered, one-send worker streams.

Advance every selected request once under its original worker dispatch fence,
then drain their already-started responses outside those fences. There are no
threads sharing worker/Memory state, hidden batched queries, retries or new exits.
One understanding slot is reserved conservatively before generation begins.
Account/RUN/financial limits may refuse earlier; these ceilings never raise them.
"""
from contextlib import ExitStack
from dataclasses import dataclass


class PipelineCapacity(ValueError):pass


@dataclass(frozen=True)
class Call:
    kind:str
    registration:str
    argument:object
    references:tuple=()


class PipelineCalls:
    def __init__(self,worker,binding):
        self.worker,self.binding=worker,binding
        self.model=1
        self.gaode=0
        self._sequence=0

    def parallel(self,calls):
        """All actual sends count, including unsuccessful/UNKNOWN outcomes.

        Reserves the complete fan-out before any dispatch; a later failure never
        returns that allowance or starts a replacement attempt. The reserved
        understanding slot is included in the six-call ceiling, not evidence of
        an actual supplier call. Actual usage remains in the original journal.
        """
        models=sum(call.kind=='model'for call in calls)
        gaode=sum(call.kind=='gaode'for call in calls)
        if any(call.kind not in ('model','gaode')for call in calls):
            raise ValueError('explicit pipeline call kind required')
        if self.model+models>6 or self.gaode+gaode>45:
            raise PipelineCapacity('complete fan-out exceeds the per-plan allowance')
        self.model+=models;self.gaode+=gaode
        streams=[];first=[]
        with ExitStack()as pending:
            for call in calls:
                key='lio4.pipeline.'+str(self._sequence);self._sequence+=1
                stream=self.worker._registered_stream(self.binding,key,call.registration,call.argument,
                    message_refs=call.references)
                pending.callback(stream.close)
                streams.append(stream)
                first.append(next(stream,''))
            return tuple(head+''.join(stream)for head,stream in zip(first,streams,strict=True))
