"""MEMORY-MANAGEMENT-EDIT@1: new explicit bytes, original action ledger."""
from dataclasses import dataclass
import hashlib
import json

from cj_memory.domain import Command, InvalidInput, Unavailable
from .domain import Action


@dataclass(frozen=True)
class Edit:
    action_id: str
    operation: str
    item_id: str
    expected_version: int
    expected_source_version: int
    text: str
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
        fields = set(cls.__dataclass_fields__) - {'raw'} | {'version'}
        if type(obj) is not dict or set(obj) != fields:
            raise InvalidInput('unsupported edit fields')
        if obj.pop('version') != 'MEMORY-MANAGEMENT-EDIT@1' or obj['operation'] != 'edit':
            raise InvalidInput('unsupported edit version or operation')
        for key in ('action_id', 'item_id', 'text'):
            if type(obj[key]) is not str or not obj[key].strip() or len(obj[key]) > 4096:
                raise InvalidInput('invalid edit field')
            obj[key].encode('utf-8')
        for key in ('expected_version', 'expected_source_version'):
            if type(obj[key]) is not int or obj[key] < 1:
                raise InvalidInput('invalid version')
        return cls(**obj, raw=raw)

    def command(self, original):
        # Scope, kind, approximate time and canonical identity come from DB only.
        value = json.loads(original.raw)
        value.update(operation_id=self.action_id, text=self.text,
                     source_id='edit-v1:' + hashlib.sha256(self.raw).hexdigest(),
                     source_version=1)
        return Command.parse(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())


def parse_action(raw):
    # Both parsers are exact: the legacy five-field version remains immutable.
    try:
        return Action.parse(raw)
    except InvalidInput:
        try:
            return Edit.parse(raw)
        except InvalidInput:
            from cj_memory_withdrawal.stop_use import StopUse
            return StopUse.parse(raw)


def approve_edit(policy, command, raw):
    if policy is None or policy.evaluate(command, raw) is not True:
        raise Unavailable('explicit current correction approval required')
