"""W1-2 (#1722): an unverifiable traveler field is saved as unconfirmed, not a whole refusal."""
from datetime import date
import logging
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch,DEFAULT

from cj_api.lio_city import CityReference
from cj_api.lio_plan_understanding import (parse_plan_understanding,parse_plan_understanding_degraded,
    prepare_plan_fields,degraded_save_enabled)
from cj_api.lio_planning_grounding import PlanningTurn
from cj_api.local_lio_pipeline_inputs import PlanConstraints
from cj_message.lio_plan_input_schema import PLAN_UNDERSTANDING
from cj_needs.domain import InvalidInput
from cj_trip.domain import packed

BEIJING=CityReference('110100','北京市','北京市',None,'city','Asia/Shanghai')


def observation(field,value,quote,*,source_index=0,state='known',note=None):
    return dict(field=field,state=state,value=value,note=note,sources=[dict(source_index=source_index,quote=quote)])


def packet(*observations,fixed_items=(),companions=()):
    return dict(version=PLAN_UNDERSTANDING,current_source_index=1,observations=list(observations),
        companions=list(companions),fixed_items=list(fixed_items),temporary_conditions=[])


def turns(first):
    return (PlanningTurn(first,date(2026,11,14)),PlanningTurn('直接出方案',date(2026,11,16)))


def compiled(constraints):
    return constraints.compile(day_count=3,city_reference=BEIJING,message_id='m',run_id='r')


