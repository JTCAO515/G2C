"""Public fixed TRIP values/canonical bytes only. No DB, credentials or listener."""
import base64
import json
import unittest
from cj_trip import domain
from cj_api.trip_projection import parse_action,receipt_projection,trip_projection

class TripProjectionChecks(unittest.TestCase):
    def test_canonical_action_freezes_exact_five_fields_and_rejects_other_bytes(self):
        a=domain.Action('a1','accept','p1','a'*64,'server-confirmation')
        self.assertEqual(parse_action(a.raw(),domain),a)
        for raw in [a.raw()+b' ',json.dumps(json.loads(a.raw())).encode(),
                    b'{"owner":"caller"}',b'\xff',a.raw().replace(b'accept',b'viewed'),
                    a.raw().replace(b'a1',b'\xc3\xa9')]:
            with self.assertRaises((ValueError,UnicodeError)):parse_action(raw,domain)

    def test_required_null_then_committed_version_and_pending_facts_preserved(self):
        for kind,version in [('accept',1),('reject',None)]:
            value=receipt_projection(domain.Receipt('a1',kind,'p1','a'*64,'t1',version),domain)
            self.assertEqual(value.model_dump(mode='json')['committed_version'],version)
        for kind,version in [('accept',None),('reject',1)]:
            with self.assertRaises(ValueError):receipt_projection(domain.Receipt('a1',kind,'p1','a'*64,'t1',version),domain)
        content=domain.packed({'title':'Synthetic e\u0301 中文','items':[{'id':'item-1','text':'Synthetic pending item','verification':'pending','evidence':[]}]})
        projected=trip_projection(domain.Trip('t1',1,content),domain).model_dump(mode='json')
        self.assertEqual(base64.b64decode(projected['content_utf8_base64']),content)
        self.assertEqual(projected['document']['items'][0]['verification'],'pending')

    def test_invalid_noncanonical_private_output_not_downgraded_to_success(self):
        obj={'title':'Synthetic','items':[{'id':'item-1','text':'Synthetic','verification':'verified','evidence':[]}]}
        for raw in [domain.packed(obj),b'\xff',b'{}',domain.packed(obj)+b' ']:
            with self.assertRaises((ValueError,UnicodeError)):trip_projection(domain.Trip('t1',1,raw),domain)
