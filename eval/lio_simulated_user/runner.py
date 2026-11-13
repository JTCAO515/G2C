"""Inject approved hosts; this module adds no network, credential or model exit."""
from typing import Protocol
from .core import TRACE_VERSION, InputError, render_choice, simulator_messages


class HostUnavailable(Exception):
    """Original host outcome unavailable. Retain it and stop; never resend."""


class DialogueHost(Protocol):
    def reply(self, text: str, locale: str, *, first: bool) -> dict: ...


class SimulatorHost(Protocol):
    def choose(self, messages: list[dict]) -> dict: ...


def run_episode(profile, attempt, dataset_sha256, candidate, evidence_layer,
                dut: DialogueHost, simulator: SimulatorHost, original_cost):
    """One original trajectory, no retries or hidden-answer access by the DUT.

    Real hosts must enforce their own native AUTH/qualification, registered exits,
    original IDs, capture, budget and window. This is not a dispatch permit.
    The finite evaluator bound is the persona's declared exit plus one response,
    not a product limit on exploration rounds. Unfinished exploration is UNKNOWN.
    """
    history = []
    memory = None
    actor_observations = []
    stage, failure_owner = 'dut', None
    user = dict(speaker='user', text=profile['opening'], disclosures=profile['initial_disclosures'])
    outcome, end_reason = 'unknown', 'evaluation_bound_before_observed_exploration_end'
    try:
        for round_number in range(1, profile['behavior']['direct_after'] + 2):
            history.append(user)
            # Only these ordinary strings cross into the DUT host. No persona,
            # answer key, actor system or scorer annotation is passed here.
            stage = 'dut'
            assistant = dut.reply(user['text'], profile['locale'], first=round_number == 1)
            if round_number == 1:
                memory = assistant.get('memory_observation')
            history.append(dict(assistant, speaker='assistant'))
            if assistant['run_outcome'] != 'completed':
                outcome, end_reason = assistant['run_outcome'], 'native_original_not_completed'
                failure_owner = 'dut'
                break
            if assistant['exploration_complete']:
                outcome, end_reason = 'completed', 'observed_exploration_end'
                break
            if round_number > profile['behavior']['direct_after']:
                break
            public_history = [dict(speaker=t['speaker'], text=t['text']) for t in history]
            messages = simulator_messages(profile, public_history, attempt)
            observed_questions = assistant['questions'] if assistant['questions_complete'] else None
            choice, received = None, False
            stage = 'simulator'
            try:
                choice = simulator.choose(messages)
                received = True
                user = render_choice(profile, choice, observed_questions, round_number)
            except InputError:
                # Expected actor-output failure; preserve the original attempt
                # and fees without masking unrelated programming exceptions.
                actor_observations.append(dict(round=round_number, received=received,
                                               choice=choice, status='FAIL'))
                outcome, end_reason, failure_owner = 'failed', 'actor_choice_contract_failed_no_retry', 'simulator'
                break
            actor_observations.append(dict(round=round_number, received=True, choice=choice, status='PASS'))
    except HostUnavailable:
        # Native producer is responsible for the same-original reconciliation;
        # nothing here mints a replacement or calls the host again.
        outcome, end_reason = 'unknown', 'host_original_unavailable_no_retry'
        failure_owner = stage
    accounting_status = 'provided'
    try:
        cost = original_cost()
    except HostUnavailable:
        cost = dict(conservative_cny=None, token_estimate_cny=None, actual_paid_cny=None)
        accounting_status = 'UNKNOWN'
        if outcome != 'failed':
            outcome, end_reason, failure_owner = 'unknown', 'original_accounting_unavailable_no_retry', 'accounting'
    return dict(version=TRACE_VERSION, dataset_sha256=dataset_sha256,
                profile_id=profile['id'], attempt=attempt, candidate=candidate,
                evidence_layer=evidence_layer, outcome=outcome, turns=history,
                memory_observation=memory, actor_observations=actor_observations,
                cost=cost, accounting_status=accounting_status, end_reason=end_reason,
                failure_owner=failure_owner)
