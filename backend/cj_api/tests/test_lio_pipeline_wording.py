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
        for response,facts in ((b'{',()),(packed(dict(version=WORDING,items=[dict(item_id='foreign',reason=None,reason_refs=[],tip=None)])),())):
            with self.assertRaises(WordingUnavailable):apply_wording(compiled.document,((items,response),),locale='en',facts=facts)
            self.assertEqual(compiled.document,before)

    def test_reason_citing_a_default_factor_is_dropped_not_the_plan(self):
        # HK run -43 (2026-11-25): this case used to refuse the whole plan (stage=word,
        # "only existing known/memory reason factors allowed"). Now only the reason goes:
        # a default factor never reaches public wording, and everything else is unchanged.
        compiled,items,reply=self.case();before=deepcopy(compiled.document)
        value=apply_wording(compiled.document,((items,reply),),locale='en',facts=(ProfileFact('interests','default','history'),))
        selected={row['item_id']for row in items}
        for old,new in zip(before['items'],value['items'],strict=True):
            if old['id']in selected:
                self.assertIsNone(new['note']);self.assertEqual(new['reason_refs'],[])
                self.assertEqual({k:v for k,v in old.items()if k not in ('note','reason_refs','tip')},
                    {k:v for k,v in new.items()if k not in ('note','reason_refs','tip')})
            else:self.assertEqual(new,old)
        self.assertEqual(compiled.document,before)

    def test_blank_reason_becomes_no_reason_not_an_unsavable_note(self):
        # HK run 4fb238dc (2026-11-26, 春熙路): the schema allows an empty reason string, and an
        # empty or blank note fails the saved itinerary's bounded-text check after wording.
        from cj_trip.structured_v4 import _optional_text
        compiled,items,_=self.case()
        for reason in ('','  ','\n'):
            with self.subTest(reason=repr(reason)):
                reply=packed(dict(version=WORDING,items=[dict(item_id=row['item_id'],
                    reason=reason,reason_refs=['interests'],tip=None)for row in items]))
                result=apply_wording(compiled.document,((items,reply),),
                    locale='en',facts=(ProfileFact('interests','known','history'),))
                for item in result['items']:
                    _optional_text(item['note'])
                    if item['id']in {row['item_id']for row in items}:
                        self.assertIsNone(item['note']);self.assertEqual(item['reason_refs'],[])

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
