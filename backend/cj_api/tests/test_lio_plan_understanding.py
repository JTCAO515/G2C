"""Plan data does not become permission, and dates retain their original day."""
from copy import deepcopy
from datetime import date
import unittest

from cj_api.lio_plan_understanding import parse_plan_understanding,project_plan_fields,compile_plan_fields,prepare_plan_fields
from cj_api.lio_city import CityReference
from cj_api.lio_planning_grounding import PlanningTurn
from cj_message.lio_plan_input_schema import PLAN_UNDERSTANDING
from cj_needs.domain import InvalidInput
from cj_trip.domain import packed


class PlanUnderstandingBoundary(unittest.TestCase):
    def compile(self,value,turns):
        return compile_plan_fields(parse_plan_understanding(packed(value),turns),turns,day_count=3,
            city_reference=CityReference('110100','北京市','北京市',None,'city','Asia/Shanghai'),
            message_id='actual-plan-trigger',run_id='actual-plan-run')

    def packet(self):
        return dict(version=PLAN_UNDERSTANDING,current_source_index=1,observations=[dict(field='start_date',
            state='known',value='2026-11-15',note=None,sources=[dict(source_index=0,quote='明天出发')])],
            companions=[],fixed_items=[],temporary_conditions=[])

    def turns(self):
        return (PlanningTurn('明天出发',date(2026,11,14)),PlanningTurn('直接出方案',date(2026,11,16)))

    def test_known_constraints_need_their_specific_original_value_not_just_an_existing_quote(self):
        cases=[('Hello','pace','relaxed',False),
            ('I want a packed itinerary','pace','relaxed',False),
            ('I want a packed itinerary','pace','packed',True),
            ('我喜欢轻松行程','pace','relaxed',True),
            ('My friend prefers relaxed travel','pace','relaxed',False),
            ('Hello','budget_currency','CNY',False),
            ('My budget is in USD','budget_currency','CNY',False),
            ('My budget is in USD','budget_currency','USD',True),
            ('My budget is 500','budget_total','1000',False),
            ('Budget USD 500 total','budget_total','500',True),
            ('预算 CNY 500 总计','budget_total','500',True),
            ('Budget USD 500 per person','budget_total','500',False),
            ('Budget USD 500 per person','budget_per_person','500',True),
            ('Paid CNY 200','budget_paid','100',False),
            ('Paid CNY 200','budget_paid','200',True),
            ('Budget USD 500 per person','budget_basis','total',False),
            ('Budget USD 500 per person','budget_basis','per_person',True),
            ('Budget USD 500 PER PERSON','budget_basis','total',False),
            ('Budget USD 500 PER PERSON','budget_basis','per_person',True),
            ('Budget USD 500 total','budget_total','not-an-amount',False),
            ('Hello','budget_includes',['hotels'],False),
            ('Budget includes hotels and trains','budget_includes',['flights'],False),
            ('Budget includes hotels and trains','budget_includes',['hotels','trains'],True),
            ('My friend has a budget of USD 500 total','budget_total','500',False),
            ('Hello','overseas_timezone','Asia/Tokyo',False),
            ('Asia/Tokyo','overseas_timezone','Asia/Shanghai',False),
            ('Asia/Tokyo','overseas_timezone','Asia/Tokyo',True)]
        for text,field,amount,accepted in cases:
            value=self.packet();value['observations']=[dict(field=field,state='known',value=amount,note=None,
                sources=[dict(source_index=0,quote=text)])]
            turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
            with self.subTest(text=text,field=field,value=amount):
                if accepted:
                    actual=self.compile(value,turns)
                    self.assertEqual(actual.fields[field],dict(state='known',value=amount))
                else:
                    with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_budget_quote_itself_covers_the_observed_value_within_its_own_clause(self):
        for text,field,amount,quote,accepted in (
                ('Budget USD 500 total','budget_total','500','USD',False),
                ('Budget USD 500 total','budget_total','500','500',True),
                ('Budget USD 500 total','budget_currency','USD','500',False),
                ('Budget USD 500 total','budget_currency','USD','USD',True),
                ('Budget USD 500 total','budget_basis','total','Budget',False),
                ('Budget USD 500 total','budget_basis','total','total',True),
                ('Budget includes hotels and trains','budget_includes',['hotels','trains'],'Budget',False),
                ('Budget includes hotels and trains','budget_includes',['hotels','trains'],'hotels and trains',True),
                ('Budget includes hotels','budget_includes',['hotels'],'Budget',False),
                ('Budget includes hotels','budget_includes',['hotels'],'hotels',True)):
            value=self.packet()
            value['observations']=[dict(field=field,state='known',value=amount,note=None,
                sources=[dict(source_index=0,quote=quote)])]
            turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
            with self.subTest(field=field,quote=quote):
                if accepted:self.compile(value,turns)
                else:
                    with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_friend_endpoint_does_not_replace_the_travelers_own_endpoint_in_the_same_message(self):
        cases=[('My friend Alice leaves from Beijing Capital Airport; I leave from Shanghai Hongqiao Airport.',
            'departure.place','Beijing Capital Airport',False),
            ('My friend Alice leaves from Beijing Capital Airport; I leave from Shanghai Hongqiao Airport.',
            'departure.place','Shanghai Hongqiao Airport',True),
            ('My friend Alice arrives at Beijing Capital Airport; I arrive at Beijing Daxing Airport.',
            'arrival.place','Beijing Capital Airport',False),
            ('My friend Alice arrives at Beijing Capital Airport; I arrive at Beijing Daxing Airport.',
            'arrival.place','Beijing Daxing Airport',True),
            ('朋友小王从北京首都机场出发；我从北京大兴机场出发。','departure.place','北京首都机场',False),
            ('朋友小王从北京首都机场出发；我从北京大兴机场出发。','departure.place','北京大兴机场',True),
            ('Beijing Capital Airport','arrival.place','Beijing Capital Airport',True)]
        for text,field,place,accepted in cases:
            value=self.packet();value['observations']=[dict(field=field,state='known',value=place,note=None,
                sources=[dict(source_index=0,quote=place)])]
            turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
            with self.subTest(text=text,field=field,place=place):
                if accepted:self.compile(value,turns)
                else:
                    with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_friend_event_date_is_not_the_travelers_start_or_departure_date(self):
        text='My friend Alice leaves on 2026-12-01; I leave on 2026-12-03.'
        turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
        for field in ('start_date','departure.date'):
            for quoted,accepted in (('2026-12-01',False),('2026-12-03',True)):
                value=self.packet();value['observations']=[dict(field=field,state='known',value=quoted,note=None,
                    sources=[dict(source_index=0,quote=quoted)])]
                with self.subTest(field=field,quote=quoted):
                    if accepted:self.compile(value,turns)
                    else:
                        with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_latest_explicit_party_count_cannot_be_omitted_or_restored_from_an_older_source(self):
        for texts,old_index,new_index,old_quote,new_quote in (
                (('Two people','Three people','Plan now'),0,1,'Two people','Three people'),
                (('两个人','三个人','直接出方案'),0,1,'两个人','三个人'),
                (('Two people; Three people.','Plan now'),0,0,'Two people','Three people'),
                (('两个人；三个人。','直接出方案'),0,0,'两个人','三个人')):
            turns=tuple(PlanningTurn(text,date(2026,11,14+i))for i,text in enumerate(texts))
            for count,index,quote,accepted in ((2,old_index,old_quote,False),(3,new_index,new_quote,True),
                                               (None,0,'',False)):
                value=self.packet();value['current_source_index']=len(turns)-1
                value['observations']=[]if count is None else[dict(field='party_size',state='known',value=count,note=None,
                    sources=[dict(source_index=index,quote=quote)])]
                with self.subTest(texts=texts,count=count):
                    if accepted:self.compile(value,turns)
                    else:
                        with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_party_questions_conditions_translation_and_third_party_do_not_replace_a_real_count(self):
        for followup in ('Three people?', 'If three people come', 'Translate "Three people"',
                         'My friend travels with three people', '三个人吗？','如果三个人去','请翻译“三个人”',
                         'If three people come, do not save','Not two people? Do not save',
                         'Translate "Three people, do not save"','My friend travels with three people, do not save'):
            turns=(PlanningTurn('Two people',date(2026,11,14)),PlanningTurn(followup,date(2026,11,15)),
                   PlanningTurn('Plan now',date(2026,11,16)))
            value=self.packet();value['current_source_index']=2;value['observations']=[dict(field='party_size',
                state='known',value=2,note=None,sources=[dict(source_index=0,quote='Two people')])]
            with self.subTest(followup=followup):self.compile(value,turns)

    def test_same_message_party_a_b_a_uses_the_last_count_not_the_unique_middle_clause(self):
        text='Two people; Three people; Two people.'
        turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
        for count,quote,accepted in ((3,'Three people',False),(2,'Two people.',True)):
            value=self.packet();value['observations']=[dict(field='party_size',state='known',value=count,note=None,
                sources=[dict(source_index=0,quote=quote)])]
            with self.subTest(count=count):
                if accepted:self.compile(value,turns)
                else:
                    with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_denied_current_party_stays_unknown_instead_of_restoring_the_old_count(self):
        for denial in ('Not two people anymore','We are no longer two people','不是两个人','不再是两个人'):
            turns=(PlanningTurn('Two people',date(2026,11,14)),PlanningTurn(denial,date(2026,11,15)),
                   PlanningTurn('Plan now',date(2026,11,16)))
            for state,number,index,quote,accepted in (('known',2,0,'Two people',False),
                                                     ('unknown',None,1,denial,True)):
                value=self.packet();value['current_source_index']=2;value['observations']=[dict(field='party_size',
                    state=state,value=number,note=None,sources=[dict(source_index=index,quote=quote)])]
                with self.subTest(denial=denial,state=state):
                    if accepted:self.compile(value,turns)
                    else:
                        with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_unquoted_multiline_translation_never_replaces_real_date_and_party_context(self):
        turns=(PlanningTurn('Two people; Start my trip tomorrow',date(2026,11,14)),
               PlanningTurn('Translate the following:\nThree people; Start my trip on 2026-12-01',date(2026,11,15)),
               PlanningTurn('Plan now',date(2026,11,16)))
        value=self.packet();value['current_source_index']=2
        value['observations']=[dict(field='party_size',state='known',value=2,note=None,
            sources=[dict(source_index=0,quote='Two people')]),dict(field='start_date',state='known',
            value='2026-11-15',note=None,sources=[dict(source_index=0,quote='Start my trip tomorrow')])]
        self.compile(value,turns)
        value['observations'][0].update(value=3,sources=[dict(source_index=1,quote='Three people')])
        with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_write_refusal_does_not_erase_an_independent_current_party_statement(self):
        for update,count,state,quote in (
                ('Three people, do not save',3,'known','Three people'),
                ('三个人，不要保存',3,'known','三个人'),
                ('Party size undecided, do not save',None,'unknown','Party size undecided'),
                ('人数未定，不要保存',None,'unknown','人数未定')):
            turns=(PlanningTurn('Two people',date(2026,11,14)),PlanningTurn(update,date(2026,11,15)),
                   PlanningTurn('Plan now',date(2026,11,16)))
            for number,label,index,reference,accepted in ((2,'known',0,'Two people',False),
                    (count,state,1,quote,True),(count,state,1,update,True)):
                value=self.packet();value['current_source_index']=2;value['observations']=[dict(field='party_size',
                    state=label,value=number,note=None,sources=[dict(source_index=index,quote=reference)])]
                with self.subTest(update=update,value=number,quote=reference):
                    if accepted:self.compile(value,turns)
                    else:
                        with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_explicitly_undecided_party_is_not_replaced_by_its_old_known_count(self):
        for reset in ('Party size undecided','人数未定'):
            turns=(PlanningTurn('Two people',date(2026,11,14)),PlanningTurn(reset,date(2026,11,15)),
                   PlanningTurn('Plan now',date(2026,11,16)))
            for count,index,quote,state,accepted in ((2,0,'Two people','known',False),(None,1,reset,'unknown',True)):
                value=self.packet();value['current_source_index']=2;value['observations']=[dict(field='party_size',
                    state=state,value=count,note=None,sources=[dict(source_index=index,quote=quote)])]
                with self.subTest(reset=reset,state=state):
                    if accepted:self.compile(value,turns)
                    else:
                        with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_date_uses_its_source_mid_day_not_plan_trigger_day(self):
        result=parse_plan_understanding(packed(self.packet()),self.turns())
        self.assertEqual(result.observations[0].value,'2026-11-15')
        value=self.packet();value['observations'][0]['value']='2026-11-17'
        with self.assertRaises(InvalidInput):parse_plan_understanding(packed(value),self.turns())

    def test_memory_text_invented_sources_and_duplicate_observations_refuse(self):
        for mutate in (lambda v:v['observations'][0]['sources'][0].update(quote='Stored memory prefers tomorrow'),
                       lambda v:v['observations'][0]['sources'][0].update(source_index=2),
                       lambda v:v['observations'].append(deepcopy(v['observations'][0])),
                       lambda v:v.update(current_source_index=0)):
            value=self.packet();mutate(value)
            with self.assertRaises(InvalidInput):parse_plan_understanding(packed(value),self.turns())

    def test_empty_fixed_data_is_not_a_fabricated_source_capability(self):
        value=self.packet();value['observations']=[]
        result=parse_plan_understanding(packed(value),self.turns())
        self.assertEqual(result.fixed_items,[])
        self.assertNotIn('permission',result.model_dump())
        for key in ('source','permission','save'):
            value=self.packet();value[key]=True
            with self.assertRaises(InvalidInput):parse_plan_understanding(packed(value),self.turns())

    def fixed_case(self):
        quote='第一天我9:00–10:00要在酒店集合，这项安排已确定，保持不变'
        turns=(PlanningTurn(quote,date(2026,11,14)),PlanningTurn('直接出方案',date(2026,11,16)))
        value=self.packet();value['observations']=[]
        fixed=dict(label='酒店集合',source_index=0,quote=quote,detail_refs=[],kind='appointment',
            applies_to=['self'],locked=True,booking_evidence=None,
            start_date=None,start_time='09:00',start_timezone=None,start_place=None,
            end_date=None,end_time='10:00',end_timezone=None,end_place=None,
            unknown_fields=[],uncertain_fields={})
        value['fixed_items']=[fixed]
        return value,turns

    def test_projection_preserves_full_fixed_rows_without_dates_people_or_booking_defaults(self):
        value,turns=self.fixed_case()
        projection=project_plan_fields(parse_plan_understanding(packed(value),turns))
        item,=projection.fields['fixed_items']
        self.assertEqual(item['description'],value['fixed_items'][0]['quote'])
        self.assertEqual(item['applies_to'],['self'])
        self.assertEqual(item['locked'],dict(state='known',value=True))
        self.assertEqual(item['start']['time'],dict(state='known',value='09:00'))
        self.assertEqual(item['end']['time'],dict(state='known',value='10:00'))
        for key in ('date','timezone','place'):
            self.assertEqual(item['start'][key],dict(state='missing'))
            self.assertEqual(item['end'][key],dict(state='missing'))
        self.assertEqual(item['booking_status'],dict(state='missing'))
        self.assertEqual(projection.fields['party_size'],dict(state='missing'))
        self.assertEqual(projection.start_date,dict(state='missing'))

    def test_fixed_unknown_participants_reservation_claims_and_duplicate_rows_refuse(self):
        original,turns=self.fixed_case()
        for mutate in (lambda v:v['fixed_items'][0].update(applies_to=['companion:forged']),
                       lambda v:v['fixed_items'][0].update(applies_to=['self','self']),
                       lambda v:v['fixed_items'].append(deepcopy(v['fixed_items'][0])),
                       lambda v:v['fixed_items'][0].update(booking_evidence=dict(status='booked',source_index=0,quote='保持不变'))):
            value=deepcopy(original);mutate(value)
            with self.assertRaises(InvalidInput):parse_plan_understanding(packed(value),turns)

    def test_compiler_preserves_undated_fixed_window_and_unknown_booking(self):
        value,turns=self.fixed_case()
        compiled=self.compile(value,turns)
        item,=compiled.fields['fixed_items']
        self.assertEqual(item['start']['time'],dict(state='known',value='09:00'))
        self.assertEqual(item['end']['time'],dict(state='known',value='10:00'))
        self.assertEqual(item['start']['date'],dict(state='missing'))
        self.assertEqual(item['booking_status'],dict(state='missing'))
        self.assertEqual(compiled.fields['party_size'],dict(state='missing'))

    def test_city_free_preflight_preserves_final_item_ids_without_timezone_or_booking_defaults(self):
        value,turns=self.fixed_case()
        result=prepare_plan_fields(parse_plan_understanding(packed(value),turns),turns)
        final=self.compile(value,turns)
        self.assertEqual(result.fields['fixed_items'][0]['item_id'],final.fields['fixed_items'][0]['item_id'])
        self.assertEqual(result.fields['fixed_items'][0]['start']['timezone'],dict(state='missing'))
        self.assertEqual(result.fields['fixed_items'][0]['booking_status'],dict(state='missing'))
        self.assertNotIn('destination_timezone',result.fields)
        self.assertEqual(result.start_date,dict(state='missing'))

    def test_city_free_preflight_rejects_omitted_original_dates_and_fixed_declarations(self):
        value=self.packet();value['observations']=[]
        checked=parse_plan_understanding(packed(value),self.turns())
        with self.assertRaisesRegex(InvalidInput,'original trip date was omitted'):
            prepare_plan_fields(checked,self.turns())
        value,turns=self.fixed_case();value['fixed_items']=[]
        checked=parse_plan_understanding(packed(value),turns)
        with self.assertRaisesRegex(InvalidInput,'fixed declarations required before lookup'):
            prepare_plan_fields(checked,turns)

    def test_endpoint_place_queries_cannot_use_model_translations_wrong_roles_or_nonfacts(self):
        cases=[('我将抵达北京首都机场','北京首都机场','北京首都机场',True),
               ('I arrive at Beijing Capital Airport','Beijing Capital Airport','Beijing Capital Airport',True),
               ('北京首都机场','北京首都机场','北京首都机场',True),
               ('我将抵达北京首都机场','北京首都机场','北京大兴机场',False),
               ('我不会抵达北京首都机场','北京首都机场','北京首都机场',False),
               ('我会抵达北京首都机场吗？','北京首都机场','北京首都机场',False),
               ('请翻译“我将抵达北京首都机场”','北京首都机场','北京首都机场',False),
               ('I depart from Beijing Capital Airport','Beijing Capital Airport','Beijing Capital Airport',False)]
        for text,quote,name,accepted in cases:
            turns=(PlanningTurn(text,date(2026,11,14)),PlanningTurn('Plan now',date(2026,11,16)))
            value=self.packet();value['observations']=[dict(field='arrival.place',state='known',value=name,note=None,
                sources=[dict(source_index=0,quote=quote)])]
            with self.subTest(text=text,name=name):
                if accepted:
                    checked=parse_plan_understanding(packed(value),turns)
                    self.assertEqual(project_plan_fields(checked).fields['arrival']['place']['value'],name)
                else:
                    with self.assertRaises(InvalidInput):parse_plan_understanding(packed(value),turns)

    def test_missing_fixed_arrangements_or_invented_fixed_clock_cannot_compile(self):
        original,turns=self.fixed_case()
        for mutate in (lambda v:v.update(fixed_items=[]),
                       lambda v:v['fixed_items'][0].update(start_time='08:00'),
                       lambda v:v['fixed_items'][0].update(applies_to=['party'])):
            value=deepcopy(original);mutate(value)
            with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_stated_start_uses_original_day_and_derives_calendar_without_people_default(self):
        compiled=self.compile(self.packet(),self.turns())
        self.assertEqual(compiled.fields['arrival']['date'],dict(state='known',value='2026-11-15'))
        self.assertEqual(compiled.fields['departure']['date'],dict(state='known',value='2026-11-17'))
        self.assertEqual(compiled.fields['party_size'],dict(state='missing'))

    def test_fixed_day_maps_only_from_a_stated_start_and_preserves_original_clocks(self):
        value,turns=self.fixed_case()
        turns=(PlanningTurn('明天出发。'+turns[0].text,date(2026,11,14)),turns[1])
        value['observations']=self.packet()['observations']
        compiled=self.compile(value,turns)
        item,=compiled.fields['fixed_items']
        self.assertEqual(item['start']['date'],dict(state='known',value='2026-11-15'))
        self.assertEqual(item['end']['date'],dict(state='known',value='2026-11-15'))
        self.assertEqual(item['start']['time'],dict(state='known',value='09:00'))
        self.assertEqual(item['end']['time'],dict(state='known',value='10:00'))
        self.assertEqual(item['booking_status'],dict(state='missing'))

    def test_only_the_fixed_items_original_location_can_seed_a_place_query(self):
        from cj_api.lio_pipeline_document import declared_endpoint_names
        for language, place, label, fixed_text, confirmed, denied, unrelated in (
            ('zh','北京饭店','酒店集合','第一天我9:00–10:00要在酒店集合，这项安排已确定，保持不变',
             '酒店集合地点是北京饭店','酒店集合地点不是北京饭店',(
                 '请补全第二天安排','另外想看看北京饭店','酒店集合照旧而我朋友住在北京饭店',
                 '酒店集合照旧并且我晚上去北京饭店吃饭','酒店集合地点是北京饭店咖啡厅',
             )),
            ('en','Beijing Hotel','hotel meetup','On day 1 I have a fixed hotel meetup from 9:00 to 10:00 a.m., keep it unchanged',
             'The hotel meetup is at Beijing Hotel','The hotel meetup is not at Beijing Hotel',(
                 'Please fill out day two','Also show me the Beijing Hotel',
                 'The hotel meetup stays as planned while my friend stays at Beijing Hotel',
                 'The hotel meetup stays as planned while I eat at Beijing Hotel tonight',
                 'The hotel meetup is at Beijing Hotel West Gate',
             )),
        ):
            for detail in (*unrelated,confirmed,denied):
                expected=detail==confirmed
                with self.subTest(language=language,detail=detail):
                    value,turns=self.fixed_case()
                    turns=(PlanningTurn(fixed_text,turns[0].question_day),
                           PlanningTurn(detail,turns[0].question_day),turns[1])
                    value['current_source_index']=2
                    value['fixed_items'][0].update(label=label,quote=fixed_text,start_place=place,end_place=place,
                        detail_refs=[dict(source_index=1,quote=detail)])
                    parsed=parse_plan_understanding(packed(value),turns)
                    projection=prepare_plan_fields(parsed,turns)
                    endpoints=declared_endpoint_names(projection.fields,id_prefix='scope',retained=None,city_names=())
                    self.assertEqual(bool(endpoints),expected)
                    # Keep the separate final fixed guard for details that
                    # contain a denial or a different participant.
                    fields=self.compile(value,turns).fields if detail in (confirmed,*unrelated[:2]) else projection.fields
                    item,=fields['fixed_items']
                    for edge, clock in (('start','09:00'),('end','10:00')):
                        self.assertEqual(item[edge]['place'],dict(state='known',value=place)if expected else dict(state='unknown'))
                        self.assertEqual(item[edge]['time'],dict(state='known',value=clock))
                    self.assertEqual(item['locked'],dict(state='known',value=True))

    def test_fixed_location_uses_the_latest_original_even_when_model_cites_the_old_place(self):
        from cj_api.lio_pipeline_document import declared_endpoint_names
        for label, place, new_place, prior, same_turn, change, denial, restated, other_activity in (
            ('酒店集合','北京饭店','北京南站',
             '第一天我9:00–10:00要在北京饭店进行酒店集合，这项安排已确定，保持不变',
             '第一天我9:00–10:00在北京饭店的酒店集合改在北京南站，这项安排已确定，保持不变',
             '酒店集合改在北京南站','酒店集合不在北京饭店','酒店集合地点在北京南站','我朋友换到北京饭店住宿'),
            ('hotel meetup','Beijing Hotel','Beijing South Station',
             'On day 1 I have a fixed hotel meetup at Beijing Hotel from 9:00 to 10:00 a.m., keep it unchanged',
             'On day 1 I have a fixed hotel meetup at Beijing Hotel from 9:00 to 10:00 moved to Beijing South Station, keep it unchanged',
             'The hotel meetup moved to Beijing South Station','The hotel meetup is not at Beijing Hotel',
             'The hotel meetup is at Beijing South Station','My friend moved to Beijing Hotel'),
        ):
            for primary, later, selected_place, is_current in (
                (same_turn,None,place,False),(prior,change,place,False),(prior,denial,place,False),
                (prior,restated,place,False),(prior,change,new_place,True),(prior,other_activity,place,True),
            ):
                with self.subTest(primary=primary,later=later,selected_place=selected_place):
                    value,turns=self.fixed_case()
                    day=turns[0].question_day
                    turns=(PlanningTurn(primary,day),*((PlanningTurn(later,day),)if later else ()),turns[1])
                    value['current_source_index']=len(turns)-1
                    details=[dict(source_index=1,quote=later)]if selected_place==new_place else []
                    value['fixed_items'][0].update(label=label,quote=primary,start_place=selected_place,
                        end_place=selected_place,detail_refs=details)
                    data=prepare_plan_fields(parse_plan_understanding(packed(value),turns),turns)
                    endpoints=declared_endpoint_names(data.fields,id_prefix='scope',retained=None,city_names=())
                    self.assertEqual(bool(endpoints),is_current)
                    fixed,=data.fields['fixed_items']
                    for edge,clock in (('start','09:00'),('end','10:00')):
                        expected=dict(state='known',value=selected_place)if is_current else dict(state='unknown')
                        self.assertEqual(fixed[edge]['place'],expected)
                        self.assertEqual(fixed[edge]['time'],dict(state='known',value=clock))
                    self.assertEqual(fixed['locked'],dict(state='known',value=True))

    def test_arrival_clock_never_uses_a_day_number_or_clipped_negation(self):
        for text,quote,clock,accepted in (
                ('I arrive at 9 a.m.','I arrive at 9 a.m.','09:00',True),
                ('我09:00到达','09:00','09:00',True),
                ('I arrive at 9 a.m.','9 a.m.','10:00',False),
                ('I arrive not at 9 a.m.','9 a.m.','09:00',False),
                ('I arrive around 9 a.m.','9 a.m.','09:00',False),
                ('一共3天','3','03:00',False)):
            value=self.packet();value['observations']=[dict(field='arrival.time',state='known',value=clock,
                note=None,sources=[dict(source_index=0,quote=quote)])]
            turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
            with self.subTest(text=text):
                if accepted:parse_plan_understanding(packed(value),turns)
                else:
                    with self.assertRaises(InvalidInput):parse_plan_understanding(packed(value),turns)

    def test_standalone_explicit_trip_date_cannot_silently_become_undated(self):
        for text in ('明天出发','Start my trip tomorrow','我明天出发去北京玩三天',
                     'Plan three days in Beijing starting tomorrow','请安排北京三天，从2026-12-01开始。',
                     '我2026-12-01出发去北京玩三天','下礼拜三出发'):
            turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
            for observations in ([],[dict(field='start_date',state='unknown',value=None,note=None,
                                         sources=[dict(source_index=0,quote=text)])],
                                  [dict(field='start_date',state='unknown',value=None,note=None,
                                         sources=[dict(source_index=1,quote='直接出方案')])]):
                value=self.packet();value['observations']=observations
                with self.subTest(text=text,observations=observations),self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_embedded_explicit_start_compiles_only_from_its_real_date_span(self):
        for text,quote,day in (('我明天出发去北京玩三天','明天','2026-11-15'),
                              ('Plan three days in Beijing starting tomorrow','tomorrow','2026-11-15'),
                              ('我2026-12-01出发去北京玩三天','2026-12-01','2026-12-01'),
                              ('下礼拜三出发','下礼拜三','2026-11-18')):
            value=self.packet();value['observations'][0].update(value=day,sources=[dict(source_index=0,quote=quote)])
            with self.subTest(text=text):
                compiled=self.compile(value,(PlanningTurn(text,date(2026,11,14)),self.turns()[1]))
                self.assertEqual(compiled.fields['arrival']['date'],dict(state='known',value=day))

    def test_party_count_matches_original_number_and_never_a_question_or_condition(self):
        for text,count,accepted in (('只有我一人',1,True),('只有我一人',2,False),('Two people',2,True),
                ('三个人',3,True),('三个人',2,False),('Just me',1,True),('Just me',2,False),
                ('If two people travel',2,False),('Two people?',2,False),('Not two people',2,False),
                ('About two people',2,False),('一共三天',3,False),('If possible, two people',2,False)):
            value=self.packet();value['observations']=[dict(field='party_size',state='known',value=count,note=None,
                sources=[dict(source_index=0,quote=text)])]
            turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
            with self.subTest(text=text,count=count):
                if accepted:self.assertEqual(self.compile(value,turns).fields['party_size'],dict(state='known',value=count))
                else:
                    with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_clock_sources_keep_arrival_departure_and_assertion_semantics(self):
        for text,quote,field,accepted in (('Our flight leaves at 9 am','9 am','arrival.time',False),
                ('Our flight leaves at 9 am','9 am','departure.time',True),
                ('If I arrive at 9 am','9 am','arrival.time',False),
                ('If the flight is on time, I arrive at 9 am','9 am','arrival.time',False),
                ('Will I arrive at 9 am?','9 am','arrival.time',False),
                ('I arrive at 9 am and leave at 6 pm','9 am','arrival.time',True),
                ('I arrive at 9 am and leave at 6 pm','6 pm','arrival.time',False),
                ('I arrive at 9 am','9 am','departure.time',False),
                ('如果我09:00到达','09:00','arrival.time',False),
                ('我09:00到达吗？','09:00','arrival.time',False)):
            value=self.packet();value['observations']=[dict(field=field,state='known',value='18:00'if quote=='6 pm'else'09:00',
                note=None,sources=[dict(source_index=0,quote=quote)])]
            if accepted and text=='Our flight leaves at 9 am':
                value['observations'].append(dict(field='departure.mode',state='known',value='flight',note=None,
                    sources=[dict(source_index=0,quote='flight')]))
            if accepted and text=='I arrive at 9 am and leave at 6 pm':
                value['observations'].append(dict(field='departure.time',state='known',value='18:00',note=None,
                    sources=[dict(source_index=0,quote='6 pm')]))
            turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
            with self.subTest(text=text,field=field):
                if accepted:self.compile(value,turns)
                else:
                    with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_quoted_translation_and_third_party_clocks_never_become_traveler_facts(self):
        for text,quote,field,value in (
                ('Translate "Two people" into Chinese.','Two people','party_size',2),
                ('Translate "Hello, Two people, goodbye" into Chinese.','Two people','party_size',2),
                ('翻译“两个人”。','两个人','party_size',2),
                ('Translate "I arrive at 9 am" into Chinese.','9 am','arrival.time','09:00'),
                ('Translate "Hello, I arrive at 9 am, goodbye" into Chinese.','9 am','arrival.time','09:00'),
                ('My friend Alice arrives at 9 am; I arrive at 6 pm.','9 am','arrival.time','09:00'),
                ('朋友Alice09:00到达；我18:00到达。','09:00','arrival.time','09:00')):
            packet=self.packet();packet['observations']=[dict(field=field,state='known',value=value,note=None,
                sources=[dict(source_index=0,quote=quote)])]
            with self.subTest(text=text),self.assertRaises(InvalidInput):
                self.compile(packet,(PlanningTurn(text,date(2026,11,14)),self.turns()[1]))
        text='My friend Alice arrives at 9 am; I arrive at 6 pm.'
        packet=self.packet();packet['observations']=[dict(field='arrival.time',state='known',value='18:00',note=None,
            sources=[dict(source_index=0,quote='6 pm')])]
        self.assertEqual(self.compile(packet,(PlanningTurn(text,date(2026,11,14)),self.turns()[1])).fields['arrival']['time'],
                         dict(state='known',value='18:00'))

    def test_latest_explicit_undecided_date_replaces_earlier_known_date_without_defaults(self):
        for text in ('日期未定，不用明天了','My dates are undecided'):
            turns=(self.turns()[0],PlanningTurn(text,date(2026,11,15)),self.turns()[1])
            value=self.packet();value['current_source_index']=2
            with self.subTest(text=text),self.assertRaises(InvalidInput):self.compile(value,turns)
            value['observations']=[dict(field='start_date',state='unknown',value=None,note=None,
                sources=[dict(source_index=1,quote=text)])]
            result=self.compile(value,turns)
            self.assertEqual(result.start_date,dict(state='unknown'))
            self.assertNotEqual(result.fields['arrival']['date'].get('state'),'known')
            value['observations']=[]
            with self.assertRaises(InvalidInput):self.compile(value,turns)
            turns=(*turns[:-1],PlanningTurn('2026-12-01出发',date(2026,11,16)),turns[-1])
            value['current_source_index']=3
            value['observations']=[dict(field='start_date',state='known',value='2026-12-01',note=None,
                sources=[dict(source_index=2,quote='2026-12-01出发')])]
            self.assertEqual(self.compile(value,turns).fields['arrival']['date'],dict(state='known',value='2026-12-01'))

    def test_date_reset_order_is_preserved_inside_one_original_message(self):
        for text,known in (('2026-12-01出发，日期未定',False),('日期未定，2026-12-01出发',True)):
            turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
            value=self.packet();value['observations'][0].update(value='2026-12-01',
                sources=[dict(source_index=0,quote='2026-12-01出发')])
            with self.subTest(text=text):
                if known:self.compile(value,turns)
                else:
                    with self.assertRaises(InvalidInput):self.compile(value,turns)
                value['observations'][0].update(state='unknown',value=None,sources=[dict(source_index=0,quote='日期未定')])
                if known:
                    with self.assertRaises(InvalidInput):self.compile(value,turns)
                else:self.assertEqual(self.compile(value,turns).start_date,dict(state='unknown'))
        text='2026-12-01出发，2026-12-02开始'
        turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1]);value=self.packet()
        for day,accepted in (('2026-12-01',False),('2026-12-02',True)):
            value['observations'][0].update(value=day,sources=[dict(source_index=0,quote=day)])
            if accepted:self.compile(value,turns)
            else:
                with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_party_quote_after_another_sentence_uses_the_original_boundary(self):
        for text,start,party in (('明天出发。两个人。','明天出发','两个人'),
                                 ('Start my trip tomorrow. Two people.','Start my trip tomorrow','Two people')):
            value=self.packet();value['observations'][0]['sources']=[dict(source_index=0,quote=start)]
            value['observations'].append(dict(field='party_size',state='known',value=2,note=None,
                sources=[dict(source_index=0,quote=party)]))
            self.assertEqual(self.compile(value,(PlanningTurn(text,date(2026,11,14)),self.turns()[1])).fields['party_size'],
                dict(state='known',value=2))

    def test_departure_mode_and_first_full_day_remain_separate_from_frozen_needs_fields(self):
        from cj_api.local_lio_pipeline_inputs import planning_edges
        turns=(PlanningTurn('My flight leaves at 6 pm',date(2026,11,14)),
            PlanningTurn('Fill the first day',date(2026,11,15)),self.turns()[1])
        value=self.packet();value['current_source_index']=2
        value['observations']=[dict(field=field,state='known',value=given,note=None,sources=[dict(source_index=index,quote=quote)])
            for field,given,index,quote in (('departure.time','18:00',0,'6 pm'),('departure.mode','flight',0,'flight'),
                                          ('first_day_full',True,1,'Fill the first day'))]
        projection=self.compile(value,turns);edge=planning_edges(projection,3)
        self.assertNotIn('mode',projection.fields['departure'])
        self.assertNotIn('first_day_full',projection.fields)
        self.assertFalse(edge.first_unknown_recipe)
        self.assertEqual(edge.override_explanations,('first_day_full_requested',))
        self.assertEqual(edge.windows[-1][0].end,2*86400+15*3600)

    def test_departure_mode_matches_own_departure_not_arrival_other_people_or_translation(self):
        for text,quote,mode,accepted in (
                ('My train leaves at 6 pm','train','train',True),
                ('我的高铁18:00出发','高铁','train',True),
                ('My flight leaves at 6 pm','flight','train',False),
                ('My flight arrives at 6 pm','flight','flight',False),
                ('My friend Alice leaves on a flight at 6 pm','flight','flight',False),
                ('If my flight leaves at 6 pm','flight','flight',False),
                ('Translate "My flight leaves at 6 pm"','flight','flight',False),
                ('My flight leaves at 6 pm','flight',['flight'],False)):
            value=self.packet();value['observations']=[dict(field='departure.mode',state='known',value=mode,note=None,
                sources=[dict(source_index=0,quote=quote)])]
            if accepted:
                value['observations'].append(dict(field='departure.time',state='known',value='18:00',note=None,
                    sources=[dict(source_index=0,quote='18:00'if '18:00'in text else'6 pm')]))
            with self.subTest(text=text,mode=mode):
                if accepted:self.assertEqual(self.compile(value,(PlanningTurn(text,date(2026,11,14)),self.turns()[1])).edge_options['departure.mode'],dict(state='known',value=mode))
                else:
                    with self.assertRaises(InvalidInput):self.compile(value,(PlanningTurn(text,date(2026,11,14)),self.turns()[1]))

    def test_full_first_day_is_only_an_explicit_affirmative_request_and_missing_mode_stays_unresolved(self):
        from cj_api.local_lio_pipeline_inputs import planning_edges
        for text,accepted in (('第一天就排满',True),('Make the first day full',True),('不要第一天排满',False),
                              ('If possible, fill the first day',False),('Translate "Fill the first day"',False)):
            value=self.packet();value['observations']=[dict(field='first_day_full',state='known',value=True,note=None,
                sources=[dict(source_index=0,quote=text)])]
            with self.subTest(text=text):
                if accepted:self.compile(value,(PlanningTurn(text,date(2026,11,14)),self.turns()[1]))
                else:
                    with self.assertRaises(InvalidInput):self.compile(value,(PlanningTurn(text,date(2026,11,14)),self.turns()[1]))
        value=self.packet();value['observations']=[dict(field='departure.time',state='known',value='18:00',note=None,
            sources=[dict(source_index=0,quote='6 pm')])]
        projection=self.compile(value,(PlanningTurn('I leave at 6 pm',date(2026,11,14)),self.turns()[1]))
        self.assertEqual(projection.edge_options['departure.mode'],dict(state='missing'))
        self.assertIn('departure_buffer_mode_unknown',planning_edges(projection,3).unknowns)

    def test_later_departure_mode_or_full_day_instruction_cannot_restore_old_option(self):
        for field,first,last,old,new in (
                ('departure.mode','My flight leaves at 6 pm','My train leaves at 6 pm','flight','train'),
                ('first_day_full','Fill the first day','Keep the first day light',True,False)):
            turns=(PlanningTurn(first,date(2026,11,14)),PlanningTurn(last,date(2026,11,15)),self.turns()[1])
            value=self.packet();value['current_source_index']=2
            value['observations']=[dict(field=field,state='known',value=old,note=None,
                sources=[dict(source_index=0,quote=first)])]
            if field=='departure.mode':
                value['observations'].append(dict(field='departure.time',state='known',value='18:00',note=None,
                    sources=[dict(source_index=1,quote=last)]))
            with self.subTest(field=field),self.assertRaises(InvalidInput):self.compile(value,turns)
            value['observations'][0].update(value=new,sources=[dict(source_index=1,quote=last)])
            self.assertEqual(self.compile(value,turns).edge_options[field],dict(state='known',value=new))
            value['observations']=[]
            with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_clipped_conditional_cannot_authorize_full_or_light_first_day(self):
        for text,quote,option in (('If possible, fill the first day','fill the first day',True),
                ('如果可以，第一天就排满','第一天就排满',True),
                ('If possible, keep the first day light','keep the first day light',False),
                ('如果可以，第一天不要排满','第一天不要排满',False)):
            value=self.packet();value['observations']=[dict(field='first_day_full',state='known',value=option,note=None,
                sources=[dict(source_index=0,quote=quote)])]
            with self.subTest(text=text),self.assertRaises(InvalidInput):
                self.compile(value,(PlanningTurn(text,date(2026,11,14)),self.turns()[1]))

    def test_repeated_a_b_a_uses_actual_last_position_and_never_middle_option(self):
        for field,a,b,old,new in (
                ('departure.mode','My flight leaves at 6 pm','My train leaves at 6 pm','train','flight'),
                ('first_day_full','Fill the first day','Keep the first day light',False,True)):
            text=f'{a}, {b}, {a}';turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
            value=self.packet();value['observations']=[dict(field=field,state='known',value=old,note=None,
                sources=[dict(source_index=0,quote=b)])]
            if field=='departure.mode':
                value['observations'].append(dict(field='departure.time',state='known',value='18:00',note=None,
                    sources=[dict(source_index=0,quote=' '+a)]))
            with self.subTest(field=field),self.assertRaises(InvalidInput):self.compile(value,turns)
            value['observations'][0].update(value=new,sources=[dict(source_index=0,quote=a)])
            self.assertEqual(self.compile(value,turns).edge_options[field],dict(state='known',value=new))

    def test_latest_explicit_departure_clock_cannot_mix_with_new_mode_and_old_time(self):
        from cj_api.local_lio_pipeline_inputs import planning_edges
        turns=(PlanningTurn('My flight leaves at 6 pm',date(2026,11,14)),
               PlanningTurn('My train leaves at 9 am',date(2026,11,15)),self.turns()[1])
        value=self.packet();value['current_source_index']=2
        value['observations']=[dict(field='departure.mode',state='known',value='train',note=None,
            sources=[dict(source_index=1,quote='train')]),dict(field='departure.time',state='known',value='18:00',note=None,
            sources=[dict(source_index=0,quote='6 pm')])]
        with self.assertRaises(InvalidInput):self.compile(value,turns)
        value['observations'][1].update(value='09:00',sources=[dict(source_index=1,quote='9 am')])
        self.assertEqual(planning_edges(self.compile(value,turns),3).windows[-1][0].end,2*86400+7*3600+30*60)
        value['observations'][1]['state']='unknown';value['observations'][1]['value']=None
        with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_timezone_offset_is_never_an_arrival_clock_or_a_later_clock_update(self):
        for text,offset in (('I arrive at 9 am China time (UTC+08:00).','08:00'),
                ('I arrive at 9 am Beijing time (GMT+08:00).','08:00'),('我09:00到达（北京时间+08:00）','08:00')):
            quote='09:00'if text.startswith('我')else'9 am'
            value=self.packet();value['observations']=[dict(field='arrival.time',state='known',value='09:00',note=None,
                sources=[dict(source_index=0,quote=quote)])]
            turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
            with self.subTest(text=text):
                self.assertEqual(self.compile(value,turns).fields['arrival']['time'],dict(state='known',value='09:00'))
                value['observations'][0].update(value=offset,sources=[dict(source_index=0,quote=offset)])
                with self.assertRaises(InvalidInput):self.compile(value,turns)
        for text,quote in (('I arrive at 9 am (GMT-05:00).','9 am'),
                ('I arrive at 9 am, GMT-05:00.','9 am'),('我09:00到达，GMT-05:00。','09:00')):
            value=self.packet();value['observations']=[dict(field='arrival.time',state='known',value='09:00',note=None,
                sources=[dict(source_index=0,quote=quote)])]
            turns=(PlanningTurn(text,date(2026,11,14)),self.turns()[1])
            self.assertEqual(parse_plan_understanding(packed(value),turns).observations[0].value,'09:00')
            with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_explicit_negative_light_between_repeated_full_requests_has_its_own_scope(self):
        for a,b in (('Fill the first day','Do not fill the first day'),('第一天就排满','第一天不要排满')):
            turns=(PlanningTurn(f'{a}, {b}, {a}',date(2026,11,14)),self.turns()[1])
            value=self.packet();value['observations']=[dict(field='first_day_full',state='known',value=False,note=None,
                sources=[dict(source_index=0,quote=b)])]
            with self.assertRaises(InvalidInput):self.compile(value,turns)
            value['observations'][0].update(value=True,sources=[dict(source_index=0,quote=a)])
            self.assertEqual(self.compile(value,turns).edge_options['first_day_full'],dict(state='known',value=True))

    def test_unquoted_meta_request_never_turns_its_last_clause_into_a_trip_instruction(self):
        for text,quote in (('Translate this sentence into Chinese, fill the first day','fill the first day'),
                ('请把下面这句话翻译成英文，第一天就排满','第一天就排满')):
            value=self.packet();value['observations']=[dict(field='first_day_full',state='known',value=True,note=None,
                sources=[dict(source_index=0,quote=quote)])]
            with self.subTest(text=text),self.assertRaises(InvalidInput):
                self.compile(value,(PlanningTurn(text,date(2026,11,14)),self.turns()[1]))

    def test_a_later_explicit_date_can_replace_the_earlier_date_without_requiring_both(self):
        turns=(PlanningTurn('明天出发',date(2026,11,14)),PlanningTurn('2026-12-01出发',date(2026,11,15)),
               PlanningTurn('直接出方案',date(2026,11,16)))
        value=self.packet();value['current_source_index']=2
        value['observations'][0].update(value='2026-12-01',sources=[dict(source_index=1,quote='2026-12-01出发')])
        self.assertEqual(self.compile(value,turns).fields['arrival']['date'],dict(state='known',value='2026-12-01'))
        value['observations'][0].update(value='2026-11-15',sources=[dict(source_index=0,quote='明天出发')])
        with self.assertRaises(InvalidInput):self.compile(value,turns)

    def test_native_fixed_arrangement_phrase_keeps_legacy_selection_unchanged(self):
        from cj_api.lio_national_intake import fixed_sources_complete
        from cj_api.lio_plan_understanding import _PlanningFieldsData,project_plan_fields
        value,turns=self.fixed_case()
        quote='On day 1 I have a hotel meetup from 9:00 to 10:00. Keep this arrangement unchanged.'
        turns=(PlanningTurn(quote,date(2026,11,14)),turns[1])
        value['fixed_items'][0].update(label='hotel meetup',quote=quote)
        parsed=parse_plan_understanding(packed(value),turns);compiled=self.compile(value,turns)
        item,=compiled.fields['fixed_items']
        self.assertEqual(item['start']['time'],dict(state='known',value='09:00'))
        self.assertEqual(item['locked'],dict(state='known',value=True))
        projection=project_plan_fields(parsed)
        data=_PlanningFieldsData(dict(fields=projection.fields),projection.sources,projection.start_date,3)
        city=CityReference('110100','北京市','北京市',None,'city','Asia/Shanghai')
        self.assertFalse(fixed_sources_complete(data,compiled.fields,turns,city,ordinal_days=3))
        for prefix in ('Do not ', 'If '):
            bad=deepcopy(value);bad_quote=prefix+quote
            bad['fixed_items'][0]['quote']=bad_quote
            bad_turns=(PlanningTurn(bad_quote,date(2026,11,14)),turns[1])
            with self.assertRaises(InvalidInput):self.compile(bad,bad_turns)


if __name__=='__main__':unittest.main()
