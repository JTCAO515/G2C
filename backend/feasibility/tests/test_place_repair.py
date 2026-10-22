"""Real fixed-80ba parser -> consumer time integration; no injected OK outcomes."""
from datetime import datetime
import unittest

from cj_place import Outcome
from cj_feasibility.routes import PLACE_COMMIT, assess_route
from test_route_offsets import NY, at_fold, rebound
from test_validator import codes


class RepairedPlaceConsumptionTests(unittest.TestCase):
    def test_fixed_pin(self):
        self.assertEqual(PLACE_COMMIT,'80ba4ae5527875ce375d22f3439f8e3256e2c4d6')

    def test_real_age_across_fall_fold_is_stale_and_withheld(self):
        args = rebound(at_fold(0),at_fold(1,1),at_fold(1,2),consumer_boundary=False)
        self.assertEqual(args['result'].outcome,Outcome.STALE)
        self.assertEqual(args['result'].source.query_started_at.fold,0)
        self.assertEqual(args['result'].source.received_at.fold,1)
        r=assess_route(**args)
        self.assertIn('ROUTE_RESULT_UNAVAILABLE',codes(r))
        self.assertNotIn('ROUTE_QUERY_AGE_CHECKED',codes(r))
        self.assertIsNone(r.conditional_relation)

    def test_real_fold_deadline_exceeded_does_not_release_route(self):
        args=rebound(at_fold(0),at_fold(1,1),at_fold(1,2),max_age=4000,consumer_boundary=False)
        # Re-evaluate the original envelope with a stricter explicit timeout.
        from dataclasses import replace
        from cj_place import Response, parse_response, prepare
        from test_validator import encode
        config=replace(args['config'],timeout_seconds=3)
        request=prepare(config,args['window'].query,'synthetic-fold-deadline',at_fold(0))
        body=encode({'status':'1','infocode':'10000','info':'OK','count':'1',
                     'route':{'origin':request.query.origin.coordinate.raw,'destination':request.query.destination.coordinate.raw,
                              'paths':[{'distance':'1000','duration':'3600'}]}})
        result=parse_response(config,request,Response(request.binding_digest,request.origin,request.path,200,body,at_fold(1,1)),
                              now=at_fold(1,2),evidence='synthetic')
        self.assertEqual(result.outcome,Outcome.UNKNOWN)
        self.assertEqual(result.reason,'response_deadline_exceeded')
        args.update(config=config,request=request,result=result)
        r=assess_route(**args)
        self.assertNotIn('ROUTE_QUERY_AGE_CHECKED',codes(r))
        self.assertIsNone(r.conditional_relation)

    def test_real_fold_receipt_before_query_invalid_and_withheld(self):
        args=rebound(at_fold(1),at_fold(0,minute=31),at_fold(1,minute=32),max_age=4000,consumer_boundary=False)
        self.assertEqual(args['result'].outcome,Outcome.INVALID_RESPONSE)
        r=assess_route(**args)
        self.assertNotIn('ROUTE_QUERY_AGE_CHECKED',codes(r))
        self.assertIsNone(r.conditional_relation)

    def test_spring_wall_jump_does_not_expire_a_two_second_response(self):
        start=datetime(2026,3,8,1,59,59,tzinfo=NY)
        receive=datetime(2026,3,8,3,0,0,tzinfo=NY)
        now=datetime(2026,3,8,3,0,1,tzinfo=NY)
        args=rebound(start,receive,now,consumer_boundary=False)
        self.assertEqual(args['result'].outcome,Outcome.OK)
        r=assess_route(**args)
        age=next(dict(c.details)['query_age_seconds'] for c in r.checks if c.code=='ROUTE_QUERY_AGE_CHECKED')
        self.assertEqual(age,'2')
        self.assertEqual(r.status,'UNKNOWN')
        self.assertIsNotNone(r.conditional_relation)
        self.assertIs(r.result.source,args['result'].source)

    def test_valid_fall_fold_keeps_source_identity_and_utc_association(self):
        args=rebound(at_fold(1),at_fold(1,1),at_fold(1,2),consumer_boundary=False)
        self.assertEqual(args['result'].outcome,Outcome.OK)
        r=assess_route(**args)
        self.assertIs(r.result.source,args['result'].source)
        self.assertEqual(r.result.source.query_started_at.fold,1)
        self.assertIn('ROUTE_QUERY_AGE_CHECKED',codes(r))
        self.assertNotIn('ROUTE_SOURCE_BINDING_UNKNOWN',codes(r))
        self.assertEqual(r.status,'UNKNOWN')


if __name__=='__main__':
    unittest.main()
