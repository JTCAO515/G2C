"""Bounded fan-out over the existing registered, one-send worker streams.

Advance every selected request once under its original worker dispatch fence,
then drain their already-started responses outside those fences. There are no
threads sharing worker/Memory state, hidden batched queries, retries or new exits.
The understanding and enabled final Memory-extraction slots are reserved before
generation begins; both are billable model calls, including empty extraction.
Account/RUN/financial limits may refuse earlier; these ceilings never raise them.
"""
from contextlib import ExitStack
from dataclasses import dataclass

from cj_message.lio_exploration_schema import ExplorationInput
from cj_message.lio_wire import ExplorationOrigin
from cj_trip.domain import packed


class PipelineCapacity(ValueError):pass


@dataclass(frozen=True)
class Call:
    kind:str
    registration:str
    argument:object
    references:tuple=()


def model_call(host,worker,binding,view,profile,system,extra):
    origin=ExplorationOrigin(host.database,binding,worker.messages.query(binding.message_id))
    messages=host._input(worker,view,view.originals[-1].text,extra)
    return Call('model','model.lio_exploration.1',
        ExplorationInput(profile,packed(messages),system,worker.provider,origin),tuple(view.references))


class PipelineCalls:
    def __init__(self,worker,binding,*,prior_model_calls=0):
        self.worker,self.binding=worker,binding
        self.model=prior_model_calls+1+int(worker.lio_memory is not None)
        self.gaode=0
        self._sequence=0

    @property
    def model_slots_left(self):
        """Code allocation only; original live reserve still decides admission."""
        return 6-self.model

    def _reserve(self,models,gaode):
        if self.model+models>6 or self.gaode+gaode>45:
            raise PipelineCapacity('complete fan-out exceeds the per-plan allowance')
        self.model+=models;self.gaode+=gaode

    def resolve_city(self,query):
        """The original one-send city registration consumes the same45 ceiling.

        The host calls this only after full graph preflight. An invalid, refused
        or UNKNOWN attempt does not refund this code allocation or retry it.
        """
        self._reserve(0,1)
        return self.worker.tools.resolve_city(self.worker,self.binding,query)

    def parallel(self,calls):
        """All actual sends count, including unsuccessful/UNKNOWN outcomes.

        Reserves the complete fan-out before any dispatch; a later failure never
        returns that allowance or starts a replacement attempt. The reserved
        understanding and enabled Memory slots are included in the six-call
        ceiling, not evidence of actual calls. Actual usage stays in the journal.
        """
        models=sum(call.kind=='model'for call in calls)
        gaode=sum(call.kind=='gaode'for call in calls)
        if any(call.kind not in ('model','gaode')for call in calls):
            raise ValueError('explicit pipeline call kind required')
        self._reserve(models,gaode)
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
