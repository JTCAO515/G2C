"""WP1 typed choices/default disclosure over source-checked planning fields."""
from copy import deepcopy
import re
import unittest

from cj_api.lio_plan_pace import from_needs_fields,saved_summary
from cj_draft.rich_schema import Pace


class PlanPaceTests(unittest.TestCase):
    def test_three_bilingual_known_styles_compile_to_typed_choices_without_mutating_facts(self):
        for word,expected in (('轻松',Pace.RELAXED),('适中',Pace.MODERATE),('紧凑',Pace.PACKED),
                              ('relaxed',Pace.RELAXED),('moderate',Pace.MODERATE),('packed',Pace.PACKED)):
            fields={'pace':dict(state='known',value=word)};before=deepcopy(fields)
            choice=from_needs_fields(fields)
            self.assertEqual((choice.value,choice.defaulted),(expected,False))
            self.assertEqual(fields,before)

    def test_unsettled_pace_uses_only_the_documented_style_default(self):
        for observation in (None,dict(state='missing'),dict(state='unknown'),dict(state='uncertain',note='undecided')):
            fields={}if observation is None else {'pace':observation};before=deepcopy(fields)
            choice=from_needs_fields(fields)
            self.assertEqual((choice.value,choice.defaulted),(Pace.MODERATE,True))
            self.assertEqual(fields,before)
            self.assertNotIn('arrival',fields);self.assertNotIn('party_size',fields)

    def test_known_noncanonical_pace_is_preserved_for_the_legacy_profile(self):
        fields={'pace':dict(state='known',value='alternate according to weather')};before=deepcopy(fields)
        choice=from_needs_fields(fields)
        self.assertIsNone(choice.value);self.assertFalse(choice.defaulted)
        self.assertEqual(fields,before)
        for locale in ('zh','en'):
            text=saved_summary(locale,3,choice,dated=True)
            self.assertNotIn('先按适中'if locale=='zh'else'used a moderate pace',text)

    def test_saved_summary_has_two_to_four_sentences_one_final_question_and_explicit_undated_state(self):
        for locale in ('zh','en'):
            for word in ('轻松','适中','紧凑'):
                pace=from_needs_fields({'pace':dict(state='known',value=word)})
                for dated in (False,True):
                    text=saved_summary(locale,3,pace,dated=dated)
                    self.assertTrue(text.endswith('？'if locale=='zh'else'?'))
                    self.assertEqual(text.count('？')+text.count('?'),1)
                    self.assertTrue(2<=len([x for x in re.split('[。.!?？]',text)if x.strip()])<=4)
                    if not dated:self.assertIn('出发日期'if locale=='zh'else'start date',text)

    def test_default_is_disclosed_and_retained_summary_does_not_claim_a_new_density(self):
        for locale in ('zh','en'):
            pace=from_needs_fields({})
            text=saved_summary(locale,4,pace,dated=True)
            self.assertIn('先按适中'if locale=='zh'else'used a moderate pace',text)
            retained=saved_summary(locale,4,pace,dated=False,retained=True)
            self.assertIn('原有安排已保留'if locale=='zh'else'keeping the original arrangements',retained)
            self.assertNotIn('先按适中'if locale=='zh'else'used a moderate pace',retained)

    def test_fixed_first_legacy_profile_keeps_pace_facts_without_claiming_rich_density(self):
        for locale in ('zh','en'):
            for fields in ({},{'pace':dict(state='known',value='紧凑')}):
                pace=from_needs_fields(fields)
                text=saved_summary(locale,3,pace,dated=True,rich_applied=False)
                self.assertNotIn('紧凑'if locale=='zh'else'packed',text)
                self.assertNotIn('先按适中'if locale=='zh'else'used a moderate pace',text)
                self.assertEqual(pace,from_needs_fields(fields))

    def test_national_tool_descriptions_use_the_confirmed_city_and_keep_legacy_scope(self):
        from cj_api.real_services import NATIONAL_TOOLS,TOOLS
        national={tool['function']['name']:tool['function']for tool in NATIONAL_TOOLS}
        legacy={tool['function']['name']:tool['function']for tool in TOOLS}
        for name in ('place_search','weather'):
            self.assertNotIn('beijing',national[name]['description'].casefold())
            self.assertNotIn('北京',national[name]['description'])
        self.assertNotIn('enum',national['place_search']['parameters']['properties']['city'])
        self.assertNotIn('default',national['place_search']['parameters']['properties']['city'])
        self.assertIn('北京',legacy['place_search']['parameters']['properties']['city']['enum'])


if __name__=='__main__':unittest.main()
