"""Explicit user candidate decision grammar; model output cannot confirm itself."""
from dataclasses import dataclass

from cj_memory.domain import InvalidInput as MemoryInvalidInput, strict_object
from cj_memory.typed import travel_selection
from .codec import InvalidInput, integer, job_identity, pg_identity


VERSION='MEMORY-CANDIDATE@1'


@dataclass(frozen=True,repr=False)
class CandidateAction:
    action_id: str
    job_id: str
    attempt_id: str
    candidate_id: str
    expected_candidate_version: int
    expected_memory_epoch: int
    operation: str
    kind: str | None
    text: str | None
    extent: str | None
    context: object
    occurred_at: str | None
    raw: bytes

    @classmethod
    def parse(cls,raw):
        try:value=strict_object(raw)
        except (MemoryInvalidInput,RecursionError):raise InvalidInput('invalid candidate action') from None
        base={'version','action_id','job_id','attempt_id','candidate_id','expected_candidate_version',
              'expected_memory_epoch','operation'}
        if type(value) is not dict or value.get('version')!=VERSION:
            raise InvalidInput('explicit candidate action version required')
        operation=value.get('operation')
        fields=base if operation=='reject' else base|{'kind','text','extent','context','occurred_at'}
        if operation not in ('confirm','reject') or set(value)!=fields:
            raise InvalidInput('exact candidate action fields required')
        action_id=job_identity(value['action_id']);job_id=job_identity(value['job_id'])
        attempt_id=job_identity(value['attempt_id']);candidate_id=pg_identity(value['candidate_id'],4096)
        integer(value['expected_candidate_version'],1);integer(value['expected_memory_epoch'],1)
        if operation=='reject':
            return cls(action_id,job_id,attempt_id,candidate_id,value['expected_candidate_version'],
                value['expected_memory_epoch'],operation,None,None,None,None,None,raw)
        if value['kind'] not in ('fact','experience','preference') or type(value['kind']) is not str:
            raise InvalidInput('confirmation requires a reviewed concrete kind')
        for field in ('text','occurred_at'):
            pg_identity(value[field],16384)
            if len(value[field])>4096:raise InvalidInput('candidate text exceeds bound')
        extent=value['extent'];context=value['context']
        if extent=='long_term':
            if context is not None:raise InvalidInput('long-term confirmation has no current context')
            selected=None
        elif extent=='current':
            if (type(context) is not dict or set(context)!={'kind','id','expected_version'}
                    or context['kind']!='travel'):
                raise InvalidInput('explicit reviewed travel context required')
            try:selected=travel_selection({'id':context['id'],'expected_version':context['expected_version']})
            except MemoryInvalidInput:raise InvalidInput('invalid reviewed travel context') from None
        else:raise InvalidInput('unsupported candidate extent')
        return cls(action_id,job_id,attempt_id,candidate_id,value['expected_candidate_version'],
            value['expected_memory_epoch'],operation,value['kind'],value['text'],extent,selected,
            value['occurred_at'],raw)
