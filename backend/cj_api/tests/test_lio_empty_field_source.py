"""A model-supplied field source with an empty quote must not reject the whole plan (2026-11-28 Hong Kong v3 run:
`LIO_INTAKE_REJECTED code=flow_schema detail=field_sources:string_too_short`)."""
from copy import deepcopy
import json
import unittest

from cj_agent.lio_intake_optional_schema import OptionalIntake
from cj_api.lio_flow_intake import _drop_empty_field_sources, parse_flow
from cj_needs.domain import InvalidInput
from test_lio_planning_flow import flow, original

TEXT = '去成都玩三天'


def wire(**changes):
    value = flow(TEXT, city='成都', days=3, intent='plan', questions=())
    value.update(version='LIO-planning-intake.8', planning_request_index=0, needs_tools=True)
    value.update(changes)
    return value


class EmptyFieldSource(unittest.TestCase):
    def parse(self, value):
        return parse_flow(json.dumps(value), (original(TEXT),), (), 'current', None, schema=OptionalIntake)

    def test_the_failure_shape_was_a_schema_rejection(self):
        value = wire(party_size=2, field_sources=[dict(field='duration_days', source_index=0, quote=TEXT),
                                                    dict(field='party_size', source_index=0, quote='')])
        with self.assertRaises(Exception):
            OptionalIntake.model_validate(deepcopy(value))      # what the old code did first, for any empty quote

    def test_an_empty_quote_for_an_optional_fact_leaves_the_plan_and_marks_the_fact_unknown(self):
        for field, extra in (('party_size', dict(party_size=2)), ('start_date', dict(start_date='2026-12-01'))):
            with self.subTest(field=field):
                value = wire(**extra, field_sources=[dict(field='duration_days', source_index=0, quote=TEXT),
                                                     dict(field=field, source_index=0, quote='')])
                intake, _, facts = self.parse(value)
                self.assertEqual(intake.city['query'] if isinstance(intake.city, dict) else intake.city.query, '成都')
                self.assertEqual(facts['duration_days']['value'], 3)
                self.assertNotIn(field, facts)

    def test_whitespace_only_quotes_count_as_empty(self):
        value = wire(party_size=3, field_sources=[dict(field='duration_days', source_index=0, quote=TEXT),
                                                    dict(field='party_size', source_index=0, quote='  ')])
        self.assertNotIn('party_size', self.parse(value)[2])

    def test_a_good_source_for_the_same_field_survives_a_stray_empty_one(self):
        value = wire(party_size=2, field_sources=[dict(field='duration_days', source_index=0, quote=TEXT),
                                                    dict(field='party_size', source_index=0, quote=''),
                                                    dict(field='party_size', source_index=0, quote='三天')])
        # Only the empty reference goes. (Whether a quote really supports the fact is not decided here, as before.)
        _, _, facts = self.parse(value)
        self.assertEqual(facts['party_size']['value'], 2)
        self.assertEqual([source['quote'] for source in facts['party_size']['sources']], ['三天'])

    def test_nothing_changes_when_no_quote_is_empty(self):
        value = wire(field_sources=[dict(field='duration_days', source_index=0, quote=TEXT)])
        before = deepcopy(value)
        self.assertEqual(_drop_empty_field_sources(value), 0)
        self.assertEqual(value, before)

    def test_a_required_fact_whose_only_source_is_empty_is_restored_only_from_the_travelers_words(self):
        value = wire(field_sources=[dict(field='duration_days', source_index=0, quote='')])
        _, _, facts = self.parse(value)                                    # 「三天」 is right there in the message
        self.assertEqual(facts['duration_days']['sources'][0]['quote'], '三天')
        other = wire(field_sources=[dict(field='duration_days', source_index=0, quote='')], duration_days=5)
        with self.assertRaises(InvalidInput):                              # the words say 三天, the model says 5: refused
            self.parse(other)

    def test_odd_shapes_are_left_to_the_schema(self):
        for bad in (None, [], {}, dict(field_sources='x'), dict(field_sources={'a': 1}), dict(field_sources=[1, None, 'x'])):
            self.assertEqual(_drop_empty_field_sources(bad), 0)


