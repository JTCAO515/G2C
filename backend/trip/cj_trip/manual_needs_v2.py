"""TRIP-needs-edit/save.2: both frozen structured grammars, same source/writer."""
import json
from .domain import Conflict
from .manual import ManualEdit,prepare as prepare_one
from .manual_needs import NeedsEdit,NeedsSave,EditV2,prepare as prepare_two
from .needs_edit_store import NeedsEdits,checked_candidate


class NeedsEditV2(NeedsEdit):
    wire_version='TRIP-needs-edit.2'

    @staticmethod
    def parse_edit(value):
        from .domain import packed
        if type(value) is not dict:raise ValueError('explicit manual edit required')
        version=value.get('version')
        if version=='TRIP-manual-edit.1':return ManualEdit.parse(packed(value))
        if version=='TRIP-manual-edit.2':return EditV2.parse(packed(value))
        raise ValueError('explicit supported manual edit version required')


class NeedsSaveV2(NeedsSave):
    @classmethod
    def parse(cls,raw):return cls._parse(raw,'TRIP-needs-save.2')


def checked(original,request,source,previous_fields):
    version=json.loads(original.content)['content_version']
    if version=='structured.1':
        prepare,expected=prepare_one,'TRIP-manual-edit.1'
        from cj_feasibility.trip_time import evaluate
    elif version=='structured.2':
        prepare,expected=prepare_two,'TRIP-manual-edit.2'
        from cj_feasibility.trip_time_v2 import evaluate
    else:raise ValueError('explicit structured original required')
    if json.loads(request.edit.raw)['version']!=expected:raise ValueError('manual version must match the original Trip')
    candidate=prepare(original,request.edit)
    if evaluate(candidate.content).status=='CONFLICT':raise Conflict('explicit Trip time conflict')
    return checked_candidate(request,source,previous_fields,candidate)


class NeedsEditsV2(NeedsEdits):
    request_type=NeedsEditV2
    check=staticmethod(checked)
    basis_version='needs-manual.2'
