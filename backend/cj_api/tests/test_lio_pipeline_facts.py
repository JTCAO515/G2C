"""Human-facing fact values use accepted locale labels, never profile JSON."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from cj_api.lio_pipeline_wording import profile_facts


def capture(rows):return SimpleNamespace(profile=SimpleNamespace(profile={'factors':rows}))


class PipelineFactPresentation(unittest.TestCase):
    def test_values_are_localized_without_changing_accepted_states_or_source_values(self):
        rows=[dict(factor_key='city',state='default',value='北京'),
              dict(factor_key='interests',state='known',value=['history','food']),
              dict(factor_key='first_visit',state='default',value=True),
              dict(factor_key='dietary',state='not_needed',value=None)]
        before=deepcopy(rows)
        facts=profile_facts(capture(rows),'en');by_key={fact.key:fact for fact in facts}
        self.assertEqual(by_key['city'].display_value,'Beijing (北京)')
        self.assertEqual(by_key['interests'].display_value,'History and culture, Local food')
        self.assertEqual(by_key['first_visit'].display_value,'Yes')
        self.assertEqual(by_key['dietary'].display_value,'No preference')
        self.assertEqual({f.key:f.state for f in facts},{row['factor_key']:row['state']for row in rows})
        self.assertEqual(rows,before)
        zh={f.key:f.display_value for f in profile_facts(capture(rows),'zh')}
        self.assertEqual(zh['city'],'北京');self.assertEqual(zh['interests'],'历史文化、当地美食') # Existing accepted option labels.

    def test_unknown_english_city_gets_disclosed_pinyin_and_unsafe_display_never_leaks_an_id(self):
        rows=[dict(factor_key='city',state='known',value='赣州'),
              dict(factor_key='dietary',state='known',value='run_id=private-example')]
        facts=profile_facts(capture(rows),'en')
        self.assertEqual(facts[0].display_value,'gan zhou (赣州)')
        self.assertNotIn('run_id',facts[1].display_value)
        self.assertEqual(rows[1]['value'],'run_id=private-example')


if __name__=='__main__':unittest.main()
