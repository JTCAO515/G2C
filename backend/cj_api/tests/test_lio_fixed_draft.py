"""Original synthetic candidate regression, never a supplier replay or grant."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from cj_api.local_lio_planning import grouped_draft_guidance,NATIONAL_GROUPED_DRAFT
from cj_draft.grouped_plan import LioGroupedPlanPublisher
from cj_trip.domain import packed
from cj_trip.structured import FieldRejected
from cj_trip.structured_v2 import validate_document

CASE=json.loads((Path(__file__).parent/'fixtures/lio991-duplicate-fixed.json').read_bytes())


def normalize(raw,fields):
    capture=SimpleNamespace(records=lambda:(SimpleNamespace(fields=fields),()))
    model=LioGroupedPlanPublisher._model_plan(None,raw,None,capture)
    document=dict(content_version='structured.2',title=model['title'],items=model['items'],sources=[])
    validate_document(document)
    return model


class FixedDraft(unittest.TestCase):
    def test_original_bytes_remain_rejected_at_the_actual_duplicate_item_guard(self):
        raw=CASE['draft_utf8'].encode()
        self.assertEqual(sha256(raw).hexdigest(),CASE['draft_sha256'])
        with self.assertRaises(FieldRejected)as caught:normalize(raw,CASE['source_fields'])
        self.assertEqual((caught.exception.field,caught.exception.rule),('items[1].id','duplicate global item ID'))

    def test_compliant_new_suggestions_preserve_the_one_original_locked_meeting(self):
        # This is a compliant model fixture, not production repair/deduplication.
        value=json.loads(CASE['draft_utf8'])
        fixed_id=CASE['source_fields']['fixed_items'][0]['item_id']
        value['days'][0][1]=[row for row in value['days'][0][1]if row[0]!=fixed_id]
        model=normalize(packed(value),CASE['source_fields'])
        preserved,=[row for row in model['items']if row['id']==fixed_id]
        self.assertEqual(preserved['fixed'],dict(state='known',value=True))
        self.assertEqual((preserved['schedule']['start']['time']['value'],preserved['schedule']['end']['time']['value']),('09:00','10:00'))
        self.assertNotIn(fixed_id,model['proposed_subjects'])
        self.assertEqual(len({row['id']for row in model['items']}),len(model['items']))

    def test_actual_fixed_ids_are_explicitly_excluded_from_new_suggestions_without_mutating_source(self):
        fields=deepcopy(CASE['source_fields']);before=packed(fields)
        guidance=grouped_draft_guidance(fields)
        self.assertIn(json.dumps([fields['fixed_items'][0]['item_id']],separators=(',',':')),guidance)
        self.assertIn('including on a first plan',guidance)
        self.assertIn('Return only NEW suggested stops',guidance)
        self.assertEqual(packed(fields),before)
        self.assertEqual(grouped_draft_guidance(dict(fixed_items=[])),NATIONAL_GROUPED_DRAFT)


if __name__=='__main__':unittest.main()
