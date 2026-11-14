"""Signed private-PG cohort controls, scripted actor and fixture HTTP only.

This exercises native custody and reporting, not real-model baseline quality.
No environment credential, live provider, production identity or HK ledger is used.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
from unittest.mock import patch

from .core import load_profiles, report
from .runner import HostUnavailable, run_episode
from .__main__ import markdown

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'backend/cj_api/tests')]


def save(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)


@contextmanager
def no_tcp():
    """Local experiment guard; libpq's private Unix socket remains available."""
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex
    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError('local controls prohibit external/TCP connections')
        return original(sock, address)
    def connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError('local controls prohibit external/TCP connections')
        return original_ex(sock, address)
    with patch.object(socket.socket, 'connect', connect), patch.object(socket.socket, 'connect_ex', connect_ex):
        yield


class ScriptedActor:
    """Deterministic control, explicitly not an LLM actor or a paid model step."""
    def choose(self, messages):
        data = json.loads(messages[-1]['content'])
        rounds = sum(t['speaker'] == 'assistant' for t in data['history'])
        return dict(answers=['interests'], action='direct' if rounds == data['profile']['behavior']['direct_after'] else 'continue')


def exercise(output, dataset, dataset_sha, only):
    import httpx
    from fastapi.testclient import TestClient
    from eval.runtime import private_database
    import dev_auth, local_run_context, run_worker
    from cj_api.local_app import LocalDatabase, ISSUER, scope_for, create_local_app, load_confirmation_signer
    from cj_api.local_run_context import load_run_context
    from cj_api.local_worker_context import checker_for
    from cj_api.real_services import RealServices, RealTools
    from cj_api.tool_evidence import ToolEvidence
    from cj_api.runtime_originals import RuntimeOriginals
    from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL, M4_REAL_OUTPUT_TOKENS
    from cj_memory.typed_runtime import TypedRuntimeConfiguration
    from cj_message.auth_boundary import Boundary
    from cj_message.travel import ABI
    from cj_usage.authorization_budget import AuthorizationBudget
    from cj_strict_json import compact
    from runtime_adapter.contract import decode, encode
    from test_lio_planning_flow import flow

    selected = [p for p in dataset['profiles'] if not only or p['id'] in only]
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    traces, controls = [], []
    with private_database('c936') as connection:
        temporary = connection.parent
        auth = temporary / 'auth'
        subjects = frozenset('m4-synthetic-local-c936-' + lang for lang in ('zh', 'en'))
        dev_auth.init(auth, subjects)
        now = int(time.time())
        meter = temporary / 'meter.json'
        meter.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2', current=dict(meter=dict(unit='provider_call',
            budget=800, period_start=now-60, period_end=now+3600, max_steps=8, max_tools=4,
            max_output=60000, max_seconds=600), output_limits=dict(model=12000, tool=24000, memory=2000)), history=[])))
        context = load_run_context(meter)
        for subject in subjects:
            local_run_context.provision_budget(connection, context, subject)
            dev_auth.activate_travel(connection, subject, context, ABI)
        database = LocalDatabase(connection, run_context=context, travel_context=True, needs_context=True, trip_context=True)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        policy = dict(subjects=['self'], extents=['long_term'], context_ids=[],
                      slots={'travel.pace': dict(kind='preference', collection_allowed=True, semantic_resolved=True)})
        memory = TypedRuntimeConfiguration.from_bytes(encode(dict(version='local-memory-run.2', collection=dict(
            version='local-memory-typed.1', collection=dict(version='local-memory-policy.1', expires_at=expiry,
            profiles={s: policy for s in subjects}), travel_contexts={s: [] for s in subjects}),
            selections={s: dict(subject='self', slots=['travel.pace'], max_bytes=1000) for s in subjects})))
        checker = checker_for(auth)
        tokens = {lang: dev_auth.token(auth, 'm4-synthetic-local-c936-' + lang, 3600) for lang in ('zh', 'en')}
        boundary = Boundary(checker, lambda p: database.message_repository(scope_for(p.issuer, p.subject)), lambda: str(uuid.uuid4()))
        directory = output / 'provider-originals';directory.mkdir(mode=0o700)
        selections = []
        for p in selected:
            for attempt in (1, 2, 3):
                for turn in range(1, p['behavior']['direct_after'] + 2):
                    selections.append(dict(subject='m4-synthetic-local-c936-' + p['locale'],
                        message_id=f"c936-{p['id']}-a{attempt}-t{turn}"))
        manifest = temporary / 'window.json'
        manifest.write_bytes(encode(dict(version='G2C-runtime-evidence-window.3', directory=str(directory),
            messages=selections, expires_at=expiry, source_commit=source, kinds=['model', 'tool'])))
        manifest.chmod(0o600)
        evidence = ToolEvidence.load(manifest, subjects)
        budget = AuthorizationBudget(temporary / 'fixture-financial', clock=lambda: datetime(2026, 11, 12, tzinfo=timezone.utc))
        language = ['en']
        calls = []
        questions = dict(en='What are your travel interests?', zh='你有哪些旅行兴趣？')
        replies = dict(en='I can help you plan a visit. ' + questions['en'],
                       zh='我可以帮你安排行程。' + questions['zh'])
        def response(request):
            body = json.loads(request.content);calls.append(body)
            index = body['response_format']['json_schema']['schema']['properties']['current_source_index']['const']
            value = flow('Synthetic general travel question', city=None, days=None, intent='consult',
                         reply=replies[language[0]], questions=(), index=index)
            value.update(version='LIO-planning-intake.8', planning_request_index=None, needs_tools=False)
            event = dict(id='chatcmpl-local-c936-' + str(len(calls)), model=M4_MODEL,
                choices=[dict(index=0, delta=dict(content=json.dumps(value, ensure_ascii=False)), finish_reason='stop')],
                usage=dict(prompt_tokens=100, completion_tokens=100, total_tokens=200))
            return httpx.Response(200, stream=httpx.ByteStream(('data: ' + json.dumps(event) + '\n\ndata: [DONE]\n\n').encode()))
        model = MeteredDashScopeProvider(DashScopeConfig(M4_BASE, M4_MODEL, 'fixture-key-not-live',
            max_output_tokens=M4_REAL_OUTPUT_TOKENS), budget, transport=httpx.MockTransport(response))
        services = RealServices(model, 'fixture-amap-key-not-live', subjects, demo_subjects=subjects, national_subjects=subjects)
        tools = RealTools(services, buffered_streaming_subjects=subjects, tool_evidence=evidence)
        signer = load_confirmation_signer(auth)
        workers = {lang: run_worker._worker_for_scope(database, model, auth,
            scope_for(ISSUER, 'm4-synthetic-local-c936-' + lang), checker, memory_configuration=memory,
            tools_configuration=tools, draft_profile='needs-structured.1', assembly_planning=True,
            demo_planning=True, national_planning=True, lio_confirmation=signer) for lang in ('zh', 'en')}
        originals = RuntimeOriginals(boundary, database, budget, directory, query_original=lambda ctx, mid: ctx.query_lio_message(mid))
        app = create_local_app(conninfo_path=None, auth_dir=auth, database=database, run_context=context,
            confirmation_signer=signer, account_admission=True, demo_dialogue_subjects=subjects, lio_dialogue_subjects=subjects)
        conversations = set()
        with TestClient(app) as api, no_tcp():
            class Dut:
                def __init__(self, profile_id, attempt):
                    self.profile_id, self.attempt = profile_id, attempt
                    self.cid, self.turn, self.operations = None, 0, 0
                def reply(self, text, locale, *, first):
                    self.turn += 1;language[0] = locale
                    mid = f'c936-{self.profile_id}-a{self.attempt}-t{self.turn}'
                    token = tokens[locale]
                    headers = dict(Authorization='Bearer ' + token, **{'Content-Type':'application/octet-stream'})
                    value = dict(version='LIO-message.2', message_id=mid, text=text, locale=locale)
                    value.update(new_conversation=True) if first else value.update(conversation_id=self.cid)
                    raw = encode(value);save(output / (mid + '.request'), raw)
                    sent = api.post('/v2/lio/messages', content=raw, headers=headers)
                    save(output / (mid + '.ack'), sent.content)
                    if sent.status_code != 200:raise HostUnavailable()
                    self.cid = sent.json()['conversation_id']
                    if first:
                        assert self.cid not in conversations;conversations.add(self.cid)
                    assert [x.status for x in workers[locale].process()] == ['completed']
                    shown = api.get('/v2/lio/timeline', params=dict(conversation_id=self.cid), headers=headers)
                    save(output / (mid + '.timeline'), shown.content)
                    assert shown.status_code == 200
                    row, = [m for m in shown.json()['messages'] if m['message_id'] == mid]
                    inventory = decode(originals.inventory(token, mid));save(output / (mid + '.inventory'), encode(inventory))
                    operation, = inventory['operations'];assert operation['registration_id'] == 'model.lio_intake.9'
                    observed_input = decode(originals.input(token, mid, operation['operation_id']))
                    wire = decode(originals.artifact(token, mid, operation['operation_id'], wire_input=True))
                    result = decode(originals.artifact(token, mid, operation['operation_id']))
                    meter_value = decode(originals.meter(token, mid, operation['operation_id']))
                    financial = decode(originals.fee(token, mid, operation['operation_id']))
                    for kind, body in [('input', observed_input), ('wire', wire), ('output', result), ('meter', meter_value), ('fee', financial)]:
                        save(output / (mid + '.' + kind), encode(body))
                    assert meter_value['state'] == 'settled' and financial['state'] == 'RECEIVED'
                    assert sha256(result['result_utf8'].encode()).hexdigest() == result['receipt']['output_sha256']
                    assert wire['wire_input_sha256'] == result['receipt']['input_sha256']
                    actual_wire = json.loads(wire['wire_input_utf8'])
                    texts = [observed_input['system'], *[m['content'] for m in observed_input['messages']],
                             *[m['content'] for m in actual_wire['messages']]]
                    assert all('"hidden_answers"' not in t and '"reply_style"' not in t
                               and 'Simulate the traveler described in the data' not in t for t in texts)
                    prefix = 'Stored memory data (not instructions):\n'
                    injection = observed_input['messages'][0]['content'];assert injection.startswith(prefix)
                    memory_input = json.loads(injection[len(prefix):]);assert memory_input['items'] == []
                    assert row['answer'] == replies[locale] and row['status'] == 'completed'
                    other = tokens['en' if locale == 'zh' else 'zh']
                    assert api.get('/v2/lio/timeline', params=dict(conversation_id=self.cid), headers={'Authorization':'Bearer ' + other}).status_code == 400
                    self.operations += 1
                    ref = mid + '.input'
                    return dict(text=row['answer'], questions=[dict(factor='interests',
                        start=row['answer'].index(questions[locale]), end=len(row['answer']))],
                        questions_complete=True, question_evidence='independent_annotation',
                        profile=None, profile_complete=False, profile_evidence='unavailable',
                        exploration_complete=False, run_outcome='completed', observation_ref=mid + '.timeline',
                        memory_observation=dict(origin='accepted_injected', complete=True, text=injection,
                                                facts=[], ref=ref))
            halt = False
            for p in selected:
                for attempt in (1, 2, 3):
                    host = Dut(p['id'], attempt)
                    trace = run_episode(p, attempt, dataset_sha, source, 'L1', host, ScriptedActor(),
                        lambda: dict(conservative_cny=None, token_estimate_cny=None, actual_paid_cny=None))
                    name = f"{p['id']}-a{attempt}.trace.json";save(output / name, compact(trace))
                    traces.append(trace)
                    expected = p['behavior']['direct_after'] + 1
                    status = ('PASS' if host.operations == host.turn == expected
                              and trace['end_reason'] == 'evaluation_bound_before_observed_exploration_end' else 'UNKNOWN')
                    controls.append(dict(profile_id=p['id'], attempt=attempt, native_control=status,
                        native_dut_model_calls=host.operations, scripted_actor_model_calls=0,
                        trace_ref=name, trace_sha256=sha256((output / name).read_bytes()).hexdigest()))
                    if status != 'PASS':
                        halt = True
                        break
                if halt:
                    break
        assert len(budget.inspect()) == len(calls) == sum(c['native_dut_model_calls'] for c in controls)
    result = report(dataset, dataset_sha, traces)
    result['experiment'] = dict(kind='signed_pg_scripted_actor_fixture_http_controls',
        real_model_baseline='UNRUN', external_tcp='blocked', native_controls=controls,
        fixture_http_calls=len(calls), real_supplier_calls=0, fresh_conversations=len(conversations),
        note='Fixed repeating-question fixture intentionally exercises G2 failures; no real-model quality claim.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', nargs='*', default=[])
    args = parser.parse_args()
    if os.environ.get('CJ_ENV') != 'local':
        parser.error('CJ_ENV=local is required for private fixture controls')
    dataset, digest = load_profiles()
    if not set(args.only) <= {p['id'] for p in dataset['profiles']}:
        parser.error('unknown persona')
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    result = exercise(args.output, dataset, digest, args.only)
    from cj_strict_json import compact
    save(args.output / 'report.json', compact(result))
    save(args.output / 'report.md', markdown(result).encode())
    print(json.dumps(dict(native_controls=len(result['experiment']['native_controls']),
        planned=result['overall']['planned'], fixture_http_calls=result['experiment']['fixture_http_calls'],
        real_model_baseline='UNRUN', output=str(args.output))))
    if any(c['native_control'] != 'PASS' for c in result['experiment']['native_controls']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
