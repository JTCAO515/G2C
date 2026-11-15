"""Protocol/pins boundaries; no source qualification or dispatch permission."""
from hashlib import sha256
import json
import tempfile
from pathlib import Path
from contextlib import nullcontext
import unittest
from cj_api.runtime_simulator_baseline import BaselineDutSpecification
from cj_api.runtime_simulator_dut import DutSpecification,DutClaims
from cj_strict_json import compact
from runtime_adapter import Binding
from runtime_adapter.contract import Unavailable


class BaselineProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.path.chmod(0o700)
        args=('baseline-a','Plan a trip in China.','en',('c936-'+'1'*64,),
            compact(dict(code_sha='a'*40,image_digest='sha256:'+'b'*64,model={})))
        self.old=DutSpecification(*args);self.baseline=BaselineDutSpecification(*args)
        self.owner=Binding('owner','c'*64,'journal','producer')

    def claims(self,spec):
        return DutClaims(self.path,self.owner,spec,guard=lambda**kw:None,
            original_exists=lambda mid:False,admission_lock=nullcontext)

    def request(self,spec):
        wire=compact(dict(version=spec.wire_version,message_id=spec.message_ids[0],
            text=spec.opening,locale=spec.locale,new_conversation=True))
        return compact(dict(version=spec.claim_version,step_id=spec.message_ids[0],
            kind='simulator_dut',binding_sha256=self.owner.key,pins_sha256=spec.key,
            prior_step_ids=[],native_input_utf8=wire.decode(),actor_link=None),sort_keys=True)

    def test_old_private_version1_bytes_and_actual4_are_unchanged(self):
        expected=compact(dict(version='LIO-simulator-dut.1',stage=self.old.stage,
            opening=self.old.opening,locale='en',message_ids=list(self.old.message_ids),
            runtime_card=json.loads(self.old.runtime_card)),sort_keys=True)
        self.assertEqual(self.old.raw,expected)
        self.assertEqual(self.old.wire_version,'LIO-message.4')

    def test_new_version2_pins_actual_legacy2_separately(self):
        value=json.loads(self.baseline.raw)
        self.assertEqual(value['version'],'LIO-simulator-dut.2')
        self.assertEqual(value['wire_version'],'LIO-message.2')
        self.assertNotEqual(self.baseline.key,self.old.key)
        claims=self.claims(self.baseline);raw=self.request(self.baseline)
        prepared=claims.claim(raw);self.assertTrue(prepared.fresh)
        self.assertEqual(claims.consume(raw,prepared.capability)['version'],'LIO-simulator-dut.2')
        self.assertFalse(claims.claim(raw).fresh)

    def test_protocol_or_pins_cannot_be_relabelled_across_candidates(self):
        for spec,other in((self.old,self.baseline),(self.baseline,self.old)):
            with self.subTest(protocol=spec.wire_version):
                value=json.loads(self.request(spec));wire=json.loads(value['native_input_utf8'])
                wire['version']=other.wire_version;value['native_input_utf8']=compact(wire).decode()
                with self.assertRaises((ValueError,Unavailable)):
                    self.claims(spec)._request(compact(value,sort_keys=True))
                with self.assertRaises(Unavailable):self.claims(other)._request(self.request(spec))


if __name__=='__main__':unittest.main()
