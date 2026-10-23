"""CJ019 internal lifecycle commands; reuse CJ011 domain types and authority."""
from dataclasses import dataclass
import json

from cj_memory.domain import InvalidInput


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
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise InvalidInput('duplicate field')
                result[key] = value
            return result
        if type(raw) is not bytes or len(raw) > 32768:
            raise InvalidInput('bytes required')
        try:
            obj = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        except (ValueError, UnicodeError):
            raise InvalidInput('invalid JSON') from None
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
