"""Typed original sources, not arbitrary empty placeholders or booking guesses."""
from copy import deepcopy
import json
import unittest
from jsonschema import Draft202012Validator,ValidationError
from cj_agent.lio_intake_facts_schema import response_format
from cj_api.lio_sourced_intake import parse_sourced
from cj_needs.domain import InvalidInput
from lio_flat_fixture import facts_fixture
import test_lio_intake_start_schema as previous


class SourcedIntake(unittest.TestCase):
    def sample(self,locale='zh',party=True):
        value,turns=previous.sample(locale,party)
        return facts_fixture(value),turns

    def test_bilingual_date_sources_and_meetup_do_not_claim_reservation(self):
        for locale in ('zh','en'):
            data,turns=self.sample(locale)
            Draft202012Validator(response_format(2)['json_schema']['schema']).validate(data)
            intake=parse_sourced(json.dumps(data),turns)
            self.assertEqual(intake.start_date['value'],'2026-11-13')
            self.assertEqual(intake.extraction['fields']['fixed_items'][0]['booking_status'],{'state':'missing'})
            self.assertTrue(previous.fixed_sources_complete(intake,previous.prepared(intake,turns),turns,previous.CITY))

    def test_arbitrary_empty_source_map_and_unlisted_fields_are_not_adapted(self):
        data,turns=self.sample()
        invalid=[{'budget':[]},[{'field':'interests','source_index':0,'quote':turns[0].text}],
                 [{'field':'start_date','source_index':1,'quote':''}]]
        for sources in invalid:
            bad=deepcopy(data);bad['field_sources']=sources
            with self.subTest(sources=sources):
                with self.assertRaises(ValidationError):Draft202012Validator(response_format(2)['json_schema']['schema']).validate(bad)
                with self.assertRaises(InvalidInput):parse_sourced(json.dumps(bad),turns)
        data['field_sources']=[]
        with self.assertRaises(InvalidInput):parse_sourced(json.dumps(data),turns)

    def test_bad_booking_string_or_unrelated_or_unstated_evidence_rejected(self):
        data,turns=self.sample()
        for evidence in ('booked',dict(status='booked',source_index=1,quote='已确定'),
                         dict(status='booked',source_index=0,quote='already booked')):
            bad=deepcopy(data);bad['fixed_items'][0]['booking_evidence']=evidence
            with self.subTest(evidence=evidence),self.assertRaises(InvalidInput):parse_sourced(json.dumps(bad),turns)

    def test_sources_still_bind_original_day_and_quote(self):
        data,turns=self.sample();data['start_date']='2026-11-14'
        with self.assertRaises(InvalidInput):parse_sourced(json.dumps(data),turns)

    def test_explicit_booking_keeps_status_only_with_its_own_original(self):
        for locale,confirmation in (('zh','已预约'),('en','already booked')):
            data,turns=self.sample(locale);item=data['fixed_items'][0];old=item['quote']
            statement=item['label']+' '+confirmation
            item['quote']=old+'; '+statement
            turns=(turns[0],type(turns[1])(text=turns[1].text.replace(old,item['quote'],1),question_day=turns[1].question_day),turns[2])
            item['booking_evidence']=dict(status='booked',source_index=1,quote=statement)
            intake=parse_sourced(json.dumps(data),turns)
            self.assertEqual(intake.extraction['fields']['fixed_items'][0]['booking_status'],{'state':'known','value':'booked'})
            self.assertTrue(previous.fixed_sources_complete(intake,previous.prepared(intake,turns),turns,previous.CITY))

    def test_cross_item_booking_and_switched_label_cannot_borrow_the_meetup_clock(self):
        for label in ('酒店甲集合','酒店乙'):
            data,turns=self.sample();item=data['fixed_items'][0];old=item['quote']
            item.update(label=label,quote=old.replace('酒店集合','酒店甲集合')+'；酒店乙已预订',detail_refs=[])
            turns=(turns[0],type(turns[1])(text=turns[1].text.replace(old,item['quote'],1),question_day=turns[1].question_day),turns[2])
            parse_sourced(json.dumps(data),turns)  # otherwise valid original DTO
            item['booking_evidence']=dict(status='booked',source_index=1,quote='酒店乙已预订')
            with self.subTest(label=label),self.assertRaises(InvalidInput):parse_sourced(json.dumps(data),turns)

    def test_original_context_negation_cannot_be_clipped_out_of_booking_proof(self):
        for suffix in ('这不代表已经预订','并非已预约','不是已预约','酒店集合并非已预约',
                       '不要声称酒店集合已预约','酒店集合可能已预约','酒店集合如果已预约','酒店集合已预约是假的'):
            for clipped in (False,True):
                data,turns=self.sample();item=data['fixed_items'][0];old=item['quote'];item['quote']=old+'；'+suffix
                turns=(turns[0],type(turns[1])(text=turns[1].text.replace(old,item['quote'],1),question_day=turns[1].question_day),turns[2])
                quote='已预约'if clipped and '已预约'in suffix else suffix
                item['booking_evidence']=dict(status='booked',source_index=1,quote=quote)
                with self.subTest(suffix=suffix,clipped=clipped),self.assertRaises(InvalidInput):parse_sourced(json.dumps(data),turns)
        data,turns=self.sample();data['field_sources'][0]['quote']='not an original source'
        with self.assertRaises(InvalidInput):parse_sourced(json.dumps(data),turns)

    def test_consultation_does_not_require_execution_booking_evidence(self):
        data,turns=self.sample();data['intent']='consult'
        data['fixed_items'][0]['booking_evidence']=dict(status='booked',source_index=1,quote='已确定')
        self.assertIsNone(parse_sourced(json.dumps(data),turns).extraction)
