"""C's real evaluator with component fixtures; no dispatch qualification."""
from hashlib import sha256
import unittest

from cj_api.runtime_actor_host import ActorChoiceInvalid
from cj_api.runtime_simulator_episode import run_native_episode
from runtime_adapter.contract import Unavailable
from eval.lio_simulated_user.core import render_choice, InputError
from eval.lio_simulated_user.runner import run_episode, HostUnavailable
import test_runtime_simulator_episode as episode_fixtures


class LocalRunnerTest(unittest.TestCase):
    def setUp(self):
        fixture = episode_fixtures.EpisodeBridgeTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        fixture.actor.attempt = 2
        self.inputs, self.cost_reads = [], []
        self.cost = dict(conservative_cny=None, token_estimate_cny=None,
                         actual_paid_cny=None)

    def original_cost(self):
        self.cost_reads.append(True)
        return self.cost

    def run_component(self):
        f = self.fixture
        return run_native_episode(f.dut, f.actor, f.links, self.original_cost,
            candidate='local-component', evidence_layer='L0',
            run_episode=run_episode, renderer=render_choice,
            input_error=InputError, host_unavailable=HostUnavailable)

    def response(self, text, locale, *, first):
        f = self.fixture
        self.inputs.append((text, locale, first))
        return dict(f.dut.last_observation, text='Fixture response',
            run_outcome='completed', exploration_complete=not first,
            profile=None, profile_complete=False, profile_evidence='unavailable',
            memory_observation=None)

    def test_exact_c_runner_binds_actor_profile_and_only_releases_ordinary_text(self):
        f = self.fixture
        f.dut.reply = self.response
        trace = self.run_component()
        self.assertEqual(trace['profile_id'], f.actor.profile_id)
        self.assertEqual(trace['attempt'], 2)
        self.assertEqual(trace['dataset_sha256'], sha256(f.spec.dataset).hexdigest())
        self.assertEqual(self.inputs, [(f.profile['opening'], f.profile['locale'], True),
            (f.profile['hidden_answers']['interests']['text'], f.profile['locale'], False)])
        self.assertEqual(len(f.releases), 1)
        self.assertEqual(trace['memory_observation'], None)
        self.assertFalse(trace['turns'][1]['profile_complete'])
        self.assertEqual(self.cost_reads, [True])
        self.assertIs(trace['cost'], self.cost)

    def test_paid_invalid_actor_preserves_original_and_reads_cost_without_replay(self):
        f = self.fixture
        f.dut.reply = self.response
        def invalid(messages):
            raise ActorChoiceInvalid('original paid response invalid')
        f.actor.choose = invalid
        trace = self.run_component()
        self.assertEqual(trace['outcome'], 'failed')
        self.assertEqual(trace['end_reason'], 'actor_choice_contract_failed_no_retry')
        self.assertEqual(len(f.actor.originals), 1)
        self.assertEqual(len(self.inputs), 1)
        self.assertEqual(f.releases, [])
        self.assertEqual(self.cost_reads, [True])

    def test_dut_unknown_does_not_call_actor_and_still_queries_original_cost(self):
        f = self.fixture
        def unknown(text, locale, *, first):
            self.inputs.append((text, locale, first))
            raise Unavailable('ORIGINAL_ADMISSION_ACK_UNKNOWN')
        def no_actor(messages):
            self.fail('actor dispatched after original DUT UNKNOWN')
        f.dut.reply, f.actor.choose = unknown, no_actor
        trace = self.run_component()
        self.assertEqual(trace['outcome'], 'unknown')
        self.assertEqual(trace['failure_owner'], 'dut')
        self.assertEqual(trace['end_reason'], 'host_original_unavailable_no_retry')
        self.assertEqual(len(self.inputs), 1)
        self.assertEqual(self.cost_reads, [True])


if __name__ == '__main__':
    unittest.main()