class LoggedShape(unittest.TestCase):
    """The exact output of Hong Kong run 9f2fa849 (v3, 2026-11-28 16:56Z), from the retained rejected-intake file: day count 2,
    no source for it, and two empty sources for start_date and party_size, both of which were null and listed unknown."""
    TEXT = '帮我规划一个北京2天的行程：第一天故宫和景山，第二天颐和园。'

    def logged(self, **changes):
        value = flow(self.TEXT, city='北京', days=2, intent='plan', questions=('start_date',), reply='好的，请问哪天出发？')
        value.update(version='LIO-planning-intake.8', planning_request_index=0, needs_tools=True,
                     unknown_fields=['start_date', 'party_size'])
        value['field_sources'] = [dict(field='start_date', quote='', source_index=0), dict(field='party_size', quote='', source_index=0)]
        value.update(changes)
        return value

    def test_the_logged_output_is_planned_with_the_duration_source_restored_from_the_travelers_words(self):
        from test_lio_planning_flow import context, run
        saved, events, lookups, _ = run(self.logged(), self.TEXT)
        state = context(events)
        self.assertEqual((state['status'], state['authority']), ('plan_preview', 'plan'))
        self.assertEqual(state['facts']['duration_days']['value'], 2)
        self.assertEqual(state['facts']['duration_days']['sources'][0]['quote'], '2天')
        self.assertEqual(len(lookups), 1)

    def test_the_duration_quote_is_exact_unambiguous_and_only_from_the_latest_message(self):
        from cj_api.lio_flow_intake import _duration_quote
        self.assertEqual(_duration_quote(self.TEXT, 2, '北京'), '2天')
        self.assertEqual(_duration_quote('plan 3 days in Chengdu', 3, 'Chengdu'), '3 days')
        self.assertEqual(_duration_quote('去成都玩三天', 3, '成都'), '三天')
        self.assertIsNone(_duration_quote('第一天故宫，第二天颐和园', 2))                 # 第一天 / 第二天 are ordinals, not counts
        self.assertIsNone(_duration_quote('每天走两万步', 2))
        self.assertIsNone(_duration_quote('玩2天，再玩3天', 2))                           # two different counts
        self.assertIsNone(_duration_quote('玩2天，也就是 二天', 2))                       # same count in two spellings: ambiguous
        self.assertIsNone(_duration_quote('规划北京2天', 3))                              # does not match the claimed count
        self.assertIsNone(_duration_quote('规划北京行程', 2))
        for dated in ('2天后出发，规划北京', '规划北京，两天之后出发', '3天前订的酒店', 'leave in 2 days, plan Beijing', 'in 2 days I fly',
                      'booked 2 days ago', '2 days later we arrive', 'within 3 days'):   # dates, not a trip length
            with self.subTest(dated=dated):
                self.assertIsNone(_duration_quote(dated, 2) or _duration_quote(dated, 3))
        self.assertIsNone(_duration_quote('2天后出发，玩3天', 3))                          # two count-like spans: not recovered, even if one is a date
        self.assertEqual(_duration_quote('Plan a 3-day trip to Beijing', 3, 'Beijing'), '3-day')
        self.assertIsNone(_duration_quote('3-day trip to Beijing', 3, 'Beijing'))                    # not a plan request by itself: not recovered
        self.assertEqual(_duration_quote('规划北京三日游', 3, '北京'), '三日')

    def test_inputs_found_by_the_red_line_review_are_never_restored_as_a_trip_length(self):
        from cj_api.lio_flow_intake import _duration_quote
        for text, claimed in (
                # dates and past or leading stretches
                ('2天后出发去成都', 2), ('两天后出发去成都', 2), ('2日后出发去成都', 2), ('3天前订好了酒店', 3), ('leave in 3 days, plan Chengdu', 3),
                ('booked 3 days ago', 3), ('12月2日出发去成都', 2), ('2号出发规划北京', 2), ('3天内到', 3), ('过去3天很累，去成都', 3),
                ('前3天去成都', 3), ('最近3天', 3), ('未来3天', 3), ('接下来3天', 3), ('这3天', 3), ('next 3 days', 3), ('3 days from today', 3),
                ('within the 3 days', 3), ('3 days left', 3),
                # pieces of longer numbers, ranges, fractions
                ('去成都玩十二天', 2), ('去成都二十天', 10), ('去成都玩2.5天', 5), ('去成都玩2.5天', 2), ('一两天去成都', 2), ('一两天去成都', 1),
                ('去成都玩3-4天', 4), ('去成都玩3-4天', 3), ('3到4天', 4), ('3~4天', 4), ('3至4天', 4), ('3 to 4 days', 4), ('3-4 days', 4),
                ('3 or 4 days', 4), ('去成都玩一天半', 1), ('3天半', 3), ('三天半', 3),
                # ordinals, each, negation, spaces that slipped past a prefix list
                ('第3天去成都', 3), ('每天2小时', 2), ('去成都，不是3天', 3), ('不要3天', 3), ('去成都，第 3 天', 3), ('每 3 天', 3), ('前 3天', 3),
                ('过去 3天', 3), ('过去的3天', 3), ('in  3 days', 3),
                # other days of the traveler's life
                ('签证只有15天，帮我规划成都', 15), ('上次去北京玩了3天，这次规划成都', 3), ('倒时差要2天', 2), ('3天的时差', 3),
                # third review round: far negation, somebody else's or an earlier trip, things that are not a trip
                ('我不想玩3天，帮我规划成都', 3), ('不去成都玩3天了', 3), ('别去成都玩3天', 3), ('不能玩3天', 3), ('没法玩3天', 3),
                ("don't plan 3 days", 3), ('not for 3 days', 3), ('I will not stay 3 days', 3), ('never stay 3 days', 3),
                ("we can't spend 3 days", 3), ('上次去北京玩3天很累，这次规划成都', 3), ('朋友去成都玩3天，我也想去成都', 3),
                ('去年去成都玩3天', 3), ('my friend planned a 3-day trip, plan Chengdu', 3), ('安排3天的会议', 3), ('他们排3天的班', 3),
                ('计划3天的出差', 3), ('会议共3天', 3), ('共3天的会议', 3), ('隔离3天的行程', 3), ('签证3天的行程', 3),
                ('我在北京转机，停留3天的行程', 3), ('plan for 3 days of meetings', 3), ('plan 3 days of work', 3),
                ('spend 3 days waiting for my visa, plan Chengdu', 3), ('stay 3 days in quarantine', 3),
                ('for 3 days I will be away, plan Chengdu', 3), ('规划3天的预算', 3), ('我想住3天的酒店', 3), ('stay 3 days at the hotel', 3),
                ('玩3天', 3),   # not a plan request on its own
                # fifth review round: 「3日」 is usually the 3rd of the month; only 「N日游」 or a Chinese numeral counts
                ('帮我规划北京3日的行程', 3), ('帮我规划3日的行程', 3), ('帮我规划北京3日', 3), ('帮我规划北京2日的行程', 2),
                # fifth review round: no punctuation to cut the clause, and a destination that is not this plan's
                ('帮我规划北京行程我在深圳待3天再过去', 3), ('帮我规划北京行程 我先在上海玩3天', 3), ('帮我规划北京行程 我在医院住3天', 3),
                ('帮我规划成都行程 展会排3天', 3), ('帮我规划北京行程我爸来北京住3天', 3),
                ('plan a trip to Beijing I will stay 3 days in Shanghai first', 3), ('plan a Beijing trip the kids stay 3 days at camp', 3),
                # fourth review round: the count sits in a later clause that is not the request itself
                ('帮我规划北京行程，我在深圳待3天再过去', 3), ('帮我规划北京行程，我在医院住3天', 3), ('帮我规划成都行程，孩子在夏令营待3天', 3),
                ('帮我规划成都行程，我爸妈来北京住3天', 3), ('帮我规划成都行程，路上要待3天', 3),
                ('plan a trip to Beijing, I will stay 3 days in Shanghai first', 3), ('plan a Beijing trip, the kids stay 3 days at camp', 3),
                ('plan a trip to Beijing, my mom will stay 3 days', 3), ('帮我规划成都行程，之后去重庆玩3天', 3),
                ('帮我规划成都和重庆的行程，重庆玩3天', 3), ('帮我规划北京行程，我先在上海玩3天', 3), ('plan a trip to Beijing; Shanghai for 3 days', 3),
                ('帮我规划成都行程，展会排3天', 3), ('帮我规划成都行程，婚礼安排3天', 3), ('帮我规划成都行程，猫寄养要3天的计划', 3),
                ('帮我规划成都行程，车只租了3天的计划', 3), ('帮我规划成都行程，签证有效期3天', 3), ('帮我规划成都行程，我只能请3天假', 3),
                # two counts in one message
                ('玩2天，再玩3天', 2), ('玩2天，再玩3天', 3)):
            with self.subTest(text=text, claimed=claimed):
                self.assertIsNone(_duration_quote(text, claimed, '成都'))
                self.assertIsNone(_duration_quote(text, claimed, '北京'))
        for text, claimed, plan_city in (('我想去成都玩3天，帮我规划重庆', 3, '重庆'), ('帮我规划重庆行程，想去成都玩3天', 3, '重庆'),
                                         ('帮我规划成都行程，去上海玩3天', 3, '成都'), ('去上海玩3天，然后帮我规划北京', 3, '北京')):
            with self.subTest(text=text, plan_city=plan_city):                 # a 「去X玩N天」 whose X is not this plan's city
                self.assertIsNone(_duration_quote(text, claimed, plan_city))
        for text, claimed, quote, city in (
                ('帮我规划一个北京2天的行程：第一天故宫和景山，第二天颐和园。', 2, '2天', '北京'), ('去成都玩三天', 3, '三天', '成都'),
                ('我想去成都玩3天，预算1000', 3, '3天', '成都'), ('去成都玩3天但是预算1000', 3, '3天', '成都'),
                ('帮我规划成都三天的行程，不要太累', 3, '三天', '成都'), ('规划北京三日游', 3, '三日', '北京'),
                ('规划北京3日游', 3, '3日', '北京'), ('帮我规划北京三日的行程', 3, '三日', '北京'), ('规划成都三天两晚', 3, '三天', '成都'), ('去成都玩十天', 10, '十天', '成都'),
                ('帮我规划无锡3天的行程', 3, '3天', '无锡'),
                ('帮我规划成都行程 3天', 3, None, '成都'),
                ('Plan 3 days in Chengdu', 3, '3 days', 'Chengdu'), ('Plan a 3-day trip', 3, '3-day', None),
                ('Plan a trip to Chengdu for 3 days', 3, '3 days', 'Chengdu'), ('三天', 3, '三天', None), ('3 days', 3, '3 days', None)):
            with self.subTest(text=text, claimed=claimed):
                self.assertEqual(_duration_quote(text, claimed, city), quote)

    def test_no_restoration_without_a_traveler_span_or_when_the_model_already_gave_a_source(self):
        text = '规划北京行程，去故宫'
        with self.assertRaises(InvalidInput):                                              # 2 days, nothing in the words says 2 days
            parse_flow(json.dumps(self.logged(duration_days=2, reply='ok')), (original(text),), (), 'm', None, schema=OptionalIntake)
        given = self.logged()
        given['field_sources'].append(dict(field='duration_days', source_index=0, quote='2天'))
        count = len(given['field_sources'])
        parse_flow(json.dumps(given), (original(self.TEXT),), (), 'm', None, schema=OptionalIntake)
        self.assertEqual(count, 3)

    def test_a_model_that_omits_the_duration_source_without_any_empty_one_is_still_refused(self):
        value = self.logged(field_sources=[])
        with self.assertRaises(InvalidInput):
            parse_flow(json.dumps(value), (original(self.TEXT),), (), 'm', None, schema=OptionalIntake)