class DegradedUnderstanding(unittest.TestCase):
    def test_strictly_accepted_understanding_is_used_unchanged(self):
        value=packet(observation('start_date','2026-11-15','明天出发'),observation('party_size',2,'我们2人'))
        original=turns('明天出发，我们2人')
        strict=parse_plan_understanding(packed(value),original)
        degraded,unconfirmed=parse_plan_understanding_degraded(packed(value),original)
        self.assertEqual(degraded,strict)
        self.assertEqual(unconfirmed,frozenset())

    def test_a_wrong_value_is_dropped_never_kept(self):
        # The model claims 3 people; the traveler said 2. Strict refuses the whole plan.
        value=packet(observation('start_date','2026-11-15','明天出发'),observation('party_size',3,'我们2人'))
        original=turns('明天出发，我们2人')
        with self.assertRaises(InvalidInput):parse_plan_understanding(packed(value),original)
        degraded,unconfirmed=parse_plan_understanding_degraded(packed(value),original)
        self.assertEqual(unconfirmed,frozenset({'party_size'}))
        constraints=PlanConstraints(degraded,original,unconfirmed,True)
        fields=compiled(constraints).fields
        self.assertEqual(fields['party_size'],dict(state='missing'))
        self.assertEqual(fields['arrival']['date'],dict(state='known',value='2026-11-15'))

    def test_an_unsupported_first_day_option_becomes_unconfirmed(self):
        # The run -47 shape: the model filled in a first-day option the traveler never stated.
        value=packet(observation('first_day_full',True,'住在王府井附近'))
        original=turns('去北京玩三天，住在王府井附近')
        with self.assertRaises(InvalidInput):parse_plan_understanding(packed(value),original)
        degraded,unconfirmed=parse_plan_understanding_degraded(packed(value),original)
        self.assertEqual(unconfirmed,frozenset({'first_day_full'}))
        projection=PlanConstraints(degraded,original,unconfirmed,True).project()
        self.assertEqual(projection.edge_options['first_day_full'],dict(state='missing'))

    def test_an_omitted_latest_value_is_unconfirmed_and_never_restored_from_older_text(self):
        # The later message says three people; the model repeats the stale two.
        value=dict(packet(observation('party_size',2,'两个人')),current_source_index=2)
        original=(PlanningTurn('两个人',date(2026,11,14)),PlanningTurn('三个人',date(2026,11,15)),
                  PlanningTurn('直接出方案',date(2026,11,16)))
        with self.assertRaises(InvalidInput):parse_plan_understanding(packed(value),original)
        degraded,unconfirmed=parse_plan_understanding_degraded(packed(value),original)
        self.assertIn('party_size',unconfirmed)
        self.assertFalse(any(row.field=='party_size'for row in degraded.observations))

    def test_an_omitted_explicit_start_date_leaves_the_plan_undated(self):
        value=packet()
        original=turns('明天出发')
        with self.assertRaises(InvalidInput):prepare_plan_fields(parse_plan_understanding(packed(value),original),original)
        degraded,unconfirmed=parse_plan_understanding_degraded(packed(value),original)
        self.assertEqual(unconfirmed,frozenset({'start_date','arrival.date'}))
        constraints=PlanConstraints(degraded,original,unconfirmed,True)
        constraints.project()
        self.assertEqual(compiled(constraints).fields['arrival']['date']['state'],'missing')

    def test_budget_fields_are_dropped_together(self):
        value=packet(observation('budget_currency','USD','Budget USD 500 total'),
                     observation('budget_total','900','Budget USD 500 total'))
        original=turns('Budget USD 500 total')
        degraded,unconfirmed=parse_plan_understanding_degraded(packed(value),original)
        self.assertIn('budget_total',unconfirmed)
        self.assertIn('budget_currency',unconfirmed)
        self.assertFalse(any(row.field.startswith('budget_')for row in degraded.observations))

    def test_duplicate_observations_of_one_field_are_both_dropped(self):
        value=packet(observation('party_size',2,'我们2人'),observation('party_size',2,'我们2人'))
        original=turns('我们2人')
        degraded,unconfirmed=parse_plan_understanding_degraded(packed(value),original)
        self.assertEqual(unconfirmed,frozenset({'party_size'}))
        self.assertEqual(degraded.observations,[])

    def test_shape_binding_and_fixed_arrangements_stay_strict(self):
        original=turns('明天出发')
        with self.assertRaises(InvalidInput):parse_plan_understanding_degraded(b'{"version":"wrong"}',original)
        with self.assertRaises(InvalidInput):
            parse_plan_understanding_degraded(packed(dict(packet(),current_source_index=0)),original)
        fixed=dict(kind='appointment',label='演唱会',quote='没有这句话',source_index=0,applies_to=['self'],
            start_date=None,start_time=None,start_timezone=None,start_place=None,end_date=None,end_time=None,
            end_timezone=None,end_place=None,locked=None,booking_evidence=None,unknown_fields=[],uncertain_fields={},
            detail_refs=[])
        with self.assertRaises(InvalidInput):
            parse_plan_understanding_degraded(packed(packet(fixed_items=[fixed])),original)

    def test_an_event_clock_needing_timezone_clarification_is_unconfirmed(self):
        text='I arrive at 10:00 Asia/Tokyo'
        value=packet(observation('arrival.time','10:00',text))
        original=turns(text)
        strict=PlanConstraints(parse_plan_understanding(packed(value),original),original)
        with self.assertRaises(InvalidInput):compiled(strict)
        degraded,unconfirmed=parse_plan_understanding_degraded(packed(value),original)
        constraints=PlanConstraints(degraded,original,unconfirmed,True)
        self.assertEqual(constraints.compiled_unconfirmed(BEIJING),frozenset({'arrival.time'}))
        self.assertEqual(compiled(constraints).fields['arrival']['time']['state'],'missing')

    def test_degraded_data_keeps_only_strictly_checked_fields(self):
        # Degrading only removes fields; every remaining field passes the strict field check.
        from cj_api.lio_plan_understanding import _check_observation,_quote_check
        cases=((turns('明天出发，我们2人'),packet(observation('start_date','2026-11-16','明天出发'),
                    observation('party_size',2,'我们2人'),observation('pace','packed','我们2人'))),
               (turns('Budget USD 500 total, packed itinerary'),packet(observation('budget_total','500','Budget USD 500 total'),
                    observation('budget_currency','EUR','Budget USD 500 total'),observation('pace','packed','packed itinerary'))),
               (turns('I land at 09:30'),packet(observation('arrival.time','10:30','I land at 09:30'),
                    observation('departure.mode','train','I land at 09:30'))),
               (turns('去北京玩三天'),packet(observation('first_day_full',False,'不存在的引用'))))
        for original,value in cases:
            with self.subTest(text=original[0].text):
                with self.assertRaises(InvalidInput):
                    prepare_plan_fields(parse_plan_understanding(packed(value),original),original)
                degraded,unconfirmed=parse_plan_understanding_degraded(packed(value),original)
                self.assertTrue(unconfirmed)
                for row in degraded.observations:
                    self.assertNotIn(row.field,unconfirmed)
                    _check_observation(row,original,_quote_check(original))
                PlanConstraints(degraded,original,unconfirmed,True).project()

    def test_switch_is_off_by_default_and_accepts_only_zero_or_one(self):
        with patch.dict(os.environ,{},clear=False):
            os.environ.pop('CJ_LIO_PLAN_DEGRADED_SAVE',None)
            self.assertFalse(degraded_save_enabled())
        for flag,expected in (('0',False),('1',True)):
            with patch.dict(os.environ,{'CJ_LIO_PLAN_DEGRADED_SAVE':flag}):
                self.assertEqual(degraded_save_enabled(),expected)
        with patch.dict(os.environ,{'CJ_LIO_PLAN_DEGRADED_SAVE':'yes'}),self.assertRaises(InvalidInput):
            degraded_save_enabled()

    def test_understanding_uses_the_strict_parser_while_the_switch_is_off(self):
        import cj_api.local_lio_pipeline_inputs as inputs
        value=packet(observation('party_size',3,'我们2人'))
        original=turns('我们2人')
        host=SimpleNamespace(database=None,_model=lambda *args:packed(value))
        with patch.object(inputs,'original_plan_turns',return_value=original):
            for flag,refused in (('0',True),('1',False)):
                with self.subTest(flag=flag),patch.dict(os.environ,{'CJ_LIO_PLAN_DEGRADED_SAVE':flag}):
                    if refused:
                        with self.assertRaises(InvalidInput):inputs.understand_constraints(host,None,None,None,locale='zh')
                    else:
                        constraints=inputs.understand_constraints(host,None,None,None,locale='zh')
                        self.assertEqual(constraints.unconfirmed,frozenset({'party_size'}))
                        self.assertTrue(constraints.degraded)


