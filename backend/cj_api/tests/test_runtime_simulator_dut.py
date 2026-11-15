from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from cj_api.runtime_simulator_dut import DutSpecification, DutClaims, VERSION
from cj_strict_json import compact
from runtime_adapter import Binding
from runtime_adapter.contract import Unavailable


class DutClaimsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.directory.chmod(0o700)
        self.owner = Binding('owner', 'a'*64, 'journal', 'producer')
        self.ids = ('c936-'+'1'*64, 'c936-'+'2'*64)
        self.spec = DutSpecification('episode-a', 'Plan a trip in Chengdu.', 'en', self.ids,
            compact(dict(code_sha='a'*40, image_digest='sha256:'+'b'*64, model={})))
        self.guards = []
        self.exists = set()
        @contextmanager
        def admission():yield
        self.claims = DutClaims(self.directory, self.owner, self.spec,
            guard=lambda **kwargs: self.guards.append(kwargs),
            original_exists=lambda mid: mid in self.exists, admission_lock=admission)

    def request(self, index=0):
        text = self.spec.opening if index == 0 else 'Please give me a plan now.'
        wire = dict(version='LIO-message.4', message_id=self.ids[index], text=text, locale='en')
        if index == 0:wire['new_conversation'] = True
        else:wire['conversation_id'] = 'lio-dialogue-'+'c'*32
        link = None if index == 0 else dict(version='LIO-simulator-rendered.1',
            actor_id='actor-'+'d'*64, actor_input_sha256='e'*64, choice_sha256='f'*64,
            rendered_text_sha256=sha256(text.encode()).hexdigest(), observer_ref='actual-dut-source')
        return dict(version=VERSION, step_id=self.ids[index], kind='simulator_dut',
            binding_sha256=self.owner.key, pins_sha256=self.spec.key,
            prior_step_ids=list(self.ids[:index]), native_input_utf8=compact(wire).decode(), actor_link=link)

    def test_separate_prefix_native4_plain_input_and_once_capability(self):
        value=self.request();raw=compact(value,sort_keys=True)
        self.assertNotIn('runtime-',value['step_id'])
        self.assertNotIn('hidden_answers',value['native_input_utf8'])
        prepared=self.claims.claim(raw)
        self.assertTrue(prepared.fresh)
        self.assertEqual(self.claims.consume(raw,prepared.capability),value)
        with self.assertRaises(Unavailable):self.claims.consume(raw,prepared.capability)
        self.assertFalse(self.claims.claim(raw).fresh)
        self.assertEqual(self.claims.read(self.ids[0]),raw)

    def test_continuation_binds_actual_rendered_text(self):
        value=self.request(1);raw=compact(value,sort_keys=True)
        self.assertTrue(self.claims.claim(raw).fresh)
        for fault in ('text','actor','link','prior','wire_version','extra'):
            with self.subTest(fault=fault):
                item=self.request(1)
                if fault in ('text','wire_version'):
                    wire=json.loads(item['native_input_utf8'])
                    wire['text' if fault=='text'else'version']='unreleased private text' if fault=='text'else'LIO-message.2'
                    item['native_input_utf8']=compact(wire).decode()
                elif fault=='actor':item['actor_link']['actor_id']='invented'
                elif fault=='link':item['actor_link']=None
                elif fault=='prior':item['prior_step_ids']=[]
                else:item['hidden_answers']={}
                with self.assertRaises((Unavailable,ValueError)):self.claims._request(compact(item,sort_keys=True))

    def test_unknown_claim_or_pin_change_never_mints_replacement(self):
        value=self.request();raw=compact(value,sort_keys=True);self.claims.claim(raw)
        changed=dict(value,native_input_utf8=value['native_input_utf8'].replace('Chengdu','Hangzhou'))
        with self.assertRaises(Unavailable):self.claims.claim(compact(changed,sort_keys=True))
        self.claims.pins=replace(self.spec,stage='another-stage')
        with self.assertRaises(Unavailable):self.claims.claim(raw)

    def test_existing_native_message_without_local_claim_is_query_only(self):
        self.exists.add(self.ids[0]);prepared=self.claims.claim(compact(self.request(),sort_keys=True))
        self.assertFalse(prepared.fresh)
        self.assertEqual(list(self.directory.iterdir()),[])

    def test_specification_rejects_legacy_namespace_and_mutable_plan(self):
        with self.assertRaises(ValueError):replace(self.spec,message_ids=('runtime-'+'0'*64,))
        with self.assertRaises(ValueError):replace(self.spec,message_ids=list(self.ids))
        with self.assertRaises(ValueError):replace(self.spec,message_ids=(self.ids[0],self.ids[0]))


if __name__=='__main__':unittest.main()