class NullQuote(unittest.TestCase):
    """Hong Kong run 30aa955a (v3, 2026-11-28, after #2112): `field_sources` held `{field: start_date, quote: "null"}` for a start date
    that was itself null; `quote` is a string that is not in the traveler's words, so `field_source_binding` refused the whole plan."""
    TEXT = '帮我规划一个北京2天的行程：第一天故宫和景山，第二天颐和园。'

    def logged(self, **changes):
        value = flow(self.TEXT, city='北京', days=2, intent='plan', questions=('start_date', 'party_size'), reply='好的，请问哪天出发、几个人？')
        value.update(version='LIO-planning-intake.8', planning_request_index=0, needs_tools=True, unknown_fields=['start_date', 'party_size'])
        value['field_sources'] = [dict(field='start_date', source_index=0, quote='null'), dict(field='duration_days', source_index=0, quote='2天')]
        value.update(changes)
        return value

    def parse(self, value):
        return parse_flow(json.dumps(value), (original(self.TEXT),), (), 'current', None, schema=OptionalIntake)

    def test_the_logged_output_is_planned(self):
        from test_lio_planning_flow import context, run
        saved, events, lookups, _ = run(self.logged(), self.TEXT)
        state = context(events)
        self.assertEqual((state['status'], state['authority']), ('plan_preview', 'plan'))
        self.assertEqual(state['facts']['duration_days']['value'], 2)
        self.assertNotIn('start_date', state['facts'])

    def test_a_source_for_an_absent_fact_is_dropped_whatever_it_quotes(self):
        for quote in ('null', 'None', 'unknown', 'N/A', '未指定', self.TEXT[:4], '2天'):
            for field in ('start_date', 'party_size'):
                with self.subTest(quote=quote, field=field):
                    value = self.logged(field_sources=[dict(field=field, source_index=0, quote=quote), dict(field='duration_days', source_index=0, quote='2天')])
                    _, _, facts = self.parse(value)
                    self.assertNotIn(field, facts)
                    self.assertEqual(facts['duration_days']['value'], 2)

    def test_a_present_date_or_party_whose_quote_is_not_the_travelers_words_is_still_refused_whole(self):
        # Invented evidence for a value that IS stated is not repaired and not trusted: the plan is refused as before.
        for change in (dict(start_date='2026-12-01'), dict(party_size=2)):
            field = next(iter(change))
            with self.subTest(field=field):
                value = self.logged(**change, unknown_fields=[], field_sources=[dict(field=field, source_index=0, quote='as stated earlier'),
                                                                                  dict(field='duration_days', source_index=0, quote='2天')])
                with self.assertRaises(InvalidInput):
                    self.parse(value)

    def test_a_quote_that_is_in_the_travelers_words_is_left_to_the_normal_checks(self):
        value = self.logged(party_size=2, unknown_fields=['start_date'],
                            field_sources=[dict(field='party_size', source_index=0, quote='北京'), dict(field='duration_days', source_index=0, quote='2天')])
        _, _, facts = self.parse(value)
        self.assertEqual(facts['party_size']['sources'][0]['quote'], '北京')       # the source check is unchanged (it never judged meaning)

    def test_a_missing_or_non_string_quote_for_an_optional_fact_is_dropped_and_for_a_required_one_still_refused(self):
        value = self.logged(field_sources=[dict(field='start_date', source_index=0, quote=None), dict(field='duration_days', source_index=0, quote='2天')])
        self.assertEqual(self.parse(value)[2]['duration_days']['value'], 2)
        refused = self.logged(field_sources=[dict(field='duration_days', source_index=0, quote='not in the message')])
        with self.assertRaises(InvalidInput):
            self.parse(refused)


