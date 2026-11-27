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
        self.assertEqual(_duration_quote(self.TEXT, 2), '2天')
        self.assertEqual(_duration_quote('plan 3 days in Chengdu', 3), '3 days')
        self.assertEqual(_duration_quote('规划成都三天', 3), '三天')
        self.assertIsNone(_duration_quote('第一天故宫，第二天颐和园', 2))                 # 第一天 / 第二天 are ordinals, not counts
        self.assertIsNone(_duration_quote('每天走两万步', 2))
        self.assertIsNone(_duration_quote('玩2天，再玩3天', 2))                           # two different counts
        self.assertIsNone(_duration_quote('玩2天，也就是 二天', 2))                       # same count in two spellings: ambiguous
        self.assertIsNone(_duration_quote('规划北京2天', 3))                              # does not match the claimed count
        self.assertIsNone(_duration_quote('规划北京行程', 2))

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
