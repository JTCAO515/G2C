"""Additive typed lifecycle inputs. Context is checked by B before Memory mutation."""
from dataclasses import dataclass
import json
from cj_memory.domain import Command,Conflict,InvalidInput
from cj_memory.typed import ContextRef,decode,packed,TypedCommand,travel_selection
from .domain import Action
from .edit import Edit
from cj_memory_withdrawal.stop_use import StopUse

VERSION='MEMORY-management.2'


@dataclass(frozen=True)
class TypedAction(Action):
    @classmethod
    def parse(cls,raw):
        value=decode(raw)
        if value.pop('version',None)!=VERSION:raise InvalidInput('typed management version required')
        old=Action.parse(packed(value))
        return cls(old.action_id,old.operation,old.item_id,old.expected_version,old.expected_source_version,raw)


@dataclass(frozen=True)
class TypedEdit(Edit):
    context: object

    @classmethod
    def parse(cls,raw):
        value=decode(raw)
        if value.pop('version',None)!=VERSION or 'context' not in value:
            raise InvalidInput('typed edit version/context required')
        context=value.pop('context')
        if context is not None:
            if (type(context) is not dict or set(context)!={'kind','id','expected_version'}
                    or context['kind']!='travel' or type(context['expected_version']) is not int
                    or context['expected_version']<1):raise InvalidInput('typed edit context shape')
            context=travel_selection({'id':context['id'],'expected_version':context['expected_version']})
        old=Edit.parse(packed(dict(value,version='MEMORY-MANAGEMENT-EDIT@1')))
        return cls(old.action_id,old.operation,old.item_id,old.expected_version,old.expected_source_version,
                   old.text,raw,context)

    def command(self,original):
        from cj_memory.typed import STORED_VERSION
        value=json.loads(original.raw)
        if original.extent=='long_term':
            if self.context is not None:raise Conflict('edit cannot change original scope')
            kind,version='legacy',None
        else:
            if (original.context_kind!='travel' or self.context is None
                    or self.context.id!=original.context_id):
                raise Conflict('edit cannot retarget original context')
            kind,version='travel',self.context.expected_version
        legacy=super().command(original) if original.schema_version==1 else None
        if legacy is not None:value=json.loads(legacy.raw)
        else:
            import hashlib
            value.update(operation_id=self.action_id,text=self.text,
                         source_id='edit-v1:'+hashlib.sha256(self.raw).hexdigest(),source_version=1)
        value.update(version=STORED_VERSION,context_kind=kind,context_version=version)
        return TypedCommand.parse(packed(value))


@dataclass(frozen=True,repr=False)
class TypedStopUse(StopUse):
    @classmethod
    def parse(cls,raw):
        value=decode(raw)
        if value.pop('version',None)!='MEMORY-STOP-USE@2':raise InvalidInput('typed stop-use version required')
        old=StopUse.parse(packed(dict(value,version='MEMORY-STOP-USE@1')))
        return cls(old.action_id,old.operation,old.item_id,old.expected_version,old.source_id,
                   old.expected_source_version,raw)


def parse_action(raw):
    value=decode(raw)
    if value.get('version')=='MEMORY-STOP-USE@2':return TypedStopUse.parse(raw)
    if value.get('operation')=='edit':return TypedEdit.parse(raw)
    return TypedAction.parse(raw)
