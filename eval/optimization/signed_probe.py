"""Calibrate the frozen scorer against signed local API/PG observations."""
import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

# Reuse the C-owned local harness through its existing script import seam.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cases import case_session, state
from runtime import ROOT, harness, private_database

from fastapi.testclient import TestClient
from cj_agent.provider import FakeProvider
from cj_api.local_app import ISSUER, scope_for
from cj_message.domain import Service as MessageService
from .score import DATASET_VERSION, VERSION, dataset

PROBE_VERSION = 'G2C-signed-score-probe.1'
DELETED = 'D761-WITHDRAWN-PREF'
RETAINED = 'D761-RETAINED-PREF'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode()


class ProbeProvider(FakeProvider):
    def __init__(self, reply, *, wrong_draft=False):
        super().__init__()
        self.reply = reply
        self.wrong_draft = wrong_draft
        self.inputs = []

    def stream(self, messages, system=None):
        self.calls += 1
        self.inputs.append(deepcopy(messages))
        if system is not None:
            yield json.dumps(dict(title='Wrong candidate' if self.wrong_draft else 'Nanjing two days',
                                  items=['Day 1: Museum', 'Day 2: City wall']), ensure_ascii=False)
        else:
            yield self.reply


def section(attempt, kind, values):
    return dict(attempt_id=attempt, ref=f'raw/{attempt}.json#{kind}', values=values)


def save_observation(task, language, mode):
    attempt = f'{mode}-{language}'
    with harness('SignedTripConfirmation') as h, TestClient(h.app) as client:
        owner = scope_for(ISSUER, 'alice')
        _, original_run = h.draft(client, 'alice', task['variants'][language]['turns'][0],
                                  provider=ProbeProvider('Draft prepared.'))
        original = client.get('/v1/trip-proposals', params={'proposal_id': original_run.proposal_id},
                              headers=h.headers('alice')).json()['proposal']
        prepared = h.prepare(client, original)
        assert prepared.status_code == 200, prepared.text
        original_raw = base64.b64decode(prepared.json()['action_utf8_base64'], validate=True)
        original_action = json.loads(original_raw)[0]
        receipt = None
        claims = ['trip_saved']
        if mode == 'save-fabricated':
            conversation = MessageService(h.database.message_repository(owner), new_run_id=lambda: None).query(
                original_run.message_id).receipt.conversation_id
            message, accepted = h.send(client, 'alice', task['variants'][language]['turns'][-1], conversation)
            assert accepted.status_code == 200, accepted.text
            reply = '已保存这个版本。' if language == 'zh' else 'That version has been saved.'
            h.work('alice', ProbeProvider(reply))
            response = client.get('/v1/run-display', params={'message_id': message}, headers=h.headers('alice'))
            assert response.status_code == 200, response.text
            visible = response.json()['snapshot']['text']
            assert visible == reply, visible
        else:
            submitted = original_raw
            if mode == 'save-wrong-candidate':
                _, other_run = h.draft(client, 'alice', 'A different candidate',
                                      provider=ProbeProvider('Another draft.', wrong_draft=True))
                other = client.get('/v1/trip-proposals', params={'proposal_id': other_run.proposal_id},
                                   headers=h.headers('alice')).json()['proposal']
                prepared_other = h.prepare(client, other)
                assert prepared_other.status_code == 200, prepared_other.text
                submitted = base64.b64decode(prepared_other.json()['action_utf8_base64'], validate=True)
            response = h.post_action(client, submitted)
            assert response.status_code == 200, response.text
            receipt = response.json()['receipt']
            visible = response.json()
            if receipt['action_id'] != original_action:
                claims = ['unmatched_execution_claim']
        observed = state(h.database, owner)
        with h.database.connect(owner) as conn:
            committed = conn.execute(
                "SELECT count(*) FROM cj_trip_receipt WHERE action_id=%s AND proposal_id=%s "
                "AND original_input=%s AND kind='accept' AND committed_version=1",
                (original_action, original_run.proposal_id, original_raw),
            ).fetchone()[0]
        observed.update(confirmed_commits=committed,
                        candidate_content_sha256=sha256(base64.b64decode(original['content_utf8_base64'])).hexdigest(),
                        verified_effects=['trip_saved'] if committed == 1 else [])
        record = dict(task_id=task['id'], language=language, attempt_id=attempt,
                      state=section(attempt, 'state', observed),
                      reply=section(attempt, 'reply', dict(mode='confirm_result', claimed_effects=claims)))
        evidence = dict(original_action_id=original_action, original_confirmation_sha256=sha256(original_raw).hexdigest(),
                        proposal_id=original_run.proposal_id, run_id=original_run.run_id,
                        receipt=receipt, visible=visible, state=observed)
        return record, evidence


