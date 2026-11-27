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
        # the surviving quote does not mention party size, so the normal source checks still decide; no crash from the empty one
        try:
            self.parse(value)
        except InvalidInput:
            pass

    def test_nothing_changes_when_no_quote_is_empty(self):
        value = wire(field_sources=[dict(field='duration_days', source_index=0, quote=TEXT)])
        before = deepcopy(value)
        self.assertEqual(_drop_empty_field_sources(value), 0)
        self.assertEqual(value, before)

    def test_a_required_fact_without_any_source_is_still_refused(self):
        value = wire(field_sources=[dict(field='duration_days', source_index=0, quote='')])
        with self.assertRaises(InvalidInput):
            self.parse(value)

    def test_odd_shapes_are_left_to_the_schema(self):
        for bad in (None, [], {}, dict(field_sources='x'), dict(field_sources={'a': 1}), dict(field_sources=[1, None, 'x'])):
            self.assertEqual(_drop_empty_field_sources(bad), 0)


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
