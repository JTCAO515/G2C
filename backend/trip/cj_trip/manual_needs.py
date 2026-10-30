"""TRIP-needs-edit.1: actual current source + same Trip/manual/FEAS checks."""
from dataclasses import dataclass
import json
from .manual import ManualEdit,ManualSave,_prepare
from .structured_v2 import validate_document
from .domain import packed
from cj_needs.domain import identifier


class EditV2(ManualEdit):
    @classmethod
    def parse(cls,raw):return cls._parse(raw,'TRIP-manual-edit.2')


@dataclass(frozen=True)
class NeedsEdit:
    raw:bytes
    needs_id:str
    needs_version:int
    edit:EditV2
    @property
    def request_id(self):return self.edit.request_id
    @classmethod
    def parse(cls,raw):
        if type(raw) is not bytes or not 0<len(raw)<=1_000_000:raise ValueError('bounded needs edit required')
        value=json.loads(raw)
        if type(value) is not dict or set(value)!={'version','needs_reference','edit'} or value['version']!='TRIP-needs-edit.1' or packed(value)!=raw:
            raise ValueError('exact canonical source-bound edit required')
        ref=value['needs_reference']
        if type(ref) is not dict or set(ref)!={'id','expected_version'}:raise ValueError('explicit needs reference required')
        identifier(ref['id'])
        if type(ref['expected_version']) is not int or not 1<=ref['expected_version']<2**63:raise ValueError('positive needs version required')
        return cls(raw,ref['id'],ref['expected_version'],EditV2.parse(packed(value['edit'])))


class NeedsSave(ManualSave):
    @classmethod
    def parse(cls,raw):return cls._parse(raw,'TRIP-needs-save.1')


def prepare(original,edit):return _prepare(original,edit,validate_document)
