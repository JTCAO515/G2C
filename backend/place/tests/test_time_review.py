"""Independent fixed-head negative probes; synthetic bytes only."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from cj_place import Config, ORIGIN, Outcome, Search, Response, prepare, parse_response

ZONE=ZoneInfo("America/New_York")
CONFIG=Config(ORIGIN,4096,4096,3,60)
BODY=json.dumps({"status":"1","infocode":"10000","info":"OK","count":"1","pois":[{"id":"SYNTH_A","name":"SYNTH_ONLY"}]}).encode()
START=datetime(2026,11,1,1,30,0,tzinfo=ZONE,fold=0)
QUERY=Search("SYNTHETIC","SYNTHETIC",1,1)

def parse(start,received,now):
 request=prepare(CONFIG,QUERY,"time-probe",start)
 response=Response(request.binding_digest,request.origin,request.path,200,BODY,received)
 return parse_response(CONFIG,request,response,now=now)

class IndependentTimeTests(unittest.TestCase):
 def test_fold_elapsed_must_be_unknown(self):
  received=datetime(2026,11,1,1,30,1,tzinfo=ZONE,fold=1)
  now=datetime(2026,11,1,1,30,2,tzinfo=ZONE,fold=1)
  self.assertEqual((received.astimezone(timezone.utc)-START.astimezone(timezone.utc)).total_seconds(),3601)
  result=parse(START,received,now)
  self.assertEqual(result.outcome,Outcome.UNKNOWN)
  self.assertEqual(result.places,())
 def test_fold_age_must_be_stale(self):
  received=START+timedelta(seconds=1)
  now=datetime(2026,11,1,1,30,2,tzinfo=ZONE,fold=1)
  self.assertEqual((now.astimezone(timezone.utc)-START.astimezone(timezone.utc)).total_seconds(),3602)
  result=parse(START,received,now)
  self.assertEqual(result.outcome,Outcome.STALE)
  self.assertEqual(result.places,())
 def test_fold_future_receive_must_be_invalid(self):
  # Query/receipt share fold1; observation is in the previous actual hour.
  start=datetime(2026,11,1,1,30,0,tzinfo=ZONE,fold=1)
  received=start+timedelta(seconds=1)
  # datetime timedelta arithmetic resets fold: explicitly keep the receipt in fold1.
  received=received.replace(fold=1)
  now=datetime(2026,11,1,1,30,2,tzinfo=ZONE,fold=0)
  self.assertLess(now.astimezone(timezone.utc),received.astimezone(timezone.utc))
  result=parse(start,received,now)
  self.assertEqual(result.outcome,Outcome.INVALID_RESPONSE)
  self.assertEqual(result.places,())
 def test_equivalent_utc_instants_enforce_existing_outcomes(self):
  cases=[(START,datetime(2026,11,1,1,30,1,tzinfo=ZONE,fold=1),datetime(2026,11,1,1,30,2,tzinfo=ZONE,fold=1),Outcome.UNKNOWN),
   (START,START+timedelta(seconds=1),datetime(2026,11,1,1,30,2,tzinfo=ZONE,fold=1),Outcome.STALE),
   (START.replace(fold=1),START.replace(second=1,fold=1),START.replace(second=2),Outcome.INVALID_RESPONSE)]
  for start,received,now,expected in cases:
   with self.subTest(expected=expected):
    result=parse(*(x.astimezone(timezone.utc) for x in (start,received,now)))
    self.assertEqual(result.outcome,expected)
    self.assertEqual(result.places,())
 def test_fresh_non_utc_keeps_original_source_timestamps(self):
  start=datetime(2026,10,22,12,tzinfo=ZoneInfo("Asia/Shanghai"));received=start+timedelta(seconds=1)
  result=parse(start,received,start+timedelta(seconds=2))
  self.assertEqual(result.outcome,Outcome.OK)
  self.assertEqual(result.source.query_started_at.isoformat(),start.isoformat())
  self.assertEqual(result.source.received_at.isoformat(),received.isoformat())
  self.assertEqual(result.source.evidence,"unverified_bytes")

if __name__=="__main__":unittest.main()
