"""Additive model data only; existing profile schema fingerprints stay frozen."""
from copy import deepcopy
import unittest
from pydantic import ValidationError

from cj_message.lio_plan_input_schema import PLAN_UNDERSTANDING,PlanUnderstanding
from cj_message.lio_exploration_schema import response_format,response_format_sha256


OLD={
    'LIO-exploration-understanding.1':'e953f01458e15a8d2a00a7ffcd856cedb0e0987112a3f8f349ce7cfb8cac77cb',
    'LIO-exploration-response.1':'0b9d19e67383838d2e2aa97c36faa59d141080fb23ec7c1f4166702d2c44c03f',
    'LIO-exploration-plan-skeleton.1':'cfec01e2c618aba550287a074371c3840b2a8e205f9b5264467627d6a4e25784',
    'LIO-exploration-plan-wording.1':'8fd2b36e673eabbb6c534d4353609a74ba63a49f0f4d2bc7a10356562ae20197'}


class PlanInputSchema(unittest.TestCase):
    def packet(self):
        return dict(version=PLAN_UNDERSTANDING,current_source_index=0,observations=[],
                    companions=[],fixed_items=[],temporary_conditions=[])

    def test_old_four_schema_hashes_unchanged_and_new_profile_is_distinct(self):
        for name,digest in OLD.items():self.assertEqual(response_format_sha256(name),digest)
        schema=response_format(PLAN_UNDERSTANDING)['json_schema']['schema']
        self.assertEqual(schema['properties']['version']['const'],PLAN_UNDERSTANDING)
        self.assertFalse(schema['additionalProperties'])
        PlanUnderstanding.model_validate(self.packet())

    def test_data_cannot_supply_source_or_write_authority_or_omit_fixed_items(self):
        for update in (dict(permission=True),dict(source=dict(protocol='LIO-message.4')),
                       dict(saved=True),dict(intent='save')):
            value=self.packet();value.update(update)
            with self.subTest(update=update),self.assertRaises(ValidationError):PlanUnderstanding.model_validate(value)
        value=self.packet();del value['fixed_items']
        with self.assertRaises(ValidationError):PlanUnderstanding.model_validate(value)

    def test_stated_values_need_bounded_original_reference_shapes(self):
        value=self.packet();value['observations']=[dict(field='start_date',state='known',value='2026-12-01',
            note=None,sources=[dict(source_index=0,quote='26.12.01出发')])]
        PlanUnderstanding.model_validate(value)
        for mutate in (lambda v:v['observations'][0].update(sources=[]),
                       lambda v:v['observations'][0]['sources'][0].update(source_index=-1),
                       lambda v:v['observations'][0].update(field='write_grant')):
            bad=deepcopy(value);mutate(bad)
            with self.assertRaises(ValidationError):PlanUnderstanding.model_validate(bad)


if __name__=='__main__':unittest.main()
