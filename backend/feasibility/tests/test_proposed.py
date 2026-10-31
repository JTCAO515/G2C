import json
from copy import deepcopy
from cj_needs.domain import Snapshot,Revision
from cj_feasibility.validator import Candidate
from cj_feasibility.proposed import evaluate
from test_validator import history,item,event,encode


def test_actual_source_candidate_check_does_not_fabricate_snapshot_or_revision():
    before,revisions=history(dict(fixed_items=[item('a',start=event(wall='09:00'),end=event(wall='10:00')),
                                             item('b',start=event(wall='11:00'),end=event(wall='12:00'))]))
    fields=json.loads(before.content);fields['fixed_items'][1]['start']=event(wall='09:30')
    candidate=Candidate(before.needs_id,before.version,encode(fields))
    result=evaluate(before,revisions,candidate,selected_fields=frozenset({'fixed_items'}),selected_item_ids=frozenset({'b'}))
    assert result.status=='CONFLICT'
    assert any(c.code=='DECLARED_OCCUPANCY_OVERLAP' for c in result.checks)
    assert before.content==revisions[-1].content
    assert all(type(r) is Revision for r in revisions) and type(before) is Snapshot


def test_locked_change_uses_original_protection_and_preserves_bilingual_evidence():
    before,revisions=history(dict(fixed_items=[item('a',locked=True)]))
    fields=json.loads(before.content);fields['fixed_items'][0]['description']='changed'
    result=evaluate(before,revisions,Candidate(before.needs_id,before.version,encode(fields)),
        selected_fields=frozenset({'fixed_items'}),selected_item_ids=frozenset({'a'}))
    assert result.status=='CONFLICT'
    assert any(c.code=='LOCKED_ITEM_CHANGED' for c in result.checks)
    assert all(c.zh and c.en for c in result.checks)
