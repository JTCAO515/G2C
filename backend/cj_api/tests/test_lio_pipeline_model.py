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

    def test_live_code_allocation_keeps_complete_coverage_with_memory_reserved(self):
        from types import SimpleNamespace
        from cj_api.local_lio_pipeline_calls import Call,PipelineCalls
        def stream(*args,**kwargs):yield 'complete skeleton fixture'
        worker=SimpleNamespace(_registered_stream=stream,lio_memory=object())
        calls=PipelineCalls(worker,'current-binding')
        calls.parallel((Call('model','registered-skeleton',object()),))
        self.assertEqual(calls.model_slots_left,3)
        items=[dict(item_id='p-'+str(n),tip=None)for n in range(60)]
        batches=wording_batches(items,available_models=calls.model_slots_left)
        self.assertEqual(len(batches),3)
        self.assertEqual([item for batch in batches for item in batch],items)
        calls.parallel(tuple(Call('model','registered-wording',batch)for batch in batches))
        self.assertEqual(calls.model_slots_left,0)
        with self.assertRaises(WordingUnavailable):wording_batches(items,available_models=0)
        self.assertEqual(wording_batches([],available_models=0),())

    def test_forged_items_missing_items_unknown_reasons_and_truncation_refuse(self):
        items=[dict(item_id='p-1',tip=None)]
        # HK run -43 (2026-11-25): an unsupported reason factor no longer refuses the whole plan;
        # it drops that item's reason (see the test below). Forged, missing, duplicate and
        # truncated output still refuse.
        for rows in ([],[dict(item_id='foreign',reason=None,reason_refs=[],tip=None)],
                     [dict(item_id='p-1',reason=None,reason_refs=[],tip=None)]*2):
            with self.assertRaises(WordingUnavailable):
                parse_wording(packed(dict(version=WORDING,items=rows)),items,allowed_reason_keys={'interests'})
        with self.assertRaises(WordingUnavailable):parse_wording(b'{',items,allowed_reason_keys=set())


    def test_unsupported_reason_factor_drops_only_that_reason(self):
        # HK run -43 (2026-11-25): LIO_PIPELINE_REFUSED stage=word message_sha256=d90d4e1dfddc
        # ("only existing known/memory reason factors allowed") refused a complete plan.
        items=[dict(item_id='p-1',tip='Sourced tip'),dict(item_id='p-2',tip=None),dict(item_id='p-3',tip=None)]
        rows=[dict(item_id='p-1',reason='Your default pace.',reason_refs=['pace'],tip='Sourced tip reworded'),
              dict(item_id='p-2',reason='Fits your interests.',reason_refs=['interests','interests'],tip=None),
              dict(item_id='p-3',reason='Fits your interests.',reason_refs=['interests'],tip=None)]
        with self.assertLogs('cj_usage.audit','INFO')as logs:
            result=parse_wording(packed(dict(version=WORDING,items=rows)),items,allowed_reason_keys={'interests'})
        self.assertEqual(result['p-1'],dict(note=None,reason_refs=[],tip='Sourced tip reworded'))
        self.assertEqual(result['p-2'],dict(note=None,reason_refs=[],tip=None))
        self.assertEqual(result['p-3'],dict(note='Fits your interests.',reason_refs=['interests'],tip=None))
        self.assertEqual(logs.output,['INFO:cj_usage.audit:LIO_WORDING_REASON_DROPPED items=2 of=3'])
        self.assertNotIn('pace',logs.output[0])


if __name__=='__main__':unittest.main()
