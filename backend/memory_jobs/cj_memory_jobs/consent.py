"""Versioned per-conversation history intent; parsing alone grants no access."""
from dataclasses import dataclass
from typing import TYPE_CHECKING
from cj_memory.domain import InvalidInput as MemoryInvalidInput, strict_object
from .codec import InvalidInput, integer

if TYPE_CHECKING:
    from cj_message.source import SourceQuery


VERSION = 'MEMORY-HISTORY@1'


@dataclass(frozen=True, repr=False)
class ConsentAction:
    action_id: str
    operation: str
    conversation_id: str
    expected_generation: str
    expected_epoch: int
    expected_source_version: int
    raw: bytes

    @classmethod
    def parse(cls, raw: bytes):
        if type(raw) is not bytes or not 0 < len(raw) <= 32768:
            raise InvalidInput('bounded original history action required')
        try:
            value = strict_object(raw)
        except (MemoryInvalidInput, RecursionError):
            raise InvalidInput('invalid history action') from None
        fields = {'version', 'action_id', 'operation', 'conversation_id',
                  'expected_generation', 'expected_epoch', 'expected_source_version'}
        if type(value) is not dict or set(value) != fields or value.pop('version') != VERSION:
            raise InvalidInput('explicit history action fields required')
        for key, limit in (('action_id', 4096), ('conversation_id', 256),
                           ('expected_generation', 1024)):
            item = value[key]
            if type(item) is not str or not item.strip() or '\0' in item:
                raise InvalidInput('invalid history identity')
            try:
                if len(item.encode('utf-8')) > limit:
                    raise InvalidInput('history identity exceeds bound')
            except UnicodeError:
                raise InvalidInput('invalid history identity') from None
        if value['operation'] not in ('enable', 'disable'):
            raise InvalidInput('explicit enable or disable required')
        integer(value['expected_epoch'])
        integer(value['expected_source_version'])  # Zero means no prior consent row.
        return cls(**value, raw=raw)


@dataclass(frozen=True, repr=False)
class EnqueueCommand:
    job_id: str
    attempt_id: str
    query: 'SourceQuery'
    raw: bytes

    @classmethod
    def parse(cls, raw):
        from cj_message.source import SourceQuery
        from cj_message.domain import InvalidInput as MessageInvalidInput
        from .codec import job_identity
        try:
            value = strict_object(raw)
            if (type(value) is not dict or set(value) != {'version','job_id','attempt_id','source'}
                    or value['version'] != 'MEMORY-JOBS@1'):
                raise InvalidInput('explicit history job fields required')
            source = value['source']
            fields = {'conversation_id','generation','epoch','after','through',
                      'source_version','withdrawal_epoch','mode'}
            if type(source) is not dict or set(source) != fields:
                raise InvalidInput('exact source comparison fields required')
            return cls(job_identity(value['job_id']),job_identity(value['attempt_id']),SourceQuery(**source),raw)
        except (MemoryInvalidInput, MessageInvalidInput, RecursionError):
            raise InvalidInput('invalid history job') from None
