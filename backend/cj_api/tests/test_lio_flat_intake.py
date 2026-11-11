"""New flat DTO is explicit; no repair of older malformed supplier results."""
from copy import deepcopy
import json
import unittest
from jsonschema import Draft202012Validator
from cj_agent.lio_intake_flat_schema import response_format,SCHEMA
from cj_api.lio_flat_intake import parse_flat
from cj_api.lio_national_intake import fields_for,fixed_sources_complete,FixedTimezoneConflict
from cj_needs.domain import InvalidInput
import test_lio_intake_start_schema as previous
from lio_flat_fixture import flat_fixture


class FlatIntake(unittest.TestCase):
    def sample(self,locale='zh',party=False):
        value,turns=previous.sample(locale,party)
        return flat_fixture(value),turns

    def test_simple_missing_facts_are_valid_nullable_values(self):
        value,turns=self.sample();value.update(start_date=None,party_size=None,fixed_items=[])
        value['field_sources']={'duration_days':value['field_sources']['duration_days']}
        result=parse_flat(json.dumps(value),turns)
        self.assertEqual(result.start_date,{'state':'missing'})
        self.assertEqual(result.extraction['fields']['party_size'],{'state':'missing'})

    def test_bilingual_date_fixed_and_person_preserve_checked_construction(self):
        for locale in ('zh','en'):
            for party in (False,True):
                with self.subTest(locale=locale,party=party):
                    value,turns=self.sample(locale,party);original=deepcopy(value)
                    Draft202012Validator(response_format(len(turns)-1)['json_schema']['schema']).validate(value)
                    intake=parse_flat(json.dumps(value),turns);fields=previous.prepared(intake,turns)
                    self.assertEqual(intake.start_date['value'],'2026-11-13')
                    self.assertEqual(fields['arrival']['date']['value'],'2026-11-13')
                    if party:self.assertTrue(fixed_sources_complete(intake,fields,turns,previous.CITY))
                    self.assertEqual(value,original)

    def test_missing_keys_wrong_types_and_older_version_are_not_adapted(self):
        value,turns=self.sample()
        for key in tuple(value):
            changed=deepcopy(value);changed.pop(key)
            with self.subTest(missing=key),self.assertRaises(InvalidInput):parse_flat(json.dumps(changed),turns)
        for change in ({'party_size':True},{'party_size':'1'},{'current_source_index':True},{'version':'LIO-planning-intake.4'}):
            with self.subTest(change=change),self.assertRaises(InvalidInput):parse_flat(json.dumps(dict(value,**change)),turns)
        old,turns=previous.sample()
        with self.assertRaises(InvalidInput):parse_flat(json.dumps(old),turns)

    def test_extra_fields_cannot_patch_canonical_or_private_fields(self):
        value,turns=self.sample()
        for name in ('start_date','party_size','fixed_items','field_sources','authority','destination_timezone','scope','unknown_slot'):
            changed=deepcopy(value);changed['extra_fields'][name]='override'
            with self.subTest(name=name),self.assertRaises(InvalidInput):parse_flat(json.dumps(changed),turns)
        changed=deepcopy(value);changed['extra_unknown_fields']=['pace']
        with self.assertRaises(InvalidInput):parse_flat(json.dumps(changed),turns)

    def test_explicit_unknown_uncertain_and_missing_are_distinct(self):
        value,turns=self.sample();value['start_date']=None;value['unknown_fields']=['start_date']
        self.assertEqual(parse_flat(json.dumps(value),turns).start_date,{'state':'unknown'})
        value['unknown_fields']=[];value['uncertain_fields']={'start_date':'还未确定'}
        self.assertEqual(parse_flat(json.dumps(value),turns).start_date,{'state':'uncertain','note':'还未确定'})
        value['start_date']='2026-11-13'
        with self.assertRaises(InvalidInput):parse_flat(json.dumps(value),turns)
        value,turns=self.sample(party=True);item=value['fixed_items'][0]
        item['unknown_fields']=['start_timezone']
        intake=parse_flat(json.dumps(value),turns)
        with self.assertRaises(FixedTimezoneConflict):previous.prepared(intake,turns)

    def test_nonexecution_does_not_consume_plan_requirements_or_add_authority(self):
        value,turns=self.sample();value['intent']='discuss'
        # Facts may be present, but do not enter NEEDS or publication.
        result=parse_flat(json.dumps(value),turns)
        self.assertEqual(result.intent,'discuss');self.assertIsNone(result.extraction)
        self.assertIsNone(result.start_date)

    def test_old_source_date_and_timezone_guards_are_reused(self):
        value,turns=self.sample();value['start_date']='2026-11-14'
        with self.assertRaises(InvalidInput):parse_flat(json.dumps(value),turns)
        value,turns=self.sample();value['field_sources']['start_date'][0]['source_index']=0
        with self.assertRaises(InvalidInput):parse_flat(json.dumps(value),turns)
        value,turns=self.sample();item=value['fixed_items'][0];old=item['quote'];item['quote']+=' CET'
        turns=(turns[0],type(turns[1])(text=turns[1].text.replace(old,item['quote'],1),question_day=turns[1].question_day))
        with self.assertRaises(FixedTimezoneConflict):previous.prepared(parse_flat(json.dumps(value),turns),turns)

    def test_vendor_schema_has_no_reference_conditional_or_union_combinators(self):
        def visit(value):
            if isinstance(value,dict):
                self.assertFalse({'$defs','$ref','anyOf','allOf','oneOf','if','then','else'}&value.keys())
                for item in value.values():visit(item)
            elif isinstance(value,list):
                for item in value:visit(item)
        visit(SCHEMA)
