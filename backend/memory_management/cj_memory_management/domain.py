"""CJ019 internal lifecycle commands; reuse CJ011 domain types and authority."""
from dataclasses import dataclass

from cj_memory.domain import InvalidInput, strict_object


@dataclass(frozen=True)
class Action:
    action_id: str
    operation: str
    item_id: str
    expected_version: int
    expected_source_version: int
    raw: bytes

    @classmethod
    def parse(cls, raw):
        obj = strict_object(raw)
        if type(obj) is not dict or set(obj) != set(cls.__dataclass_fields__) - {'raw'}:
            raise InvalidInput('unsupported fields')
        for key in ('action_id', 'item_id', 'operation'):
            if type(obj[key]) is not str or not obj[key].strip() or len(obj[key]) > 4096:
                raise InvalidInput('invalid field')
        if obj['operation'] not in ('pause', 'resume'):
            raise InvalidInput('unsupported operation')
        for key in ('expected_version', 'expected_source_version'):
            if type(obj[key]) is not int or obj[key] < 1:
                raise InvalidInput('invalid version')
        return cls(**obj, raw=raw)
