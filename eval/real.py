"""Single-use M4 synthetic real batch, through the original signed API/RUN/Meter.

The frozen plan is written before dispatch. Existing output is read-only: no
resume/retry of uncertain originals. Keys stay in process memory, budgets use
B's sole persistent authorization journal. No remote host or arbitrary URL.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import re
import threading
import time

import httpx
import uvicorn

from runtime import ROOT, private_database
from cases import state
from gates import POLICY
from judge import judge
from report import report, markdown
from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL
from cj_agent.worker import Outcome
from cj_api.local_app import LocalDatabase, create_local_app, ISSUER, scope_for
from cj_api.local_run_context import load_run_context
from cj_api.real_services import RealServices, RealTools
from cj_memory.typed_api import create_local_typed_app
from cj_memory.typed_local import TypedConfiguration
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_message.travel import ABI
from cj_trip.confirmation import ConfirmationSigner
from cj_usage.authorization_budget import AuthorizationBudget
import dev_auth
import local_run_context
import run_worker

STATE = Path.home() / '.local/share/g2c/m4-real-services'
NETWORK = 'development-mac-real-exits'


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def keychain(name):
    result = subprocess.run(['security', 'find-generic-password', '-s', name, '-w',
                             str(Path.home() / 'Library/Keychains/login.keychain-db')],
                            capture_output=True, text=True, timeout=20)
    if result.returncode or not result.stdout.strip():
        raise ValueError('required_authorized_keychain_item_unavailable')
    return result.stdout.strip()


@contextmanager
def tcp_app(app):
    """Measure the actual local TCP client stream, never buffered TestClient time."""
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False,
                                         lifespan='on'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() >= deadline:
            raise RuntimeError('local_TCP_server_unavailable')
        time.sleep(.01)
    try:
        with httpx.Client(base_url='http://127.0.0.1:' + str(sock.getsockname()[1]),
                          timeout=660, trust_env=False) as client:
            yield client
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()


def expect(response, evidence, name):
    evidence.setdefault('http', []).append(dict(name=name, status=response.status_code,
                                               body=response.json()))
    if response.status_code != 200:
        raise RuntimeError('signed_API_rejected_' + name)
    return response.json()


def post(client, path, body, headers, evidence, name):
    return expect(client.post(path, content=json.dumps(body, ensure_ascii=False).encode(),
                              headers=headers), evidence, name)


def body_available(text):
    # Source URLs/tool metadata are not first answer-body content.
    return any(line.strip() and not line.startswith(('Source: ', '来源：'))
               for line in text.splitlines())


def stream_run(client, headers, mid, future, started, evidence):
    """Original protected v2 snapshot, with a measured 200ms client poll interval.

    The frozen v1 SSE reader cannot consume MESSAGE-send.2 travel context. The
    first observed body is a conservative client-time upper bound, including
    polling/read overhead; source-only output is excluded.
    """
    events = []
    evidence['events'] = events
    first = None
    terminal = None
    text = ''
    deadline = time.monotonic() + 660
    while time.monotonic() < deadline:
        response = client.get('/v2/run-display', params={'message_id': mid}, headers=headers)
        if response.status_code != 200:
            events.append(dict(http_status=response.status_code,
                               client_seconds=time.monotonic()-started, data=response.json()))
            # The accepted message can precede creation of its RUN record.
            # Only repeat this safe read; never resubmit the original message.
            if response.status_code == 503 and not future.done():
                time.sleep(.2)
                continue
            raise RuntimeError('signed_API_display_rejected')
        elapsed = time.monotonic() - started
        data = response.json()['snapshot']
        if not events or events[-1].get('http_status') or events[-1]['data'] != data:
            events.append(dict(data=data, client_seconds=elapsed))
        text = data['text']
        if first is None and body_available(text):
            first = elapsed
        if data['status'] in ('completed', 'failed', 'unknown', 'cancelled', 'context_invalid'):
            terminal = elapsed
            break
        time.sleep(.2)
    outcomes = future.result(timeout=660)
    return events, text, first, terminal, outcomes


def memory_document(subject, kind, travels):
    collection = dict(version='local-memory-typed.1', collection=dict(
        version='local-memory-policy.1',
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
        profiles={subject: dict(subjects=['self'], slots={'eval-slot': dict(
            kind=kind, collection_allowed=True, semantic_resolved=True)},
            extents=['long_term', 'current'], context_ids=[])}),
        travel_contexts={subject: [v['id'] for v in travels]})
    return dict(version='local-memory-run.2', collection=collection,
                selections={subject: dict(subject='self', slots=['eval-slot'], max_bytes=32768)})


def original_operations(database, subject):
    with database.connect(scope_for(ISSUER, subject)) as conn:
        rows = conn.execute('SELECT run_id,operation_key,registration_id,attempt_id,input_bytes '
                            'FROM cj_run_metered_operation ORDER BY run_id,operation_key').fetchall()
    return [dict(run_id=r, operation_key=k, registration_id=g, attempt_id=a,
                 input=json.loads(bytes(b))) for r,k,g,a,b in rows]


def run_case(client, database, conninfo, auth, context, services, scenario, language, subject, evidence, *, allowed_native=None):
    headers = {'Authorization': 'Bearer ' + dev_auth.token(auth, subject, 30),
               'Content-Type': 'application/octet-stream'}
    recipe = scenario['recipe']
    memory = recipe.startswith('memory-')
    travels = []
    for label in ('a', 'b') if memory else ():
        value = post(client, '/v1/travel-context-actions', dict(version='TRAVEL-context-action.1',
            action_id=label + '-' + subject, operation='create', travel_context=None), headers,
            evidence, 'travel-' + label)
        travels.append(value['receipt']['travel_context'])
    configuration = None
    memory_app = None
    expected = {}
    if memory:
        document = memory_document(subject, scenario.get('memory_kind', 'preference'), travels)
        configuration = TypedRuntimeConfiguration.from_bytes(json.dumps(document).encode())
        memory_app = create_local_typed_app(conninfo_path=conninfo, auth_dir=auth,
            configuration=TypedConfiguration.from_bytes(json.dumps(document['collection']).encode()))
    # The signed app paths and original worker are the same as B's official host.
    def send(cid, mid, text, intent='none', selected=None):
        head = expect(client.put('/v1/conversations', params={'conversation_id': cid},
                                 headers=headers), evidence, 'conversation')
        needs = None
        if intent == 'consider_trip':
            result = post(client, '/v1/needs-actions', dict(action_id='needs-' + mid,
                needs_id=mid, expected_version=0, source=dict(kind='manual', text=text),
                changes=dict(party_size=dict(state='unknown'))), headers, evidence, 'needs')
            needs = dict(id=mid, expected_version=result['receipt']['version'])
        body = dict(version='MESSAGE-send.2', conversation_id=cid, message_id=mid,
            text=text, trip_id=None, creation_intent=intent,
            expected_generation=head['generation'], expected_sequence=head['last_sequence'],
            travel_context=None if selected is None else dict(id=selected['id'], expected_version=selected['version']),
            needs_reference=needs)
        return post(client, '/v2/messages', body, headers, evidence, 'message')['receipt']

    tools = RealTools(services) if allowed_native is None else RealTools(services, allowed_native=allowed_native)
    def work():
        return run_worker.run_once(database, services.model, auth, memory_configuration=configuration,
                                   tools_configuration=tools, real_services=services)

    cid = subject
    if memory:
        # Preserve the baseline/model call that belongs to the original #497 recipe.
        send(cid, subject + '-baseline', '合成基线' if language == 'zh' else 'Synthetic baseline')
        evidence['baseline_outcomes'] = [o.__dict__ for o in work()]
        from fastapi.testclient import TestClient
        with TestClient(memory_app) as api:
            text = scenario['memory_' + language]
            command = dict(version='MEMORY-manual.2', operation_id=subject + '-save', item_id=subject + '-memory',
                subject='self', slot='eval-slot', kind=scenario.get('memory_kind', 'preference'), text=text,
                extent='long_term', context=None, occurred_at='date unknown')
            saved = post(api, '/v2/memories', command, headers, evidence, 'memory-save')
            iid = saved['receipt']['item_id']
            status = 'active'
            if recipe in ('memory-edit', 'memory-pause'):
                changed = dict(version='MEMORY-management.2', action_id=subject + '-change',
                    operation='edit' if recipe == 'memory-edit' else 'pause', item_id=iid,
                    expected_version=1, expected_source_version=1)
                if recipe == 'memory-edit':
                    text = '我喜欢紧凑安排' if language == 'zh' else 'I prefer a packed schedule'
                    changed.update(text=text, context=None)
                else:
                    status = 'disabled'
                post(api, '/v2/memory-management-actions', changed, headers, evidence, 'memory-change')
            if recipe == 'memory-stop':
                item = expect(api.get('/v2/memory-items', params={'item_id': iid}, headers=headers),
                              evidence, 'memory-source')['item']
                post(api, '/v2/memory-withdrawal-actions', dict(version='MEMORY-STOP-USE@2',
                    action_id=subject + '-stop', operation='withdraw', item_id=iid, expected_version=1,
                    source_id=item['command']['source_id'], expected_source_version=1),
                    headers, evidence, 'memory-stop')
                status = 'withdrawn'
            expected = dict(memory_kind=command['kind'], memory_item_count=1, memory_status=status,
                memory_text=text, memory_texts=[] if status in ('disabled', 'withdrawn') else [text])
    if recipe in ('memory-new-chat', 'memory-restart'):
        cid += '-new'
    if recipe == 'memory-restart':
        policy_path = conninfo.parent / (subject + '-memory.json')
        save(policy_path, document)
        evidence['restart_scope'] = 'new original real worker process; same persistent PG/API/journal'
        def work():
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'eval/real_worker.py'),
                str(conninfo), str(auth), str(conninfo.parent / 'run.json'), str(policy_path)],
                capture_output=True, text=True, timeout=660, check=True)
            return [Outcome(**value) for value in json.loads(result.stdout)]
    mid = subject + '-task'
    started = time.monotonic()
    receipt = send(cid, mid, scenario['inputs'][language],
        intent='consider_trip' if recipe in ('preview', 'accept', 'reject') else 'none',
        selected=travels[1] if recipe == 'memory-other-travel' else None)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(work)
        events, answer, first, terminal, outcomes = stream_run(client, headers, mid, future, started, evidence)
    evidence.update(events=events, answer=answer, outcomes=[o.__dict__ for o in outcomes])
    evidence['time_to_terminal_seconds'] = terminal
    current = next(o for o in outcomes if o.message_id == mid)
    observed = dict(message_receipt=receipt, run_status=current.status)
    if current.proposal_id is not None:
        candidate = expect(client.get('/v1/trip-proposals', params={'proposal_id': current.proposal_id},
            headers=headers), evidence, 'proposal')['proposal']
        observed.update(candidate_document=candidate['document'],
            candidate_content_sha256=sha256(base64.b64decode(candidate['content_utf8_base64'])).hexdigest())
        terminal = time.monotonic() - started
        if recipe in ('accept', 'reject'):
            confirmation = expect(client.post('/v1/trip-confirmations', json=dict(action_id=subject + '-action',
                kind=recipe, proposal_id=candidate['proposal_id'], candidate_hash=candidate['candidate_hash']),
                headers={'Authorization': headers['Authorization']}), evidence, 'confirmation')
            raw = base64.b64decode(confirmation['action_utf8_base64'])
            observed['action_receipt'] = expect(client.post('/v1/trip-actions', content=raw,
                headers=headers), evidence, 'trip-action')['receipt']
    if memory:
        with TestClient(memory_app) as api:
            item = expect(api.get('/v2/memory-items', params={'item_id': iid}, headers=headers),
                evidence, 'memory-final')['item']
        observed.update(memory_status=item['status'], memory_text=item['command']['text'],
                        memory_kind=item['command']['kind'])
    scope = scope_for(ISSUER, subject)
    observed.update(state(database, scope))
    evidence['operations'] = original_operations(database, subject)
    # Inputs from the original persisted registration, not from model self-report.
    observed['provider_inputs'] = [v['input']['messages'] for v in evidence['operations']
        if v['run_id'] == receipt['run_id'] and v['registration_id'].startswith('model.')]
    artifact_complete = recipe not in ('preview','accept','reject') or 'candidate_document' in observed
    return observed, expected, first, terminal if current.status == 'completed' and artifact_complete else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--batch-id', default='round2-full')
    parser.add_argument('--smoke', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        print('READ_ONLY: existing batch; no dispatch or retry')
        return 0
    from real_phase import claimed
    if claimed('full'):
        print('READ_ONLY: canonical full phase already claimed; no dispatch/retry');return 0
    if os.environ.get('CJ_M4_SYNTHETIC_ONLY') != '1':
        parser.error('explicit CJ_M4_SYNTHETIC_ONLY=1 required')
    if re.fullmatch('[a-z0-9-]{1,24}', args.batch_id) is None:
        parser.error('bounded synthetic batch identifier required')
    os.environ['CJ_ENV'] = 'local'
    raw = Path(__file__).with_name('scenarios.json').read_bytes()
    scenarios = json.loads(raw)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    from smoke import require_full_ready
    require_full_ready(args.smoke, commit)
    from real_budget import estimate, verified_journal, stop_reached
    from real_phase import claim
    before = verified_journal()
    forecast = estimate(before, include_smoke=False)
    if not forecast['within_authorization']:
        raise ValueError('full_batch_estimate_exceeds_authorization_report_495_before_dispatch')
    model_key=keychain('g2c-dashscope');amap_key=keychain('g2c-amap-web-key')
    if not claim('full',args.output,commit):
        print('READ_ONLY: canonical full phase already claimed; no request/retry');return 0
    budget = AuthorizationBudget(STATE)
    budget.check_date();verified_journal()
    plan = dict(schema_version=1, sample_set_id='g2c-m4-synthetic-33',
        sample_set_version='2:' + sha256(raw).hexdigest(), evidence_layer='real',
        provenance='Original fixed33/11; synthetic only, no tuning of prompts, model, holdout or judges.',
        collector_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), approved_thresholds=dict(POLICY), attempts=[1],
        batch_id=args.batch_id, smoke_evidence_sha256=sha256((args.smoke/'summary.json').read_bytes()).hexdigest(),
        candidates=[dict(id=commit, commit=commit, config_version='M4 real-m4 / signed MESSAGE-send.2 / registered exit / legacy draft / typed memory',
                         model_version=M4_MODEL, source_as_of=datetime.now(timezone.utc).isoformat())],
        networks=[dict(id=NETWORK, kind='local_real_services', endpoint='loopback signed API → Beijing DashScope/authorized tools',
            client_environment='Codex development Mac; current egress, geographic target classification UNKNOWN',
            measurement=dict(kind='program', independent=True, outcome='PASS',
                             ref='eval/real.py:tcp_app + per-row raw client monotonic timestamps'),
            description='Actual local TCP protected v2 snapshot polls (200ms), real external exits. Not an overseas or China target-network measurement.')],
        scenarios=scenarios)
    report(plan, [])
    args.output.mkdir(parents=True, mode=0o700)
    (args.output / 'raw').mkdir(mode=0o700)
    save(args.output / 'plan.json', plan)
    save(args.output / 'budget-before.json', before)
    save(args.output / 'preflight-estimate.json', forecast)
    save(args.output / 'packages.json', {v: version(v) for v in ('httpx','psycopg','uvicorn','fastapi')})
    subjects = frozenset('m4-synthetic-' + args.batch_id + '-' + str(i) + '-' + lang for i in range(len(scenarios)) for lang in ('zh','en'))
    model = MeteredDashScopeProvider(DashScopeConfig(M4_BASE, M4_MODEL, model_key,
                                                   max_output_tokens=1024), budget)
    services = RealServices(model, amap_key, subjects)
    observations = []
    with redirect_stdout(io.StringIO()), private_database('real-evaluation') as conninfo:
        auth = conninfo.parent / 'auth'
        dev_auth.init(auth, sorted(subjects))
        now = int(time.time())
        profile = conninfo.parent / 'run.json'
        save(profile, dict(version='CJ-LOCAL-RUN@2', history=[], current=dict(meter=dict(
            unit='provider_call', budget=100, period_start=now-60, period_end=now+21600,
            max_steps=24, max_tools=12, max_output=65536, max_seconds=600),
            output_limits=dict(model=12000, tool=48000, memory=2000))))
        context = load_run_context(profile)
        for subject in subjects:
            local_run_context.provision_budget(conninfo, context, subject)
            dev_auth.activate_travel(conninfo, subject, context, ABI)
        database = LocalDatabase(conninfo, run_context=context, travel_context=True, needs_context=True)
        app = create_local_app(conninfo_path=conninfo, auth_dir=auth, run_context=context,
            travel_context=True, needs_profile='manual-v1',
            confirmation_signer=ConfirmationSigner((auth / 'trip-confirmation.key').read_bytes()))
        with tcp_app(app) as client:
            for i, scenario in enumerate(scenarios):
                for language in ('zh', 'en'):
                    key = scenario['id'] + '-' + language + '-1'
                    subject = 'm4-synthetic-' + args.batch_id + '-' + str(i) + '-' + language
                    row = dict(candidate_id=commit, scenario_id=scenario['id'], language=language,
                        network_id=NETWORK, attempt=1, purpose='holdout' if scenario['split']=='holdout' else 'evaluation',
                        attempt_source='eval/real.py signed TCP API / original B run_once / persistent authorization budget',
                        observed_at=datetime.now(timezone.utc).isoformat(), source_as_of=datetime.now(timezone.utc).isoformat(),
                        raw_evidence_ref='raw/' + key + '.json', first_body_seconds=None, full_answer_seconds=None,
                        draft_seconds=None)
                    evidence = dict(input_sha256=sha256(scenario['inputs'][language].encode()).hexdigest())
                    started = time.monotonic()
                    try:
                        observed, expected, first, terminal = run_case(client, database, conninfo, auth, context,
                            services, scenario, language, subject, evidence)
                        judgment = judge(scenario, observed, expected)
                        evidence.update(observed=observed, expected=expected, judgment=judgment)
                        artifact_missing = scenario['recipe'] in ('preview','accept','reject') and 'candidate_document' not in observed
                        evidence['requested_candidate_missing'] = artifact_missing
                        row.update(status='success' if observed['run_status']=='completed' and not artifact_missing else 'failure',
                            first_body_seconds=first, full_answer_seconds=terminal,
                            independent_judgment=judgment, serious_errors=judgment['serious_errors'],
                            judgment=dict(kind='program', independent=True, outcome=judgment['task_outcome'], ref='eval/judge.py'))
                    except Exception as error:
                        evidence.update(error_kind=type(error).__name__, execution_stage='inspect original HTTP/attempt evidence; never redispatch')
                        row.update(status='failure', serious_errors=[], judgment=dict(kind='program', independent=True,
                            outcome='FAIL', ref='eval/real.py:execution_failure'))
                    evidence['operations'] = original_operations(database, subject)
                    original_ids = {v['attempt_id'] for v in evidence['operations']}
                    attempts = [v for v in budget.inspect() if v['attempt_id'] in original_ids]
                    evidence['authorization_attempts'] = attempts
                    row.update(model_calls=sum(v['kind']=='model' for v in attempts),
                               tool_calls=sum(v['kind']!='model' for v in attempts), memory_calls=0,
                               scenario_wall_seconds=time.monotonic()-started,
                               cost=dict(complete=False, components=[
                                   dict(name='actual billed monetary receipt', amount=None, currency='CNY',
                                        source='Vendor invoice/settlement not provided', basis='unknown'),
                                   dict(name='conservative authorization hold', amount=str(sum(v['kind']!='fact' for v in attempts)),
                                        currency='CNY', source=row['raw_evidence_ref']+'#authorization_attempts', basis='reserved')]))
                    save(args.output / row['raw_evidence_ref'], evidence)
                    observations.append(row)
                    save(args.output / 'observations.json', observations)
                    save(args.output / 'budget-after.json', budget.inspect())
                    summary = report(plan, observations)
                    save(args.output / 'report.json', summary)
                    (args.output / 'report.md').write_text(markdown(summary))
                    # Progress is deliberately outside redirect_stdout, no API content or keys.
                    os.write(1, (key+' '+row['status']+' '+row['judgment']['outcome']+'\n').encode())
                    counts = {kind: sum(v['kind']==kind for v in budget.inspect()) for kind in ('model','place','route','weather','fact')}
                    if stop_reached(counts):
                        save(args.output / 'stop.json', dict(reason='authorization stop threshold', counts=counts))
                        return 2
    return int(any(v['status']=='failure' or v['judgment']['outcome']=='FAIL' for v in observations))


if __name__ == '__main__':
    raise SystemExit(main())