def wish(label, quote, **changes):
    value = dict(label=label, kind='intent', quote=quote, source_index=0, detail_refs=[], applies_to=['self'], locked=None, booking_evidence=None,
                 start_date=None, start_time=None, start_timezone=None, start_place=None, end_date=None, end_time=None, end_timezone=None, end_place=None,
                 unknown_fields=['start_date', 'start_time', 'end_time', 'locked'], uncertain_fields={})
    value.update(changes)
    return value


class WishItems(unittest.TestCase):
    """Hong Kong run 869c104a (v2, 2026-11-28): day-by-day sightseeing wishes came back as `intent` fixed items and the plan stopped to
    ask for their participants, dates and clocks. An item with nothing that says it is fixed is dropped, as if not provided."""
    TEXT = NullQuote.TEXT

    def test_the_two_hong_kong_shapes_plan_instead_of_asking(self):
        from test_lio_planning_flow import context, run
        for changes in ({}, dict(locked=False)):
            with self.subTest(changes=changes):
                value = NullQuote().logged()
                value['fixed_items'] = [wish('故宫和景山', '第一天故宫和景山', **changes), wish('颐和园', '第二天颐和园', **changes)]
                _, events, lookups, _ = run(value, self.TEXT)
                state = context(events)
                self.assertEqual((state['status'], state['authority']), ('plan_preview', 'plan'))
                self.assertEqual(len(lookups), 1)

    def test_known_residual_a_fixed_item_with_no_fixed_word_is_taken_for_a_wish(self):
        # Known and accepted (statement 2026-11-28 under JT's pre-authorization, P2): a real fixed arrangement whose quote and name have none
        # of the fixed, booked, paid or timed words above is dropped as if not provided: it is not locked, nothing false is written, and
        # the planner still sees the traveler's words. A number rule would also keep a whole-sentence quote with 「2天」 and bring the
        # Hong Kong failure back, so there is none. Whether to replace this by a residual whitelist waits for the real `fixed_items` of
        # the v2 retest.
        from cj_api.lio_flow_intake import _drop_wish_items
        for quote in ('Day 1 Palace Museum at nine', 'Palace Museum 0900', '故宫14h', '9到11故宫', '12.1故宫', '1日故宫', 'on the 1st Palace Museum',
                      '12-01故宫', '第一天故宫，三个人', '一号故宫'):
            with self.subTest(quote=quote):
                self.assertEqual(_drop_wish_items([wish('故宫', quote)]), 1)

    def test_an_item_with_anything_that_says_it_is_fixed_is_kept(self):
        from cj_api.lio_flow_intake import _drop_wish_items
        keep = [wish('故宫', '第一天故宫', locked=True), wish('故宫', '第一天故宫', booking_status='booked'), wish('故宫', '第一天故宫', start_time='09:00'),
                wish('故宫', '第一天故宫', start_date='2026-12-01'), wish('故宫', '第一天故宫', start_place='东门'),
                wish('故宫', '第一天故宫已预约'), wish('故宫（固定安排）', '第一天故宫'),
                # red-line review round: real bookings and clocks the shared marker words miss
                wish('故宫', '第一天故宫和景山已经订好票'), wish('故宫', '故宫门票订好了'), wish('故宫', '已经买好票'), wish('故宫', '已经订了故宫的票'),
                wish('Palace Museum', 'I booked the Palace Museum'), wish('Palace Museum', 'tickets booked'), wish('Palace Museum', 'Day 1: Palace Museum 9am'),
                # #2124: arranged by others, tours, guides, spelled-out clocks, noon
                wish('故宫', '第一天故宫，家人已经说好了'), wish('故宫', '第一天去故宫，跟团'), wish('Palace Museum', 'Day 1 Palace Museum with my tour group'),
                wish('故宫', '第一天故宫（团队行程）'), wish('故宫', '导游带我们去故宫'), wish('故宫', '已经约好导游'), wish('故宫', '已经安排好了故宫'),
                wish('Palace Museum', 'already arranged: Palace Museum'), wish('故宫', '参加公司团建，第一天故宫'), wish('故宫', '第一天下午两点故宫'),
                wish('故宫', '早上八点半故宫'), wish('Palace Museum', 'Palace Museum at noon'), wish('Palace Museum', "Palace Museum at 9 o'clock"),
                wish('故宫', '第一天包车去故宫'), wish('Palace Museum', 'Day 1 guided tour of the Palace Museum'), wish('故宫', '第一天中午故宫'),
                # third review round: an explicit time, date or payment written another way, and sign-ups
                wish('Palace Museum', 'Day 1 Palace Museum at 9'), wish('Palace Museum', 'Palace Museum nine am'), wish('Palace Museum', 'Palace Museum 9 in the morning'),
                wish('故宫', '第一天故宫，12/1'), wish('故宫', '十二月一号故宫'), wish('Palace Museum', 'Day 1 (Dec 1) Palace Museum'),
                wish('故宫', '第一天故宫，已经付款了'), wish('故宫', '交了定金'), wish('Palace Museum', 'already paid'), wish('Palace Museum', 'deposit sent'),
                wish('故宫', '已经报名了故宫'), wish('Palace Museum', 'signed up for the Palace Museum'), wish('故宫', '第一天故宫上午场'),
                wish('故宫', '故宫讲解员'), wish('故宫', '故宫名额已经拿到'), wish('故宫', '第一天开会，会议'),
                # fourth review round (words only, no number rule): times, dates, payments, orders, confirmations written with a word
                wish('故宫', '下周一故宫'), wish('故宫', '周六故宫'), wish('Palace Museum', '1 December Palace Museum'),
                wish('Palace Museum', 'on Saturday Palace Museum'),
                wish('故宫', '付过钱了'), wish('故宫', '已支付'), wish('故宫', '已经买单'), wish('故宫', '已经下单'), wish('Palace Museum', 'already purchased'),
                wish('Palace Museum', 'I bought entry'), wish('Palace Museum', 'order placed'), wish('Palace Museum', 'I have a pass'),
                wish('Palace Museum', 'I have an appointment'), wish('故宫', '已约'), wish('故宫', '约了故宫'), wish('故宫', '预留了故宫'), wish('故宫', '订单号123456'),
                wish('故宫', '已经订上了'), wish('故宫', '订到了故宫'), wish('故宫', '买到了故宫'), wish('故宫', '入场券到手'), wish('故宫', '已核销'),
                wish('Palace Museum', 'scheduled'), wish('Palace Museum', 'all set'),
                # added in the word-only round: holidays, next month, confirmations
                wish('故宫', '春节故宫'), wish('故宫', '下个月故宫'), wish('故宫', '国庆去故宫'), wish('故宫', '今晚故宫'), wish('故宫', '已经确认'), wish('故宫', '已经落实'),
                wish('故宫', '敲定了故宫'), wish('故宫', '定下来了'), wish('故宫', '已经办好'), wish('故宫', '人家给留了位'), wish('Palace Museum', 'secured entry'),
                wish('Palace Museum', 'settled'), wish('Palace Museum', 'registered'), wish('Palace Museum', 'we are on the list'), wish('Palace Museum', 'next month'),
                wish('Palace Museum', 'on Christmas'), wish('故宫', '掏了钱'), wish('Palace Museum', 'comped'),
                wish('故宫', '第一天9:30故宫'), wish('故宫', '第一天上午9点故宫'), wish('故宫', '12月1日故宫'), wish('故宫', '2026-12-01 故宫'), wish('故宫', '第一天故宫', detail_refs=[dict(source_index=0, quote='x')]),
                wish('故宫', '第一天故宫', kind='appointment'), wish('酒店', '第一天酒店', kind='hotel'), wish('机票', '第一天航班', kind='transport')]
        items = [dict(item) for item in keep]
        self.assertEqual(_drop_wish_items(items), 0)
        self.assertEqual(items, keep)
        for request in ('帮我安排好北京两天的行程：第一天故宫和景山，第二天颐和园。', '日期还没确定，第一天故宫', '帮我确认一下路线，第一天故宫'):
            with self.subTest(request=request):         # a request word in a whole-sentence quote must not keep a wish (the P0 would be back)
                self.assertEqual(_drop_wish_items([wish('故宫', request)]), 1)
        for plain in ('第一天故宫和景山', '第二天颐和园', '想去故宫转转', 'I want to see the Palace Museum on day 1',
                      '第一天上午故宫', '下午逛景山', 'Day 2 Jinli and the old street'):
            with self.subTest(plain=plain):
                only = [wish('故宫', plain)]
                self.assertEqual(_drop_wish_items(only), 1, plain)
        mixed = [wish('故宫', '第一天故宫'), wish('酒店集合', '第一天9点酒店集合', kind='hotel', locked=True)]
        self.assertEqual(_drop_wish_items(mixed), 1)
        self.assertEqual([item['kind'] for item in mixed], ['hotel'])


class EndToEnd(unittest.TestCase):
    def test_the_whole_plan_goes_through_like_the_same_plan_without_the_empty_source(self):
        # Through the real intake runner: the empty quote changes nothing about what is planned or stored.
        from test_lio_planning_flow import context, run
        bad = wire(party_size=2, field_sources=[dict(field='duration_days', source_index=0, quote=TEXT),
                                                 dict(field='party_size', source_index=0, quote='')])
        clean = wire(unknown_fields=['party_size'], field_sources=[dict(field='duration_days', source_index=0, quote=TEXT)])
        saved_bad, events_bad, lookups_bad, _ = run(bad, TEXT)
        saved_clean, events_clean, lookups_clean, _ = run(clean, TEXT)
        self.assertEqual((len(saved_bad), len(lookups_bad)), (len(saved_clean), len(lookups_clean)))
        self.assertEqual(context(events_bad)['status'], context(events_clean)['status'])
        self.assertEqual(context(events_bad)['facts'].keys(), context(events_clean)['facts'].keys())
        self.assertNotEqual(context(events_bad)['status'], 'rejected')


if __name__ == '__main__':
    unittest.main()
