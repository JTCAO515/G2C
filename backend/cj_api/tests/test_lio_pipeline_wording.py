"""Wording may change generated prose, never the final plan or protected data."""
from copy import deepcopy
import unittest

from cj_api.lio_pipeline_wording import wording_items,apply_wording
from cj_api.lio_pipeline_model import WordingUnavailable
from cj_message.lio_pipeline_schema import WORDING
from cj_trip.domain import packed
from cj_trip.rich_reasons import ProfileFact
from test_lio_pipeline_compilation import prepared,build


class FinalWording(unittest.TestCase):
    def case(self):
        compiled=build(prepared());document=compiled.document
        items=wording_items(document,compiled.proposed_subjects)
        reply=packed(dict(version=WORDING,items=[dict(item_id=row['item_id'],
            reason='A good fit for your interests.',reason_refs=['interests'],tip='Invented booking promise')for row in items]))
        return compiled,items,reply

    def test_only_generated_sight_meal_prose_changes_without_mutating_source_document(self):
        compiled,items,reply=self.case();before=deepcopy(compiled.document)
        value=apply_wording(compiled.document,((items,reply),),
            locale='en',facts=(ProfileFact('interests','known','history'),))
        selected={row['item_id']for row in items}
        self.assertTrue(selected)
        for old,new in zip(before['items'],value['items'],strict=True):
            if old['id']in selected:
                self.assertEqual(new['note'],'A good fit for your interests.')
                self.assertIsNone(new['tip'])
                self.assertEqual({k:v for k,v in old.items()if k not in ('note','reason_refs')},
                    {k:v for k,v in new.items()if k not in ('note','reason_refs')})
            else:self.assertEqual(new,old)
        self.assertEqual({k:v for k,v in value.items()if k!='items'},
            {k:v for k,v in before.items()if k!='items'})
        self.assertEqual(compiled.document,before)

    def test_default_reason_foreign_id_and_truncated_result_never_partially_change_plan(self):
        compiled,items,reply=self.case();before=deepcopy(compiled.document)
        for response,facts in ((reply,(ProfileFact('interests','default','history'),)),
                (b'{',()),(packed(dict(version=WORDING,items=[dict(item_id='foreign',reason=None,reason_refs=[],tip=None)])),())):
            with self.assertRaises(WordingUnavailable):apply_wording(compiled.document,((items,response),),locale='en',facts=facts)
            self.assertEqual(compiled.document,before)

    def test_late_wording_cannot_make_saved_booking_or_internal_metadata_claims(self):
        compiled,items,_=self.case()
        for reason in ('I have booked your hotel.','行程已为你保存。','tool_call_id=private-example'):
            reply=packed(dict(version=WORDING,items=[dict(item_id=row['item_id'],
                reason=reason,reason_refs=['interests'],tip=None)for row in items]))
            result=apply_wording(compiled.document,((items,reply),),
                locale='en',facts=(ProfileFact('interests','known','history'),))
            for item in result['items']:
                if item['id']in {row['item_id']for row in items}:
                    self.assertIsNone(item['note']);self.assertEqual(item['reason_refs'],[])


if __name__=='__main__':unittest.main()
