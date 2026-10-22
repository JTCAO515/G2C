"""Consume the pinned real PLACE parser/types using synthetic bytes only."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import json
import unittest

from cj_place import (ORIGIN, Config, Coordinate, Departure, Endpoint, FieldState,
                      Observed, Outcome, Quantity, Response, RouteQuery, parse_response, prepare)
from cj_feasibility import Candidate
from cj_feasibility.routes import Window, assess_route
from test_validator import codes, encode, event, history, item, known

AT = datetime(2026, 10, 22, 1, tzinfo=timezone.utc)


def seconds(raw):
    return Observed(FieldState.PRESENT, Quantity(raw, Decimal(raw), 's'))


def fixture(duration='3600', gap='09:15', *, evidence='synthetic'):
    a = item('a', start=event('2026-10-22', '08:00'), end=event('2026-10-22', '09:00'))
    b = item('b', start=event('2026-10-22', gap), end=event('2026-10-22', '12:00'))
    before, revisions = history({'fixed_items': [a, b]})
    candidate = Candidate(before.needs_id, before.version, before.content)
    query = RouteQuery(Endpoint('SYNTH_A', Coordinate('116.1,39.1'), 'exit'),
                       Endpoint('SYNTH_B', Coordinate('116.2,39.2'), 'entrance'),
                       'walking', Departure('at_query_time', None))
    config = Config(ORIGIN, 4096, 16384, 3, 60)
    request = prepare(config, query, 'synthetic-cj035-route', AT)
    path = {'distance': '1000'}
    if duration is not None:
        path['duration'] = duration
    payload = {'status': '1', 'infocode': '10000', 'info': 'OK', 'count': '1',
               'route': {'origin': query.origin.coordinate.raw, 'destination': query.destination.coordinate.raw,
                         'paths': [path]}}
    response = Response(request.binding_digest, request.origin, request.path, 200,
                        encode(payload), AT + timedelta(seconds=1))
    result = parse_response(config, request, response, now=AT + timedelta(seconds=2), evidence=evidence)
    assert result.outcome is Outcome.OK
    window = Window('a', 'b', query, seconds('0'), seconds('0'))
    return dict(before=before, revisions=revisions, candidate=candidate, window=window, result=result,
                route_index=0, request=request, config=config, as_of=AT + timedelta(seconds=2),
                selected_fields=frozenset(), selected_item_ids=frozenset())


def details(report, code='ROUTE_CONDITIONAL_WINDOW'):
    return dict(next(c.details for c in report.checks if c.code == code))


class RouteTests(unittest.TestCase):
    def test_sixty_minutes_cannot_fit_fifteen_conditionally_not_reality(self):
        args = fixture()
        r = assess_route(**args)
        self.assertEqual(r.conditional_relation, 'required_exceeds_gap')
        self.assertEqual(details(r)['required_seconds'], '3600')
        self.assertEqual(details(r)['gap_seconds'], '900')
        self.assertEqual(r.status, 'UNKNOWN')
        self.assertIn('ROUTE_EVIDENCE_UNVERIFIED', codes(r, 'UNKNOWN'))
        self.assertIs(r.result, args['result'])
        self.assertIs(r.result.source, args['result'].source)
        self.assertIs(r.request, args['request'])
        self.assertIs(r.window.query.origin, args['window'].query.origin)

    def test_explicit_buffer_rest_and_fractional_seconds_no_rounding(self):
        args = fixture(duration='899.999999')
        args['window'] = replace(args['window'], buffer=seconds('0.000001'), rest=seconds('0.000001'))
        with localcontext() as ctx:
            ctx.prec, ctx.Emax, ctx.Emin = 2, 2, -2
            r = assess_route(**args)
        self.assertEqual(details(r)['required_seconds'], '900.000001')
        self.assertEqual(r.conditional_relation, 'required_exceeds_gap')
        args['window'] = replace(args['window'], rest=seconds('0'))
        r = assess_route(**args)
        self.assertEqual(r.conditional_relation, 'required_within_gap')
        self.assertEqual(r.status, 'UNKNOWN')

    def test_missing_duration_and_each_observed_state_never_zero(self):
        for state in FieldState:
            if state is FieldState.PRESENT:
                continue
            args = fixture()
            route = replace(args['result'].routes[0], duration=Observed(state))
            args['result'] = replace(args['result'], routes=(route,))
            r = assess_route(**args)
            self.assertIsNone(r.conditional_relation)
            self.assertIn('route.duration', next(c.missing for c in r.checks if c.code == 'ROUTE_REQUIRED_SECONDS_UNKNOWN'))
        args = fixture(duration=None)
        self.assertIsNone(assess_route(**args).conditional_relation)

    def test_no_inferred_buffer_or_rest(self):
        for field in ('buffer', 'rest'):
            args = fixture()
            args['window'] = replace(args['window'], **{field: Observed(FieldState.UNKNOWN)})
            r = assess_route(**args)
            self.assertIsNone(r.conditional_relation)
            self.assertIn('ROUTE_REQUIRED_SECONDS_UNKNOWN', codes(r))

    def test_wrong_identity_role_coordinates_mode_and_result_query_unknown(self):
        for part in ('id', 'role', 'coordinates', 'mode', 'departure'):
            args = fixture()
            query = args['window'].query
            if part == 'id':
                query = replace(query, origin=replace(query.origin, provider_id='SYNTH_OTHER'))
            elif part == 'role':
                query = replace(query, origin=replace(query.origin, coordinate_role='entrance'))
            elif part == 'coordinates':
                query = replace(query, origin=replace(query.origin, coordinate=Coordinate('116.100001,39.1')))
            elif part == 'mode':
                query = replace(query, mode='driving')
            else:
                query = replace(query, departure=Departure('specified_time', AT))
            args['window'] = replace(args['window'], query=query)
            r = assess_route(**args)
            self.assertIsNone(r.conditional_relation)
            self.assertEqual(r.status, 'UNKNOWN')
        args = fixture()
        args['result'] = replace(args['result'], query=replace(args['window'].query, mode='driving'))
        self.assertIn('ROUTE_QUERY_BINDING_UNKNOWN', codes(assess_route(**args)))

    def test_stale_and_timestamp_anomalies_unknown(self):
        args = fixture()
        args['as_of'] = AT + timedelta(seconds=61)
        r = assess_route(**args)
        self.assertIn('ROUTE_SOURCE_STALE', codes(r))
        self.assertIsNone(r.conditional_relation)
        self.assertEqual(details(r, 'ROUTE_SOURCE_STALE')['query_age_seconds'], '61')
        for delta in (-1, 10):
            args = fixture()
            args['result'] = replace(args['result'], source=replace(args['result'].source, received_at=AT+timedelta(seconds=delta)))
            self.assertIn('ROUTE_SOURCE_TIME_UNKNOWN', codes(assess_route(**args)))
        args = fixture()
        args['as_of'] = AT + timedelta(seconds=60)
        self.assertIsNotNone(assess_route(**args).conditional_relation)  # explicit inclusive max age

    def test_source_ref_digest_endpoint_version_and_original_time_bound(self):
        for key, value in [('request_ref','other'), ('binding_digest','0'*64),
                           ('endpoint',ORIGIN+'/v3/direction/driving'), ('api_version','v2'),
                           ('query_started_at',AT+timedelta(seconds=1)), ('provider','other')]:
            args = fixture()
            args['result'] = replace(args['result'], source=replace(args['result'].source, **{key:value}))
            r = assess_route(**args)
            self.assertIn('ROUTE_SOURCE_BINDING_UNKNOWN', codes(r))
            self.assertIsNone(r.conditional_relation)
        args = fixture()
        args['request'] = replace(args['request'], binding_digest='0'*64)
        self.assertIn('ROUTE_QUERY_BINDING_UNKNOWN', codes(assess_route(**args)))

    def test_future_or_past_departure_not_inferred_from_query_time(self):
        for time in ('08:59', '09:01'):
            args = fixture()
            fields = json.loads(args['candidate'].content)
            fields['fixed_items'][0]['end'] = event('2026-10-22',time)
            # Explicit selected unlocked edit passes protection, applicability still unknown.
            args['candidate'] = replace(args['candidate'], content=encode(fields))
            args['selected_fields'], args['selected_item_ids'] = frozenset({'fixed_items'}), frozenset({'a'})
            r = assess_route(**args)
            self.assertIn('ROUTE_FUTURE_APPLICABILITY_UNKNOWN', codes(r))
            self.assertIsNone(r.conditional_relation)

    def test_unverified_fixture_never_promoted_and_fake_trust_rejected(self):
        for category in ('synthetic','unverified_bytes'):
            r = assess_route(**fixture(duration='1', evidence=category))
            self.assertEqual(r.status,'UNKNOWN')
            self.assertEqual(r.conditional_relation,'required_within_gap')
        args = fixture()
        args['result'] = replace(args['result'],source=replace(args['result'].source,evidence='trusted'))
        r = assess_route(**args)
        self.assertEqual(r.status,'INVALID')
        self.assertIsNone(r.conditional_relation)

    def test_quantity_invalid_unit_nan_negative_raw_mismatch_not_usable(self):
        for q in (Quantity('1',Decimal(1),'m'),Quantity('NaN',Decimal('NaN'),'s'),
                  Quantity('-1',Decimal(-1),'s'),Quantity('1',Decimal(2),'s'),
                  Quantity('1e999999',Decimal('1e999999'),'s')):
            args = fixture()
            args['result'] = replace(args['result'],routes=(replace(args['result'].routes[0],duration=Observed(FieldState.PRESENT,q)),))
            r=assess_route(**args)
            self.assertIsNone(r.conditional_relation)
            self.assertIn('ROUTE_REQUIRED_SECONDS_UNKNOWN',codes(r))

    def test_protected_candidate_change_blocks_arithmetic(self):
        args=fixture()
        fields=json.loads(args['candidate'].content)
        fields['fixed_items'][0]['end']=event('2026-10-22','08:55')
        args['candidate']=replace(args['candidate'],content=encode(fields))
        r=assess_route(**args)
        self.assertEqual(r.status,'CONFLICT')
        self.assertIn('ROUTE_PROTECTION_WITHHELD',codes(r))
        self.assertIsNone(r.conditional_relation)

    def test_different_subjects_unknown_and_cancelled_not_imposed(self):
        for scenario in ('different','cancelled','unknown','missing_time'):
            args=fixture()
            fields=json.loads(args['candidate'].content)
            if scenario=='different':
                fields['companions']={'m':'Mother'}
                fields['fixed_items'][1]['applies_to']=['companion:m']
            elif scenario=='cancelled':
                fields['fixed_items'][1]['booking_status']=known('cancelled')
            elif scenario=='unknown':
                fields['fixed_items'][1]['booking_status']={'state':'unknown'}
            else:
                fields['fixed_items'][1]['start']['date']={'state':'missing'}
            args['before'],args['revisions']=history(fields)
            args['candidate']=Candidate(args['before'].needs_id,args['before'].version,args['before'].content)
            r=assess_route(**args)
            self.assertEqual(r.status,'UNKNOWN')
            self.assertIsNone(r.conditional_relation)

    def test_no_results_missing_source_no_automatic_route_selection(self):
        for change in (dict(outcome=Outcome.NO_RESULTS),dict(source=None),dict(routes=())):
            args=fixture()
            args['result']=replace(args['result'],**change)
            r=assess_route(**args)
            self.assertEqual(r.status,'UNKNOWN')
            self.assertIsNone(r.conditional_relation)
        for index in (-1,1,True):
            args=fixture()
            args['route_index']=index
            self.assertIsNone(assess_route(**args).conditional_relation)

    def test_inputs_unchanged_deterministic_and_bilingual(self):
        args=fixture()
        old=repr(args)
        a,b=assess_route(**args),assess_route(**args)
        self.assertEqual(a,b)
        self.assertEqual(repr(args),old)
        for c in a.checks:
            self.assertTrue(c.zh and c.en)
            if c.status=='UNKNOWN':
                self.assertTrue(c.missing)


class AdditionalRouteRiskTests(unittest.TestCase):
    def test_route_entry_cannot_claim_another_query_or_future_guarantee(self):
        for change in (dict(future_guaranteed=True), dict(time_semantics='future'),
                       dict(query=replace(fixture()['window'].query, mode='driving'))):
            args=fixture()
            args['result']=replace(args['result'],routes=(replace(args['result'].routes[0],**change),))
            r=assess_route(**args)
            self.assertIn('ROUTE_VALUE_BINDING_UNKNOWN',codes(r))
            self.assertIsNone(r.conditional_relation)

    def test_same_or_absent_item_and_naive_asof_invalid(self):
        args=fixture()
        args['window']=replace(args['window'],origin_item_id='b')
        self.assertEqual(assess_route(**args).status,'INVALID')
        args=fixture()
        args['window']=replace(args['window'],origin_item_id='absent')
        self.assertEqual(assess_route(**args).status,'INVALID')
        args=fixture()
        args['as_of']=AT.replace(tzinfo=None)
        self.assertEqual(assess_route(**args).status,'INVALID')

    def test_explicit_zero_duration_stays_zero_but_unknown_is_not_zero(self):
        args=fixture(duration='0')
        r=assess_route(**args)
        self.assertEqual(details(r)['duration_seconds'],'0')
        self.assertEqual(r.conditional_relation,'required_within_gap')
        self.assertIn('ROUTE_ENDPOINT_MAPPING_DECLARED',codes(r,'UNKNOWN'))
        self.assertEqual(r.status,'UNKNOWN')
        args=fixture(duration='not-a-number')
        self.assertIsNone(assess_route(**args).conditional_relation)


if __name__=='__main__':
    unittest.main()