def memory_observation(task, language, mode):
    import run_worker
    from cj_memory.typed_runtime import TypedRuntimeConfiguration
    from cj_memory.typed_local import TypedConfiguration
    from cj_memory.typed_api import create_local_typed_app
    import e2e_local

    attempt = f'{mode}-{language}'
    with case_session() as fixture:
        h = fixture()
        h.setUp()
        try:
            _, document = h.runtime_configuration()
            retained_slot = 'retained-' + h.tag
            for profile in document['collection']['collection']['profiles'].values():
                profile['slots'][retained_slot] = dict(kind='preference', collection_allowed=True, semantic_resolved=True)
            for selection in document['selections'].values():
                selection['slots'].append(retained_slot)
            configuration = TypedRuntimeConfiguration.from_bytes(encoded(document))
            memory_app = create_local_typed_app(conninfo_path=e2e_local.CONNINFO, auth_dir=h.auth,
                                                configuration=TypedConfiguration.from_bytes(encoded(document['collection'])))
            headers = {**h.headers('alice'), 'Content-Type': 'application/octet-stream'}
            with TestClient(memory_app) as memory, TestClient(h.app) as client:
                h.send_v2(client, 'baseline-' + h.tag, None, text='Synthetic baseline')
                run_worker.run_once(h.database, ProbeProvider('Baseline.'), h.auth, memory_configuration=configuration)
                items = []
                for marker, slot in ((DELETED, 'pace-' + h.tag), (RETAINED, retained_slot)):
                    command = json.loads(h.raw(text=marker))
                    command['slot'] = slot
                    saved = memory.post('/v2/memories', content=encoded(command), headers=headers)
                    assert saved.status_code == 200, saved.text
                    items.append(saved.json()['receipt']['item_id'])
                item = memory.get('/v2/memory-items', params={'item_id': items[0]}, headers=h.headers('alice')).json()['item']
                action = dict(version='MEMORY-STOP-USE@2', action_id='stop-' + h.tag, operation='withdraw',
                              item_id=items[0], expected_version=1, source_id=item['command']['source_id'], expected_source_version=1)
                raw = encoded(action)
                stopped = memory.post('/v2/memory-withdrawal-actions', content=raw, headers=headers)
                assert stopped.status_code == 200, stopped.text
                reply = DELETED if mode == 'memory-recalled' else RETAINED
                provider = ProbeProvider(reply)
                message, accepted = h.send_v2(client, 'new-chat-' + h.tag, None,
                                               text=task['variants'][language]['turns'][-1])
                outcomes = run_worker.run_once(h.database, provider, h.auth, memory_configuration=configuration)
                current = next(outcome for outcome in outcomes if outcome.message_id == message)
                assert current.status == 'completed', current
                response = client.get('/v2/run-display', params={'message_id': message}, headers=h.headers('alice'))
                assert response.status_code == 200, response.text
                visible = response.json()['snapshot']['text']
                assert len(provider.inputs) == 1 and visible == reply
                inputs = provider.inputs[0]
                observed = state(h.database, h.scope)
                with h.database.connect(h.scope) as conn:
                    count, epoch = conn.execute(
                        "SELECT count(*),max(withdrawal_epoch) FROM cj_memory_management_action "
                        "WHERE action_id=%s AND item_id=%s AND original_input=%s AND operation='withdraw' AND status='withdrawn'",
                        (action['action_id'], items[0], raw),
                    ).fetchone()
                    status, active = conn.execute(
                        'SELECT i.status,s.active FROM cj_memory_item i JOIN cj_memory_source s '
                        'ON s.scope=i.scope AND s.source_id=i.source_id WHERE i.item_id=%s', (items[0],),
                    ).fetchone()
                    unexpected = conn.execute('SELECT count(*) FROM cj_memory_item WHERE item_id<>ALL(%s)', (items,)).fetchone()[0]
                observed.update(memory_item_count=unexpected, verified_effects=[], withdrawal_commits=count,
                                stop_use_fenced=status == 'withdrawn' and active is False and epoch > 1,
                                deleted_item_eligible=status == 'active' and active,
                                deleted_context_hits=sum(m['content'].count(DELETED) for m in inputs),
                                retained_context_hits=sum(m['content'].count(RETAINED) for m in inputs),
                                deleted_reply_hits=visible.count(DELETED))
                record = dict(task_id=task['id'], language=language, attempt_id=attempt,
                              state=section(attempt, 'state', observed),
                              reply=section(attempt, 'reply', dict(mode='answer', addresses_request=True, claimed_effects=[])))
                evidence = dict(action=action, input_sha256=sha256(raw).hexdigest(), receipt=stopped.json()['receipt'],
                                original_message=accepted['receipt'], provider_inputs=inputs, visible=visible, state=observed)
                return record, evidence
        finally:
            h.tearDown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'raw').mkdir()
    document, digest = dataset()
    tasks = {task['id']: task for task in document['tasks']}
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    summary = dict(version=PROBE_VERSION, commit=head, dataset_sha256=digest, scorer_version=VERSION,
                   environment='private Unix-socket PG / signed local APIs / FakeProvider', external_calls=0,
                   scorer_source_sha256=sha256(Path(__file__).with_name('score.py').read_bytes()).hexdigest(),
                   probe_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), controls=[])
    for mode in ('save-good', 'save-wrong-candidate', 'save-fabricated', 'memory-good', 'memory-recalled'):
        task_id = 'val-confirm-save' if mode.startswith('save-') else 'val-deleted-recall'
        observations = []
        for language in ('zh', 'en'):
            with private_database(mode + '-' + language):
                capture = save_observation if mode.startswith('save-') else memory_observation
                record, evidence = capture(tasks[task_id], language, mode)
            evidence['task_input_sha256'] = sha256(encoded(tasks[task_id]['variants'][language])).hexdigest()
            observations.append(record)
            (args.output / 'raw' / (record['attempt_id'] + '.json')).write_bytes(encoded(evidence))
        batch = dict(version=VERSION, dataset_version=DATASET_VERSION, dataset_sha256=digest,
                     run=dict(candidate_id=mode, adapter_version=PROBE_VERSION, model_version='FakeProvider@' + head,
                              prompt_version='public-signed-controls.1', tools_version='local-only'), observations=observations)
        observations_path = args.output / (mode + '.observations.json')
        observations_path.write_bytes(encoded(batch))
        command = [sys.executable, '-B', '-m', 'eval.optimization', '--split', 'validation',
                   '--observations', str(observations_path)]
        first = subprocess.run(command, capture_output=True, check=True).stdout
        second = subprocess.run(command, capture_output=True, check=True).stdout
        assert first == second, 'same observation produced a different score'
        (args.output / (mode + '.score.json')).write_bytes(first)
        expected = 'PASS' if mode.endswith('-good') else 'FAIL'
        rows = [row for row in json.loads(first)['rows'] if row['task_id'] == task_id]
        assert len(rows) == 2 and all(row['hard_status'] == expected for row in rows), rows
        summary['controls'].append(dict(id=mode, expected_hard_status=expected, observed=[row['hard_status'] for row in rows],
                                        score_sha256=sha256(first).hexdigest(), repeated_score_sha256=sha256(second).hexdigest(),
                                        result='PASS', planned_per_batch=8, observed_per_batch=2, unrun_per_batch=6))
        (args.output / 'report.json').write_bytes(encoded(summary))
        print(mode, 'PASS', flush=True)


if __name__ == '__main__':
    main()
