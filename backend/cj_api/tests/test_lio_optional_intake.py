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
    def test_plain_failed_parameter_text_remains_data_without_a_failed_execution_grant(self):
        for text,quote in (('从2026-12-01开始，两个人','两个人'),('Start on 2026-12-01, two people','two people')):
            value=flow('继续',city='北京',days=3,start='2026-12-01',party=2,index=2,questions=())
            value.update(version='LIO-planning-intake.8',planning_request_index=0)
            value['city'].update(source_index=0,quote='北京')
            value['field_sources']=[dict(field='duration_days',source_index=0,quote='三天'),
                dict(field='start_date',source_index=1,quote='2026-12-01'),dict(field='party_size',source_index=1,quote=quote)]
            intake,_,_=parse_flow(json.dumps(value),tuple(map(original,('规划北京三天',text,'继续'))),
                ({'message_id':'completed-request'},{'message_id':'failed-parameters'}),'current',None,schema=OptionalIntake)
            self.assertEqual(intake.start_date,dict(state='known',value='2026-12-01'))
            self.assertEqual(intake.extraction['fields']['party_size'],dict(state='known',value=2))

    def test_translation_cannot_supply_date_or_party_to_an_existing_real_request(self):
        for request,meta,current,city,days_quote,party_quote in (
                ('规划北京三天','请翻译“从2026-12-01开始，两个人”','继续','北京','三天','两个人'),
                ('Plan Beijing for three days','Please translate "Start on 2026-12-01, two people"',
                 'Continue','Beijing','three days','two people')):
            value=flow(current,city=city,days=3,start='2026-12-01',party=2,index=2,questions=())
            value.update(version='LIO-planning-intake.8',planning_request_index=0)
            value['city'].update(source_index=0,quote=city)
            value['field_sources']=[dict(field='duration_days',source_index=0,quote=days_quote),
                dict(field='start_date',source_index=1,quote='2026-12-01'),
                dict(field='party_size',source_index=1,quote=party_quote)]
            turns=tuple(map(original,(request,meta,current)))
            with self.subTest(meta=meta):
                intake,_,snapshot=parse_flow(json.dumps(value),turns,
                    ({'message_id':'real-request'},{'message_id':'unknown-translation'}),
                    'current',None,schema=OptionalIntake)
                self.assertEqual(intake.start_date,dict(state='missing'))
                self.assertEqual(intake.extraction['fields']['party_size'],dict(state='missing'))
                self.assertNotIn('start_date',snapshot);self.assertNotIn('party_size',snapshot)
                self.assertEqual(intake.duration_days,3)

    def test_nonplanning_source_selection_covers_quotes_without_discarding_real_sibling_facts(self):
        from cj_api.lio_flow_intake import _nonplanning_fact_source
        cases=[('“从2026-12-01开始，两个人”','两个人',True),
               ('He said: start on 2026-12-01 with two people.','two people',True),
               ('请翻译从2026-12-01开始，两个人','两个人',True),
               ('我12月1日出发。请翻译“明天出发”。','12月1日',False),
               ('我12月1日出发。请翻译“明天出发”。','明天',True),
               ('就定在“2026-12-01”出发，两个人','2026-12-01',False)]
        for text,quote,blocked in cases:
            with self.subTest(text=text,quote=quote):self.assertEqual(_nonplanning_fact_source(text,quote),blocked)

    def test_real_date_and_quoted_party_in_same_message_have_separate_provenance(self):
        text='我从2026-12-01出发。请翻译“两个人”。'
        value=flow('继续',city='北京',days=3,start='2026-12-01',party=2,index=2,questions=())
        value.update(version='LIO-planning-intake.8',planning_request_index=0)
        value['city'].update(source_index=0,quote='北京')
        value['field_sources']=[dict(field='duration_days',source_index=0,quote='三天'),
            dict(field='start_date',source_index=1,quote='2026-12-01'),dict(field='party_size',source_index=1,quote='两个人')]
        intake,_,snapshot=parse_flow(json.dumps(value),tuple(map(original,('规划北京三天',text,'继续'))),
            ({'message_id':'real-request'},{'message_id':'mixed-input'}),'current',None,schema=OptionalIntake)
        self.assertEqual(intake.start_date,dict(state='known',value='2026-12-01'))
        self.assertEqual(intake.extraction['fields']['party_size'],dict(state='missing'))
        self.assertIn('start_date',snapshot);self.assertNotIn('party_size',snapshot)

    def test_translation_first_then_real_parameter_has_independent_source_scope(self):
        from cj_api.lio_flow_intake import _nonplanning_fact_source
        for text,real,translated in (
                ('请翻译“从2026-12-01开始，两个人”。我从2026-12-10出发，三个人。','2026-12-10','2026-12-01'),
                ('请翻译“两个人”，我从2026-12-10出发。','2026-12-10','两个人'),
                ('Please translate "Start on 2026-12-01, two people". I start on 2026-12-10 with three people.',
                 '2026-12-10','2026-12-01'),
                ('Please translate "two people", and we actually start on 2026-12-10 with three people.',
                 '2026-12-10','two people')):
            with self.subTest(text=text):
                self.assertFalse(_nonplanning_fact_source(text,real))
                self.assertTrue(_nonplanning_fact_source(text,translated))
                english=text.startswith('Please')
                party=3 if 'three people'in text or'三个人'in text else None
                value=flow('Continue',city='Beijing'if english else'北京',days=3,start=real,party=party,index=2,questions=())
                value.update(version='LIO-planning-intake.8',planning_request_index=0)
                value['city'].update(source_index=0,quote='Beijing'if english else'北京')
                value['field_sources']=[dict(field='duration_days',source_index=0,quote='three days'if english else'三天'),
                    dict(field='start_date',source_index=1,quote=real)]
                if party is not None:value['field_sources'].append(dict(field='party_size',source_index=1,quote='three people'if english else'三个人'))
                request='Plan Beijing for three days'if english else'规划北京三天'
                intake,_,snapshot=parse_flow(json.dumps(value),tuple(map(original,(request,text,'Continue'))),
                    ({'message_id':'real-request'},{'message_id':'mixed'}),'current',None,schema=OptionalIntake)
                self.assertEqual(intake.start_date,dict(state='known',value=real))
                self.assertEqual(intake.extraction['fields']['party_size'],dict(state='missing')if party is None else dict(state='known',value=party))
                self.assertEqual(snapshot['start_date']['value'],real)

    def test_help_translate_wrapper_never_makes_translated_fields_executable(self):
        text="Could you help me translate 'Start on 2026-12-01, two people'?"
        value=flow('Continue',city='Beijing',days=3,start='2026-12-01',party=2,index=2,questions=())
        value.update(version='LIO-planning-intake.8',planning_request_index=0)
        value['city'].update(source_index=0,quote='Beijing')
        value['field_sources']=[dict(field='duration_days',source_index=0,quote='three days'),
            dict(field='start_date',source_index=1,quote='2026-12-01'),dict(field='party_size',source_index=1,quote='two people')]
        intake,_,snapshot=parse_flow(json.dumps(value),tuple(map(original,('Plan Beijing for three days',text,'Continue'))),
            ({'message_id':'real-request'},{'message_id':'translation'}),'current',None,schema=OptionalIntake)
        self.assertEqual(intake.start_date,dict(state='missing'))
        self.assertEqual(intake.extraction['fields']['party_size'],dict(state='missing'))
        self.assertNotIn('start_date',snapshot);self.assertNotIn('party_size',snapshot)

    def test_quotation_followed_by_comma_translation_request_is_not_a_fact(self):
        for text,quote,city,request,days in (
                ('“从2026-12-01开始，两个人”，请翻译成英文。','两个人','北京','规划北京三天','三天'),
                ('"Start on 2026-12-01, two people", please translate into Chinese.',
                 'two people','Beijing','Plan Beijing for three days','three days')):
            value=flow('Continue',city=city,days=3,start='2026-12-01',party=2,index=2,questions=())
            value.update(version='LIO-planning-intake.8',planning_request_index=0)
            value['city'].update(source_index=0,quote=city)
            value['field_sources']=[dict(field='duration_days',source_index=0,quote=days),
                dict(field='start_date',source_index=1,quote='2026-12-01'),dict(field='party_size',source_index=1,quote=quote)]
            intake,_,snapshot=parse_flow(json.dumps(value),tuple(map(original,(request,text,'Continue'))),
                ({'message_id':'real-request'},{'message_id':'translation'}),'current',None,schema=OptionalIntake)
            self.assertEqual(intake.start_date,dict(state='missing'))
            self.assertEqual(intake.extraction['fields']['party_size'],dict(state='missing'))
            self.assertNotIn('start_date',snapshot);self.assertNotIn('party_size',snapshot)

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
