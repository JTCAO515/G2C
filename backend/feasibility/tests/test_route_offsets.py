"""Local offset/fold audit; consumes original fixed dd4 PLACE, not its repair."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json
import unittest

from cj_place import Response, parse_response, prepare
from cj_feasibility import Candidate
from cj_feasibility.routes import assess_route
from test_routes import fixture, details
from test_validator import codes, encode, event, history

NY = ZoneInfo('America/New_York')


def at_fold(fold, second=0, minute=30):
    return datetime(2026, 11, 1, 1, minute, second, tzinfo=NY, fold=fold)


def rebound(start, receive, now, *, max_age=60):
    args = fixture()
    # Candidate departure is a unique UTC wall time, not a guessed NY fold.
    fields = json.loads(args['candidate'].content)
    utc = start.astimezone(timezone.utc)
    dest = utc + timedelta(minutes=15)
    fields['fixed_items'][0]['end'] = event(utc.date().isoformat(), utc.strftime('%H:%M:%S'), 'UTC')
    fields['fixed_items'][1]['start'] = event(dest.date().isoformat(), dest.strftime('%H:%M:%S'), 'UTC')
    args['before'], args['revisions'] = history(fields)
    args['candidate'] = Candidate(args['before'].needs_id, args['before'].version, args['before'].content)
    args['config'] = replace(args['config'], max_age_seconds=max_age, timeout_seconds=4000)
    args['request'] = prepare(args['config'], args['window'].query, 'synthetic-fold-audit', start)
    body = encode({'status':'1','info':'OK','infocode':'10000','count':'1',
                   'route':{'origin':args['window'].query.origin.coordinate.raw,
                            'destination':args['window'].query.destination.coordinate.raw,
                            'paths':[{'distance':'1000','duration':'3600'}]}})
    args['result'] = parse_response(args['config'], args['request'],
                                   Response(args['request'].binding_digest,args['request'].origin,args['request'].path,
                                            200,body,receive), now=now,evidence='synthetic')
    args['as_of'] = now
    return args


class OffsetAuditTests(unittest.TestCase):
    def test_original_source_age_across_fold_uses_elapsed_utc(self):
        # dd4 parser permits 2 wall seconds; actual elapsed age is 3602 seconds.
        args = rebound(at_fold(0),at_fold(1,1),at_fold(1,2))
        self.assertIsNotNone(args['result'].source)
        r = assess_route(**args)
        self.assertIn('ROUTE_SOURCE_STALE',codes(r))
        self.assertEqual(details(r,'ROUTE_SOURCE_STALE')['query_age_seconds'],'3602')
        self.assertIsNone(r.conditional_relation)

    def test_receipt_order_across_fold_uses_elapsed_utc(self):
        # Increasing local wall labels can still put receipt before query.
        args = rebound(at_fold(1),at_fold(0,minute=31),at_fold(1,minute=32),max_age=4000)
        self.assertIsNotNone(args['result'].source)
        r = assess_route(**args)
        self.assertIn('ROUTE_SOURCE_TIME_UNKNOWN',codes(r))
        self.assertIsNone(r.conditional_relation)

    def test_source_start_different_fold_must_not_match_original_request(self):
        args = rebound(at_fold(0),at_fold(1,1),at_fold(1,2),max_age=4000)
        # Preserve original request/ref/digest but substitute a different instant.
        args['result'] = replace(args['result'],source=replace(args['result'].source,query_started_at=at_fold(1)))
        r = assess_route(**args)
        self.assertIn('ROUTE_SOURCE_BINDING_UNKNOWN',codes(r))
        self.assertNotIn('ROUTE_QUERY_AGE_CHECKED',codes(r))
        self.assertIsNone(r.conditional_relation)

    def test_fall_and_spring_unique_local_endpoints_have_real_elapsed_gap(self):
        for day, end, expected in [('2026-11-01','02:30','10800'),('2026-03-08','03:30','7200')]:
            start = datetime.fromisoformat(day+'T00:30').replace(tzinfo=NY)
            args = rebound(start,start+timedelta(seconds=1),start+timedelta(seconds=2))
            fields = json.loads(args['candidate'].content)
            fields['fixed_items'][0]['end'] = event(day,'00:30','America/New_York')
            fields['fixed_items'][1]['start'] = event(day,end,'America/New_York')
            args['before'],args['revisions'] = history(fields)
            args['candidate'] = Candidate(args['before'].needs_id,args['before'].version,args['before'].content)
            r = assess_route(**args)
            self.assertEqual(details(r)['gap_seconds'],expected)
            self.assertEqual(r.status,'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
