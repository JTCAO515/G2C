"""New optional-parameter profile, old profile preservation and real no-save holds."""
from copy import deepcopy
import json
import unittest
from jsonschema import Draft202012Validator
from cj_agent.lio_intake_optional_schema import OptionalIntake,SYSTEM,response_format,response_format_sha256
from cj_agent.lio_intake_flow_schema import response_format as old_format
from cj_api.lio_flow_intake import parse_flow
from cj_api.local_lio_national import publication_held
from cj_needs.domain import InvalidInput
from test_lio_planning_flow import flow,original


class OptionalIntakeChecks(unittest.TestCase):
    def test_explicit_version_and_original_index_do_not_mutate_old_profile(self):
        before=old_format(0)
        wire=flow('去成都玩三天');wire['version']='LIO-planning-intake.8'
        Draft202012Validator(response_format(0)['json_schema']['schema']).validate(wire)
        intake,_,_=parse_flow(json.dumps(wire),(original('去成都玩三天'),),(),'current',None,schema=OptionalIntake)
        self.assertEqual(intake.duration_days,3)
        self.assertEqual(intake.start_date,{'state':'missing'})
        self.assertEqual(intake.extraction['fields']['party_size'],{'state':'missing'})
        self.assertEqual(old_format(0),before)
        self.assertFalse(Draft202012Validator(before['json_schema']['schema']).is_valid(wire))
        self.assertNotEqual(response_format_sha256(0),response_format_sha256(1))
        for change in ('index','version','invented-date','invented-party'):
            value=deepcopy(wire)
            if change=='index':value['current_source_index']=1
            elif change=='version':value['version']='LIO-planning-intake.7'
            elif change=='invented-date':value['start_date']='2026-11-12'
            else:value['party_size']=1
            with self.subTest(change=change),self.assertRaises(InvalidInput):
                parse_flow(json.dumps(value),(original('去成都玩三天'),),(),'current',None,schema=OptionalIntake)

    def test_unknown_party_keeps_explicit_self_but_does_not_invent_a_participant(self):
        from test_lio_intake_start_schema import sample,checked,prepared,CITY
        from cj_api.lio_national_intake import fixed_sources_complete
        from types import SimpleNamespace
        for locale in ('zh','en'):
            value,turns=sample(locale)
            intake=checked(value,turns);fields=prepared(intake,turns)
            self.assertEqual(fields['party_size'],{'state':'missing'})
            self.assertTrue(fixed_sources_complete(intake,fields,turns,CITY))
            self.assertEqual(fields['fixed_items'][0]['applies_to'],['self'])
            replacement=('第一天有人','第一天我') if locale=='zh' else ('On day 1 someone has','On day 1 I have')
            before=turns[1].text;after=before.replace(replacement[1],replacement[0])
            turns=(turns[0],SimpleNamespace(text=after,question_day=turns[1].question_day))
            source=value['extraction']['fields']['fixed_items'][0]['source_ref']
            source['quote']=source['quote'].replace(replacement[1],replacement[0])
            intake=checked(value,turns);fields=prepared(intake,turns)
            self.assertFalse(fixed_sources_complete(intake,fields,turns,CITY))

    def test_undecided_date_does_not_remove_any_actual_hold(self):
        for text in ('没定日期 没定人数','日期还没定','dates are undecided','date is undecided'):
            self.assertFalse(publication_held(text))
        for text in ('日期没定，不要保存','如果日期没定','dates are undecided; do not save',
                     'if dates are undecided','date is undecided; just discuss'):
            self.assertTrue(publication_held(text))
        self.assertIn('Dates and party size are OPTIONAL',SYSTEM)
        self.assertNotIn('must be asked together',SYSTEM)


if __name__=='__main__':unittest.main(verbosity=2)