class DegradedReply(unittest.TestCase):
    def plan(self,unconfirmed,locale):
        from cj_api.local_lio_pipeline_generation import PipelineGeneration
        import cj_api.local_lio_pipeline_generation as generation
        host=SimpleNamespace(current=lambda _:None,_finish=lambda worker,binding,state,body,scene,lang:body)
        worker=SimpleNamespace(runs=SimpleNamespace(snapshot=lambda _:object()),
            _event=lambda *args:self.fail('saved plan emitted a refusal event'))
        prepared=SimpleNamespace(projection=SimpleNamespace(fields={}),unconfirmed=unconfirmed)
        capture=SimpleNamespace(basis=SimpleNamespace(day_count=3,start_date=None))
        with patch.multiple(generation,prepare_generation=DEFAULT,retrieve_skeleton=DEFAULT,
                compile_retrieved_plan=DEFAULT,order_retrieved_plan=DEFAULT,route_ordered_plan=DEFAULT,
                schedule_retrieved_plan=DEFAULT,word_retrieved_plan=DEFAULT,publish_retrieved_plan=DEFAULT)as stages:
            stages['prepare_generation'].return_value=prepared
            stages['retrieve_skeleton'].return_value=({},(),capture)
            stages['order_retrieved_plan'].return_value=SimpleNamespace(content='{}',status='CONDITIONAL_SCHEDULE',reason='')
            stages['route_ordered_plan'].return_value=({},capture)
            stages['schedule_retrieved_plan'].return_value=SimpleNamespace(content='{}',status='CONDITIONAL_SCHEDULE',reason='')
            stages['word_retrieved_plan'].return_value=SimpleNamespace(summary='Summary.',unknown_transfers=(),
                edge_proximity_unconfirmed=())
            stages['publish_retrieved_plan'].return_value=(None,SimpleNamespace(proposal_id='p'))
            return PipelineGeneration().plan(host,worker,SimpleNamespace(run_id='run-1'),'view',locale=locale,
                effective={},prior_model_calls=1)

    def test_saved_reply_names_unconfirmed_fields_and_the_log_is_content_free(self):
        expected={'zh':'这些信息没能确认，先按未确认保存：出发日期、人数','en':'saved as unconfirmed: start date, party size'}
        for locale,text in expected.items():
            with self.subTest(locale=locale),self.assertLogs('cj_usage.audit',logging.INFO)as logs:
                body=self.plan(frozenset({'start_date','arrival.date','party_size'}),locale)
                self.assertIn('行程已保存'if locale=='zh'else'The itinerary is saved',body)
                self.assertIn(text,body)
                self.assertEqual(logs.output,['INFO:cj_usage.audit:LIO_PIPELINE_DEGRADED run_id=run-1 '
                                              'fields=arrival.date,party_size,start_date'])

    def test_a_save_with_nothing_unconfirmed_is_unchanged(self):
        for locale in ('zh','en'):
            body=self.plan(frozenset(),locale)
            self.assertNotIn('先按未确认保存'if locale=='zh'else'saved as unconfirmed',body)


if __name__=='__main__':
    unittest.main()
