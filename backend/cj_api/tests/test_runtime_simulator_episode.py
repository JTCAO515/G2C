from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from cj_api.runtime_actor import ActorSpecification
from cj_api.runtime_actor_host import ActorChoiceInvalid
from cj_api.runtime_simulator_episode import EpisodeLinks, SimulatorActorBridge, SimulatorDutBridge
from cj_run.core import Binding
from cj_strict_json import compact
from runtime_adapter import Binding as Owner
from runtime_adapter.contract import Unavailable

ROOT=Path(__file__).resolve().parents[3]


class EpisodeBridgeTest(unittest.TestCase):
    def setUp(self):
        from eval.lio_simulated_user.core import SIMULATOR_SYSTEM, actor_output_schema, render_choice, InputError
        from eval.lio_simulated_user.runner import HostUnavailable
        self.InputError,self.HostUnavailable=InputError,HostUnavailable
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name);self.directory.chmod(0o700)
        card=compact(dict(code_sha='a'*40,image_digest='sha256:'+'b'*64,model={}))
        self.spec=ActorSpecification((ROOT/'eval/lio_simulated_user/profiles.v1.json').read_bytes(),SIMULATOR_SYSTEM,compact(actor_output_schema(),sort_keys=True),card)
        profile=json.loads(self.spec.dataset)['profiles'][0];self.profile=profile
        source=dict(message_id='current-dut',observer_ref='native-source',conversation_id='native-cid',generation='native-generation')
        argument=SimpleNamespace(binding=Binding('owner','actor-chat','actor-generation','actor-'+'d'*64,'actor-run',1),specification=self.spec,source=compact(source),profile_id=profile['id'],attempt=1,round=1,original=lambda:b'actual-canonical-actor-input')
        original=SimpleNamespace(argument=argument)
        choice=dict(answers=['interests'],action='continue')
        self.actor=SimpleNamespace(specification=self.spec,profile_id=profile['id'],originals=[original],choose=lambda messages:choice)
        self.releases=[]
        self.dut=SimpleNamespace(latest='current-dut',last_observation=dict(questions=[dict(factor='interests',start=0,end=1)],questions_complete=True,observation_ref='native-source'),originals=[{}],specification=SimpleNamespace(message_ids=('first','second')),release=lambda text,link:self.releases.append((text,link)))
        self.links=EpisodeLinks(self.directory,Owner('owner','c'*64,'journal','producer'),self.spec,guard=lambda**kw:None)
        self.bridge=SimulatorActorBridge(self.actor,self.dut,self.links,render_choice,InputError,HostUnavailable)

    def test_exact_renderer_release_is_bound_to_native_actor_and_next_dut(self):
        choice=self.bridge.choose([]);self.assertEqual(choice['answers'],['interests'])
        text,link=self.releases[0];self.assertEqual(text,self.profile['hidden_answers']['interests']['text'])
        self.assertEqual(link['rendered_text_sha256'],sha256(text.encode()).hexdigest())
        body=json.loads(next(self.directory.glob('episode-link-*')).read_bytes())
        self.assertEqual(body['next_message_id'],'second');self.assertEqual(body['dut_source']['message_id'],'current-dut')
        self.assertNotIn('hidden_answers',json.dumps(body));self.assertNotIn('messages',body)
        self.assertEqual(body['link']['actor_input_sha256'],sha256(b'actual-canonical-actor-input').hexdigest())

    def test_expected_actor_error_maps_without_dropping_original(self):
        def invalid(messages):raise ActorChoiceInvalid('paid response invalid')
        self.actor.choose=invalid
        with self.assertRaises(self.InputError):self.bridge.choose([])
        self.assertEqual(len(self.actor.originals),1);self.assertEqual(self.releases,[])
        def unknown(messages):raise Unavailable('ORIGINAL_PROVIDER_UNKNOWN')
        self.actor.choose=unknown
        with self.assertRaises(self.HostUnavailable):self.bridge.choose([])
        self.assertEqual(len(self.actor.originals),1)

    def test_programming_error_propagates_and_wrong_source_never_releases(self):
        def broken(messages):raise TypeError('internal programming error')
        self.actor.choose=broken
        with self.assertRaises(TypeError):self.bridge.choose([])
        self.actor.choose=lambda messages:dict(answers=['interests'],action='continue')
        self.dut.latest='another-source'
        with self.assertRaises(self.HostUnavailable):self.bridge.choose([])
        self.assertEqual(self.releases,[])

    def test_paid_schema_valid_but_behavior_invalid_choice_never_releases(self):
        self.actor.choose=lambda messages:dict(answers=[],action='direct')
        with self.assertRaises(self.InputError):self.bridge.choose([])
        self.assertEqual(self.releases,[]);self.assertEqual(len(self.actor.originals),1)

    def test_stale_observation_cannot_bind_a_new_native_actor(self):
        self.dut.last_observation['observation_ref']='previous-dut-source'
        with self.assertRaises(self.HostUnavailable):self.bridge.choose([])
        self.assertEqual(self.releases,[])
        self.assertEqual(list(self.directory.glob('episode-link-*')),[])

    def test_changed_render_link_cannot_overwrite_original(self):
        self.bridge.choose([]);record=next(self.directory.glob('episode-link-*'));original=record.read_bytes()
        with self.assertRaises(Unavailable):self.links.record(self.actor.originals[0],dict(answers=['interests'],action='continue'),'changed text','second')
        self.assertEqual(record.read_bytes(),original)

    def test_dut_only_maps_operational_unavailability(self):
        def unavailable(*a,**kw):raise Unavailable('ORIGINAL_UNKNOWN')
        bridge=SimulatorDutBridge(SimpleNamespace(reply=unavailable),self.HostUnavailable)
        with self.assertRaises(self.HostUnavailable):bridge.reply('ordinary text','en',first=True)
        def bug(*a,**kw):raise ValueError('programming bug')
        bridge.dut=SimpleNamespace(reply=bug)
        with self.assertRaises(ValueError):bridge.reply('ordinary text','en',first=True)


if __name__=='__main__':unittest.main()
