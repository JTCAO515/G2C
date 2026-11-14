import unittest

from cj_api.lio_pipeline_model import wording_batches,parse_wording,WordingUnavailable
from cj_message.lio_pipeline_schema import WORDING
from cj_trip.domain import packed


class PipelineModel(unittest.TestCase):
    def test_wording_batches_cover_all_items_with_at_most_four_calls(self):
        for count in range(61):
            items=[dict(item_id='p-'+str(n),tip=None)for n in range(count)]
            batches=wording_batches(items)
            self.assertLessEqual(len(batches),4)
            self.assertEqual([item for batch in batches for item in batch],items)

    def test_exact_batch_accepts_existing_reasons_without_inventing_a_tip(self):
        value=dict(version=WORDING,items=[dict(item_id='p-1',reason='Fits your interests.',reason_refs=['interests'],tip='Invented fact')])
        result=parse_wording(packed(value),[dict(item_id='p-1',tip=None)],allowed_reason_keys={'interests'})
        self.assertEqual(result,{'p-1':dict(note='Fits your interests.',reason_refs=['interests'],tip=None)})

    def test_forged_items_missing_items_unknown_reasons_and_truncation_refuse(self):
        items=[dict(item_id='p-1',tip=None)]
        for rows in ([],[dict(item_id='foreign',reason=None,reason_refs=[],tip=None)],
                     [dict(item_id='p-1',reason='Your default',reason_refs=['pace'],tip=None)],
                     [dict(item_id='p-1',reason=None,reason_refs=[],tip=None)]*2):
            with self.assertRaises(WordingUnavailable):
                parse_wording(packed(dict(version=WORDING,items=rows)),items,allowed_reason_keys={'interests'})
        with self.assertRaises(WordingUnavailable):parse_wording(b'{',items,allowed_reason_keys=set())


if __name__=='__main__':unittest.main()
