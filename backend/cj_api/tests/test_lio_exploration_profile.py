"""Sourced exploration state, separate from save/default/Memory write authority."""
import json
from types import SimpleNamespace
import unittest

from cj_needs.domain import InvalidInput
from cj_api.lio_exploration_factors import FACTORS, BY_KEY, defaults
from cj_api.lio_exploration_profile import (Original, Source, MemorySource,
    parse_updates, memory_prefill, merge, snapshot, restore)


def packet(key, value, quote, *, state='known', index=0):
    return dict(factor_key=key, value=value, state=state,
                sources=[dict(source_index=index, quote=quote)])


def parse(updates, *texts):
    originals = tuple(Original('mid-'+str(i), i+1, text) for i,text in enumerate(texts))
    return parse_updates(json.dumps(dict(version='LIO-profile-update.1', updates=updates)), originals)


def memory(text, *, slot='travel.pace', source_id='manual-v2:real-id', version=1):
    return SimpleNamespace(payload=json.dumps(dict(version='MEMORY-RUN-CONSUME@2', items=[dict(
        subject='self', slot=slot, text=text, kind='preference', extent='long_term',
        source_id=source_id, source_version=1, version=version, context=None)])).encode())


class ExplorationProfileTests(unittest.TestCase):
    def test_catalogue_is_the_exact_fourteen_factors_with_bilingual_three_or_four_options(self):
        expected = {'city','duration_days','season','first_visit','party_type','interests',
                    'pace','lodging_tier','dietary','must_see','avoid','mobility','arrival','departure'}
        self.assertEqual(set(BY_KEY), expected)
        self.assertEqual(len(FACTORS), len(expected))
        for factor in FACTORS:
            self.assertEqual(len(factor.weights), 3)
            for locale in ('zh','en'):
                group = factor.question(locale)
                self.assertIn(len(group['options']), (3,4))
                self.assertEqual(len({o['id'] for o in group['options']}), len(group['options']))
                self.assertTrue(all(o['id'].startswith(factor.key+'.') for o in group['options']))
                self.assertTrue(all(o['display_text'] and o['send_text'] for o in group['options']))
                self.assertFalse(any(o['display_text'].casefold() in ('other','其他') for o in group['options']))
        self.assertEqual(BY_KEY['interests'].memory_slots, ('travel.interests',))
        self.assertEqual(BY_KEY['lodging_tier'].memory_slots, ('travel.budget','lodging.style'))
        self.assertTrue(BY_KEY['interests'].multiple)

    def test_bilingual_plain_text_corrections_replace_older_explicit_values(self):
        for first, later, quote1, quote2 in (
            ('喜欢紧凑节奏','节奏改为：轻松','紧凑','轻松'),
            ('I like a packed pace','Change my travel pace to relaxed','packed','relaxed')):
            original = parse([packet('pace','packed',quote1)], first)
            correction = parse([packet('pace','relaxed',quote2,index=1)], first,later)
            profile = merge(merge({},original), correction)
            self.assertEqual(profile['pace'].value, 'relaxed')
            self.assertEqual(profile['pace'].state, 'known')
            self.assertEqual(profile['pace'].sources[0].message_id, 'mid-1')
            self.assertEqual(profile['pace'].sources[0].quote, quote2)
            self.assertEqual(merge(profile,original), profile)

    def test_latest_source_order_is_used_not_model_array_order(self):
        updates = parse([packet('pace','relaxed','轻松'),packet('pace','packed','紧凑')], '先紧凑，后来改为轻松')
        self.assertEqual(merge({},updates)['pace'].value, 'relaxed')

    def test_refusals_are_not_needed_and_inference_cannot_override_them(self):
        for text in ('随便','都行','no preference','anything','prefer not to answer'):
            refused = parse([packet('pace',None,text,state='not_needed')], text)
            profile = merge({},refused)
            guessed = parse([packet('pace','relaxed','带孩子',state='inferred',index=1)], text,'带孩子')
            self.assertEqual(merge(profile,guessed)['pace'].state, 'not_needed')
            changed = parse([packet('pace','packed','packed',index=1)], text,'packed')
            self.assertEqual(merge(profile,changed)['pace'].value, 'packed')

    def test_inference_never_overrides_explicit_even_if_newer(self):
        profile = merge({},parse([packet('pace','packed','紧凑')], '紧凑'))
        guessed = parse([packet('pace','relaxed','带孩子',state='inferred',index=1)], '紧凑','带孩子')
        self.assertEqual(merge(profile,guessed), profile)
        unknown = merge({},guessed)
        self.assertEqual(unknown['pace'].state, 'inferred')

    def test_absent_empty_forged_and_negated_original_quotes_refuse(self):
        for item in (
            dict(packet('pace','packed','packed'),sources=[]),
            packet('pace','packed',''), packet('pace','packed','invented'),
            packet('pace','packed','packed',index=1),
            dict(packet('pace','packed','packed'),sources=[dict(message_id='fake',quote='packed')])):
            with self.subTest(item=item), self.assertRaises(InvalidInput):
                parse([item], 'not packed')
        with self.assertRaises(InvalidInput):
            parse([packet('pace','packed','packed')], 'not packed')
        with self.assertRaises(InvalidInput):
            parse([packet('pace',None,'随便',state='not_needed')], '不是随便')

    def test_quote_does_not_allow_different_known_value(self):
        for key,value,quote in (('pace','packed','轻松'),('duration_days',4,'三天'),
                                ('city','上海','北京'),('first_visit',False,'第一次')):
            with self.subTest(key=key),self.assertRaises(InvalidInput):
                parse([packet(key,value,quote)],quote)

    def test_duration_first_visit_and_multiselect_values_are_grounded(self):
        for quote,value in (('三天',3),('4 days',4),('five days',5),('366天',366)):
            self.assertEqual(parse([packet('duration_days',value,quote)],quote)[0].value,value)
        for quote,value in (('第一次',True),('first visit',True),('来过中国',False),('returning to China',False)):
            self.assertEqual(parse([packet('first_visit',value,quote)],quote)[0].value,value)
        row=parse([packet('interests',['history','food'],'历史和美食')],'历史和美食')[0]
        self.assertEqual(row.value,('history','food'))
        self.assertEqual(parse([packet('dietary',['mild'],'不吃辣')],'不吃辣')[0].value,('mild',))

    def test_inference_is_only_allowed_for_configured_factors_and_bounded_values(self):
        for key,value in (('arrival','morning'),('city','beijing'),('pace','dangerous'),('interests',['food','food'])):
            with self.subTest(key=key),self.assertRaises(InvalidInput):
                parse([packet(key,value,'带孩子',state='inferred')],'带孩子')

    def test_model_cannot_label_itself_default_or_memory_or_add_unapproved_factors(self):
        for state in ('default','memory','unknown'):
            with self.subTest(state=state),self.assertRaises(InvalidInput):
                parse([packet('pace','relaxed','轻松',state=state)],'轻松')
        for key in ('nationality','age','budget_amount'):
            with self.subTest(key=key),self.assertRaises(InvalidInput):
                parse([packet(key,'literal','literal')],'literal')

    def test_actual_saved_memory_keeps_real_source_id_without_fabricating_mid(self):
        rows = memory_prefill(memory('I prefer a slow travel pace.'))
        self.assertEqual(rows[0].state, 'memory')
        self.assertEqual(rows[0].value, 'relaxed')
        self.assertIsInstance(rows[0].sources[0], MemorySource)
        source = snapshot(merge({},(),rows))['factors'][0]['sources'][0]
        self.assertEqual(source['source_id'],'manual-v2:real-id')
        self.assertNotIn('message_id',source)
        self.assertNotIn('quote',source)

    def test_memory_is_rebuilt_each_turn_and_explicit_value_or_refusal_wins(self):
        saved = memory_prefill(memory('I prefer slow travel.'))
        previous = merge({},(),saved)
        self.assertEqual(merge(previous,()), {})  # deleted/disabled/missing from the fresh admitted selection
        changed = memory_prefill(memory('I prefer packed travel.',version=2))
        self.assertEqual(merge(previous,(),changed)['pace'].value,'packed')
        explicit = merge(previous,parse([packet('pace','moderate','moderate')],'moderate'),saved)
        self.assertEqual(merge(explicit,(),changed)['pace'].value,'moderate')
        refused=merge({},parse([packet('pace',None,'都行',state='not_needed')],'都行'))
        self.assertEqual(merge(refused,(),saved)['pace'].state,'not_needed')

    def test_memory_projection_respects_actual_subject_and_slot_selection(self):
        run = memory('packed')
        data=json.loads(run.payload);data['items'][0]['subject']='companion:friend'
        run.payload=json.dumps(data).encode()
        self.assertEqual(memory_prefill(run),())
        self.assertEqual(memory_prefill(memory('packed',slot='unselected.slot')),())

    def test_overlapping_memory_slots_retain_both_sources_without_guessing_the_winner(self):
        run=memory('I prefer luxury hotels.',slot='travel.budget')
        data=json.loads(run.payload)
        data['items'].append(dict(data['items'][0],slot='lodging.style',text='I prefer simple stays.',source_id='manual-v2:second',version=3))
        run.payload=json.dumps(data).encode()
        fact=memory_prefill(run)[0]
        self.assertEqual(len(fact.sources),2)
        self.assertEqual(fact.value,('I prefer luxury hotels.','I prefer simple stays.'))

    def test_defaults_are_proposals_and_never_create_precise_dates_or_user_sources(self):
        values=defaults({})
        self.assertEqual(values['city'],'北京');self.assertEqual(values['duration_days'],3)
        self.assertEqual(values['party_type'],'two_adults');self.assertEqual(values['pace'],'moderate')
        self.assertIsNone(values['arrival']);self.assertIsNone(values['departure'])
        for word,key,city in (('history','history','北京'),('food','food','成都'),('modern city','modern','上海'),('nature','nature','杭州')):
            profile=merge({},parse([packet('interests',[key],word)],word))
            self.assertEqual(defaults(profile)['city'],city)
        self.assertFalse(any(isinstance(value,Source) for value in values.values()))

    def test_persisted_context_rebinds_originals_and_refuses_tampering(self):
        original=Original('mid-0',1,'节奏改为轻松')
        profile=merge({},parse([packet('pace','relaxed','轻松')],original.text))
        saved=snapshot(profile)
        self.assertEqual(restore(json.dumps(saved),(original,)),profile)
        for change in ('mid','sequence','quote','offset','state','value','duplicate'):
            raw=json.loads(json.dumps(saved));fact=raw['factors'][0];source=fact['sources'][0]
            if change=='mid':source['message_id']='foreign-mid'
            elif change=='sequence':source['sequence']=2
            elif change=='quote':source['quote']='紧凑'
            elif change=='offset':source['offset']=0
            elif change=='state':fact['state']='memory'
            elif change=='value':fact['value']='packed'
            else:raw['factors'].append(fact.copy())
            with self.subTest(change=change),self.assertRaises(InvalidInput):
                restore(json.dumps(raw),(original,))
        with self.assertRaises(InvalidInput):
            restore(json.dumps(saved),())

    def test_persisted_memory_is_never_reused_after_deletion_or_replacement(self):
        saved=snapshot(merge({},(),memory_prefill(memory('I prefer slow travel.'))))
        self.assertEqual(restore(json.dumps(saved),()),{})
        fresh=restore(json.dumps(saved),(),memory('I prefer packed travel.',version=2))
        self.assertEqual(fresh['pace'].value,'packed')
        self.assertEqual(fresh['pace'].sources[0].version,2)


if __name__ == '__main__':
    unittest.main()
