"""One #167 native scenario on the formal protected local host; fresh private DB per invocation."""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BUNDLE = 'space.go2china.run.acceptance'
sys.path.insert(0, str(ROOT / 'scripts'))
CASES = ['testStreamEnglish', 'testStreamChinese', 'testStopEnglish', 'testStopChinese',
         'testFailureEnglish', 'testFailureChinese']


DRAFT_CASES = ['testDraftValidationEnglish', 'testDraftValidationChinese', 'testDraftProviderEnglish', 'testDraftProviderChinese', 'testDraftUnknownEnglish', 'testDraftUnknownChinese', 'testDraftStopEnglish', 'testDraftStopChinese', 'testDraftPublishedEnglish', 'testDraftPublishedChinese']


BUDGET_CASES = ["testAnswerBudgetEnglish", "testAnswerBudgetChinese", "testDraftBudgetEnglish", "testDraftBudgetChinese", "testUnknownEnglish", "testUnknownChinese"]

AUTH_CASES = ['testRegisteredSwitchOriginal', 'testRegisteredRevokedOriginal', 'testRegisteredExpiredOriginal']

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--build-dir', required=True, type=Path)
    parser.add_argument('--draft-status', action='store_true', help='Retained compatibility flag for older commands')
    parser.add_argument('--run-context', required=True, type=Path, help='Explicit CJ-LOCAL-RUN@1 or @2 operator file')
    parser.add_argument('--diagnostic-test', required=True, choices=CASES + DRAFT_CASES + BUDGET_CASES + AUTH_CASES + ['testReleaseClosed'])
    args = parser.parse_args()
    output, build = args.output.resolve(), args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT): raise ValueError('External evidence only')
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'report.json').exists(): raise ValueError('Preserve prior evidence')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('SIMCTL_CHILD_', 'G2C_DEV_', 'PG', 'LIBPQ'))}
    env.update(CJ_ENV='local', DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
    os.environ['CJ_ENV'] = 'local'
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], env=env))
    target = next(d for r, ds in devices['devices'].items() if 'iOS-17-5' in r for d in ds if d['udid'] == args.simulator)
    if target['state'] == 'Shutdown': subprocess.run(['xcrun', 'simctl', 'boot', args.simulator], env=env, check=True)
    subprocess.run(['xcrun', 'simctl', 'bootstatus', args.simulator, '-b'], env=env, check=True)
    sources = list((ROOT / 'ios/App').glob('*.swift')) + list((ROOT / 'ios/Modules/CJRunClient/Sources').rglob('*.swift')) + list((ROOT / 'ios/Modules/CJShell/Sources').rglob('*.swift'))
    sources += [HERE / 'DevelopmentRunUITests.swift', HERE / 'check_runs.py', HERE / 'check_run_budget.py', HERE / 'check_registered_runs.py']
    report = dict(status='RUNNING', working_tree_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)), head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        cases={}, unrun=['real tools/providers/cloud/device'], run_context=json.loads(args.run_context.read_text()),
        scope='Actual iOS17.5 App, formal local API, private PG/runtime, real worker with controlled FakeProvider; no actual tool requested',
        source_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    def save(): (output / 'report.json').write_text(json.dumps(report, indent=2))
    save()
    import psycopg
    import uvicorn
    import dev_auth
    import migrate
    from pg_suites import cluster
    from fastapi.testclient import TestClient
    from cj_api.local_app import app_from_environment, LocalDatabase, ISSUER, AUDIENCE, scope_for
    from cj_agent.provider import FakeProvider, ProviderFailed, ProviderUnknown
    from cj_agent.draft import proposal_id_for
    from cj_message.domain import Service as MessageService
    from cj_run.core import Binding, Service as RunService
    from run_worker import run_once
    from cj_api.local_run_context import load_run_context
    from cj_run.step_usage import ledger_scope_for
    from cj_usage.codec import decode, encode
    from cj_usage.core import Meter
    context = load_run_context(args.run_context)
    registered = report['run_context']['version'] == 'CJ-LOCAL-RUN@2'
    if args.diagnostic_test in AUTH_CASES and not registered:
        raise ValueError('Registered boundary cases require an explicit @2 profile')
    report['git_trees'] = {path: subprocess.check_output(['git','rev-parse',report['head']+':'+path],cwd=ROOT,text=True).strip()
                           for path in ('ios','backend','contracts','scripts')}

    with tempfile.TemporaryDirectory(prefix='cj167-', dir='/tmp') as temporary:
        root = Path(temporary)
        with cluster('runui', port=55575, role='cj167_initializer', root=root / 'pg') as config:
            with psycopg.connect(**config, autocommit=True) as conn:
                chain = migrate.load(); migrate.up(conn, chain, chain[-1]['version'])
            connection = root / 'connection.json'; connection.write_text(json.dumps(config))
            auth = root / 'auth'; subjects = {k: 'cj167-' + k + '-' + uuid.uuid4().hex[:8] for k in ('A', 'B')}
            dev_auth.init(auth, list(subjects.values()))
            tokens = {k: dev_auth.token(auth, subject, 120) for k, subject in subjects.items()}
            private_tokens = list(tokens.values())
            os.environ.update(CJ_LOCAL_CONNINFO=str(connection), CJ_LOCAL_AUTH_DIR=str(auth), CJ_LOCAL_RUN_CONTEXT=str(args.run_context.resolve()))
            env.update(CJ_LOCAL_CONNINFO=str(connection), CJ_LOCAL_AUTH_DIR=str(auth), CJ_LOCAL_RUN_CONTEXT=str(args.run_context.resolve()))
            operator_records = []
            def operator(subject, *arguments):
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/local_run_context.py'),
                    '--conninfo-json', str(connection), '--auth-dir', str(auth), '--run-context', str(args.run_context.resolve()),
                    '--subject', subject, *arguments], env=env, capture_output=True, text=True, timeout=30)
                operator_records.append(dict(subject=subject, operation=arguments[0], returncode=result.returncode,
                    stdout=result.stdout, stderr=result.stderr))
                report['operator_records'] = operator_records; save()
                result.check_returncode()
            for subject in subjects.values(): operator(subject, 'init-budget')
            app = app_from_environment(); database = LocalDatabase(connection, run_context=context)
            specs, audit, errors = {}, [], []
            responses = []
            stream_frames = []
            lock = threading.Lock(); stop = threading.Event()
            held_reads = {}

            def fixture_value(case_id):
                spec = specs[case_id]
                return dict(endpoint=endpoint, accounts=dict(tokens), subjects=subjects, conversation=case_id,
                            prompt=spec['prompt'], choice=spec['choice'])

            def access(case_id, allowed):
                subject = subjects[specs[case_id]['choice']]
                invited = list(subjects.values()) if allowed else [s for s in subjects.values() if s != subject]
                path = auth/'invited-next.json'; path.write_text(json.dumps(invited)); path.chmod(0o600)
                path.replace(auth/'invited.json')
                report.setdefault('auth_events', []).append(dict(case=case_id, allowed=allowed))
                save()

            class ControlledFake(FakeProvider):
                def stream(self, messages, system=None):
                    prompt = messages[-1]['content']
                    with lock:
                        spec = next((s for s in specs.values() if prompt in (s['prompt'], s['prompt'] + ' second') or (system is not None and s['prompt'] in prompt)), None)
                        if spec is None: raise ProviderFailed('unregistered local test input')
                        spec['calls'] += 1
                        self.calls += 1
                        if system is not None: spec['draft_calls'] += 1
                    if system is not None:
                        if spec['mode'] == 'draft_provider': raise ProviderFailed('controlled draft rejection')
                        if spec['mode'] == 'draft_unknown': raise ProviderUnknown('controlled draft unknown')
                        if spec['mode'] == 'draft_validation':
                            yield '{"title":123,"items":[]}'
                            return
                    if spec['mode'] == 'failure': raise ProviderFailed('controlled definite provider rejection')
                    if spec['mode'] == 'unknown': raise ProviderUnknown('controlled provider outcome unknown')
                    for index, chunk in enumerate(FakeProvider(chunks_per_reply=2).stream(messages, system)):
                        if index and not spec['release'].wait(90): raise ProviderFailed('local test release deadline')
                        yield chunk

            def worker():
                try:
                    model = ControlledFake()
                    while not stop.is_set():
                        run_once(database, model, auth)
                        stop.wait(.05)
                except Exception as error:
                    with lock: errors.append(type(error).__name__)
                    stop.set()
            worker_thread = threading.Thread(target=worker, daemon=True); worker_thread.start()

            async def observed(scope, receive, send):
                if scope['type'] == 'http':
                    with lock: audit.append((scope['method'], scope['path']))
                response_status = None
                async def capture_response(message):
                    nonlocal response_status
                    if message['type'] == 'http.response.start':
                        response_status = message['status']
                        with lock: responses.append((scope.get('path'), message['status']))
                    if scope.get('path') == '/v1/run-events' and message['type'] == 'http.response.body':
                        with lock: stream_frames.append(dict(message_id=parse_qs(scope.get('query_string', b'').decode()).get('message_id', [''])[0], body=message.get('body', b'').decode('utf-8')))
                    if (scope.get('path') == '/v2/run-draft-status' and response_status == 200
                            and message['type'] == 'http.response.body' and not message.get('more_body', False)):
                        original = parse_qs(scope.get('query_string', b'').decode()).get('message_id', [''])[0]
                        with lock: held = held_reads.get(original)
                        if held is not None:
                            held['captured'].set()
                            if not await asyncio.to_thread(held['release'].wait, 30):
                                raise TimeoutError('actual original read release missing')
                            await send(message); held['released'].set(); return
                    await send(message)
                await app(scope, receive, capture_response)

            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            endpoint = f'http://127.0.0.1:{port}'
            server = uvicorn.Server(uvicorn.Config(observed, host='127.0.0.1', port=port, log_level='error', access_log=False))
            api_thread = threading.Thread(target=server.run, daemon=True); api_thread.start()
            deadline = time.monotonic() + 10
            while not server.started:
                if not api_thread.is_alive() or time.monotonic() > deadline: raise RuntimeError('API startup failed')
                time.sleep(.02)

            def proof(case_id):
                with lock:
                    spec = specs[case_id]; calls = list(audit[spec['audit_start']:spec.get('audit_end')]); failures = list(errors)
                if failures: raise RuntimeError('worker failed: ' + ','.join(failures))
                scope = scope_for(ISSUER, subjects[spec['choice']])
                with database.connect(scope) as conn:
                    rows = conn.execute('SELECT message_id,raw_input,run_id FROM cj_message_receipt WHERE conversation_id=%s ORDER BY sequence', (spec['conversation'],)).fetchall()
                    pending = conn.execute('SELECT count(*) FROM cj_message_delivery WHERE NOT acknowledged').fetchone()[0]
                    role = conn.execute('SELECT current_user').fetchone()[0]
                    account = ledger_scope_for(scope, context.current.meter)
                    ledger_row = conn.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s', (account,)).fetchone()
                    ledger = decode(ledger_row[0])
                    encoded_ledger = encode(ledger)
                    fingerprint = hashlib.sha256(encoded_ledger.encode()).hexdigest()
                    originals = [dict(message_id=mid, run_id=run, sha256=hashlib.sha256(bytes(raw)).hexdigest()) for mid,raw,run in rows]
                    original_fingerprint = hashlib.sha256(json.dumps(originals,sort_keys=True).encode()).hexdigest()
                    registered_rows, registered_bindings = [], []
                    if registered:
                        profile = conn.execute('SELECT version FROM cj_local_metered_profile WHERE scope=%s',(scope,)).fetchone()
                        assert profile == ('registered-exit.1',)
                        requirements = conn.execute('SELECT q.message_id,q.run_id,q.version FROM cj_message_metered_requirement q '
                            'JOIN cj_message_receipt m ON (m.scope,m.message_id)=(q.scope,q.message_id) '
                            'WHERE m.conversation_id=%s ORDER BY q.message_id',(spec['conversation'],)).fetchall()
                        assert {(m,r) for m,r,v in requirements if v=='registered-exit.1'} == {(m,r) for m,_,r in rows}
                        registered_bindings = conn.execute('SELECT b.run_id,b.ledger_scope,b.unit,b.period_start,b.period_end,b.source_abi '
                            'FROM cj_run_metered_binding b JOIN cj_message_receipt m ON (m.scope,m.run_id)=(b.scope,b.run_id) '
                            'WHERE m.conversation_id=%s ORDER BY b.run_id',(spec['conversation'],)).fetchall()
                        for run,ledger_scope,unit,start,end,abi in registered_bindings:
                            assert (ledger_scope,unit,start,end,abi)==(account,'provider_call',context.current.meter.period_start,
                                context.current.meter.period_end,'RUN-USAGE-OPERATIONS@1')
                        operations = conn.execute('SELECT o.run_id,o.operation_key,o.registration_id,o.kind,o.attempt_id,o.operation_id,'
                            'o.ledger_scope,o.command_bytes,o.input_bytes FROM cj_run_metered_operation o '
                            'JOIN cj_message_receipt m ON (m.scope,m.run_id)=(o.scope,o.run_id) '
                            'WHERE m.conversation_id=%s ORDER BY o.run_id,o.operation_key',(spec['conversation'],)).fetchall()
                        for run,key,registration,kind,attempt,operation,ledger_scope,command_raw,input_raw in operations:
                            command_raw,input_raw=bytes(command_raw),bytes(input_raw); command=json.loads(command_raw)
                            assert (command['run_id'],command['kind'],command['attempt_id'],command['operation_id'])==(run,kind,attempt,operation)
                            assert ledger_scope==account and kind=='model' and command['reserve']==1
                            assert command['input_digest']==hashlib.sha256(input_raw).hexdigest()
                            registered_rows.append(dict(run_id=run,key=key,registration=registration,kind=kind,attempt_id=attempt,
                                operation_id=operation,ledger_scope=ledger_scope,command_sha256=hashlib.sha256(command_raw).hexdigest(),
                                input_sha256=hashlib.sha256(input_raw).hexdigest()))
                    registered_fingerprint = hashlib.sha256(json.dumps([registered_bindings,registered_rows],sort_keys=True).encode()).hexdigest() if registered else None
                status, text, effects, draft_outcome = None, '', 0, None
                pending_proposals, formal_trips, proposal_bindings = 0, 0, []
                budget_stage = 'none'
                if rows:
                    messages = MessageService(database.message_repository(scope), new_run_id=lambda: None)
                    original = messages.query(rows[-1][0]).receipt
                    runs = RunService(database.run_repository(scope), valid=lambda b: messages.query(b.message_id) is not None)
                    state = runs.snapshot(Binding(scope, original.conversation_id, original.generation, original.message_id, original.run_id, original.sequence))
                    status, text, effects, draft_outcome = state.status, state.text, len(state.effects), state.draft_outcome
                    budget_stage = state.budget_exhausted_stage
                    trips = database.trip_repository(scope)
                    for effect in state.effects:
                        if effect.startswith('trip_proposal:'):
                            identifier = effect.removeprefix('trip_proposal:')
                            detail = trips.proposal_detail(identifier)
                            pending_proposals += detail.status == 'pending'
                            formal_trips += trips.detail(detail.proposal.trip_id) is not None
                            proposal_bindings.append(identifier == detail.proposal.proposal_id == proposal_id_for(original.run_id))
                return dict(runtime_role=role, pending_deliveries=pending, ledger_fingerprint=fingerprint,
                    original_fingerprint=original_fingerprint, originals=originals,
                    registered_fingerprint=registered_fingerprint, registered_operations=len(registered_rows),registered_originals=registered_rows,
                    exposure=Meter.exposure(ledger), ledger=json.loads(encoded_ledger), ledger_attempts=len(ledger.attempts),
                    usage_receipts=sum(a.receipt is not None for a in ledger.attempts.values()),
                    tool_steps=sum(run.tools for run in ledger.runs.values()), budget_stage=budget_stage,
                    requests=len(calls), status=status, text=text, effects=effects, message_id=rows[-1][0] if rows else None,
                    draft_outcome=draft_outcome, draft_calls=spec['draft_calls'],
                    pending_proposals=pending_proposals, formal_trips=formal_trips, proposal_binding_valid=all(proposal_bindings),
                    published_effects=sum(effect.startswith('trip_proposal:') for effect in state.effects) if rows else 0,
                    creation_intent=json.loads(bytes(rows[-1][1]))['creation_intent'] if rows else None,
                    draft_reads=calls.count(('GET', '/v2/run-draft-status')),
                    receipts=len(rows), provider_calls=spec['calls'], posts=calls.count(('POST', '/v1/messages')),
                    cancellations=calls.count(('POST', '/v1/run-cancellations')),
                    forbidden_writes=sum(m not in ('GET', 'HEAD') and p not in ('/v1/messages', '/v1/run-cancellations') for m, p in calls))

            class Control(BaseHTTPRequestHandler):
                def log_message(self, *args): pass
                def do_GET(self):
                    try:
                        parsed = urlsplit(self.path); query = parse_qs(parsed.query)
                        if parsed.path == '/prepare':
                            mode, language = query['mode'][0], query['language'][0]
                            if mode not in ('normal', 'stop', 'failure', 'release', 'draft_validation', 'draft_provider', 'draft_unknown', 'draft_stop', 'draft_published', 'budget_answer', 'draft_budget', 'unknown') or language not in ('en', 'zh-Hans'): raise ValueError('invalid case')
                            choice = 'A' if language == 'en' else 'B'
                            cid = 'cj167-' + uuid.uuid4().hex
                            prompt = f'CJ167 {mode} {cid} ' + ('北京行程测试' if choice == 'B' else 'Beijing travel test')
                            with TestClient(app) as client:
                                client.put('/v1/conversations', params={'conversation_id': cid}, headers={'Authorization': 'Bearer ' + tokens[choice]}).raise_for_status()
                            if mode.startswith('draft_'):
                                needs_path = root / 'needs-input.json'
                                needs_path.write_text(json.dumps(dict(action_id='manual-' + cid, needs_id='needs-' + cid,
                                    expected_version=0, source={'kind':'manual','text':'Local operator supplied party size'},
                                    changes={'party_size':{'state':'known','value':1}})))
                                operator(subjects[choice], 'put-needs', '--input-json', str(needs_path))
                                operator(subjects[choice], 'bind-needs', '--conversation-id', cid, '--needs-id', 'needs-' + cid)
                            with lock:
                                for prior in specs.values():
                                    if 'audit_end' not in prior: prior['audit_end'] = len(audit)
                                specs[cid] = dict(conversation=cid, mode=mode, prompt=prompt, choice=choice, calls=0, draft_calls=0, release=threading.Event(), audit_start=len(audit))
                            value = dict(endpoint=endpoint, accounts=tokens, subjects=subjects, conversation=cid, prompt=prompt, choice=choice)
                        elif parsed.path == '/proof':
                            value = proof(query['case'][0])
                            if query.get('settled') == ['1']:
                                deadline = time.monotonic() + 15
                                while value['pending_deliveries'] and time.monotonic() < deadline:
                                    time.sleep(.05); value = proof(query['case'][0])
                                if value['pending_deliveries']: raise RuntimeError('original delivery did not finish')
                        elif parsed.path == '/observe-foreign-ui':
                            report.setdefault('native_foreign_account_checks', []).append(query['case'][0]); save(); value = {}
                        elif parsed.path == '/observe-read-recovery':
                            value = proof(query['case'][0])
                            with lock: frames = [f['body'] for f in stream_frames if f['message_id'] == value['message_id'] and f['body']]
                            if not frames or not ('data: {"status":"unavailable"}' in frames[-1] or 'RUN_EVENTS_UNAVAILABLE' in frames[-1]):
                                raise RuntimeError('no producer unavailable evidence for original read recovery')
                            report.setdefault('explicit_snapshot_reads', []).append(dict(message_id=value['message_id'],
                                reason='producer unavailable; root cause UNKNOWN', before=value))
                            save()
                        elif parsed.path == '/reconcile':
                            before = proof(query['case'][0])
                            result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/run_worker.py'),
                                '--conninfo-json', str(connection), '--auth-dir', str(auth),
                                '--run-context', str(args.run_context.resolve()), '--once'], env=env,
                                capture_output=True, text=True, timeout=30)
                            report.setdefault('worker_restarts', []).append(dict(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
                            save(); result.check_returncode()
                            if 'local_provider_calls=0' not in result.stdout: raise RuntimeError('original worker redispatched')
                            value = proof(query['case'][0])
                            if value['ledger_fingerprint'] != before['ledger_fingerprint']: raise RuntimeError('reconciliation changed original ledger')
                            if (value['original_fingerprint'],value['registered_fingerprint']) != (before['original_fingerprint'],before['registered_fingerprint']):
                                raise RuntimeError('reconciliation changed original IDs or bytes')
                        elif parsed.path == '/hold-original-read':
                            original = proof(query['case'][0])['message_id']
                            with lock:
                                held_reads[original] = dict(captured=threading.Event(), release=threading.Event(), released=threading.Event())
                            value = {}
                        elif parsed.path == '/wait-original-held':
                            original = proof(query['case'][0])['message_id']
                            if not held_reads[original]['captured'].wait(10): raise TimeoutError('actual v2 original response not held')
                            value = {}
                        elif parsed.path == '/release-original-read':
                            original = proof(query['case'][0])['message_id']; held = held_reads[original]
                            held['release'].set()
                            if not held['released'].wait(10): raise TimeoutError('actual original response not released')
                            report.setdefault('held_originals', []).append(original); save(); value = {}
                        elif parsed.path == '/withdraw-access':
                            access(query['case'][0],False); value = {}
                        elif parsed.path in ('/renew-short-token','/restore-identity'):
                            case_id = query['case'][0]; choice = specs[case_id]['choice']
                            if parsed.path == '/restore-identity': access(case_id,True)
                            minutes = 1 if parsed.path == '/renew-short-token' else 120
                            fresh = dev_auth.token(auth,subjects[choice],minutes)
                            tokens[choice] = fresh; private_tokens.append(fresh)
                            if minutes == 1:
                                claims = dev_auth.jwt.decode(fresh,(auth/'public.pem').read_bytes(),algorithms=['RS256'],
                                    audience=AUDIENCE,issuer=ISSUER)
                                specs[case_id]['short_expiry'] = claims['exp']
                            report.setdefault('credential_events', []).append(dict(case=case_id,minutes=minutes,same_subject=True))
                            save(); value = fixture_value(case_id)
                        elif parsed.path == '/wait-real-expiry':
                            case_id = query['case'][0]; spec = specs[case_id]
                            while time.time() <= spec['short_expiry']: time.sleep(.2)
                            with TestClient(app) as client:
                                response = client.get('/v2/run-draft-status',params={'message_id':proof(case_id)['message_id']},
                                    headers={'Authorization':'Bearer '+tokens[spec['choice']]})
                            assert response.status_code == 401
                            payload = response.json()
                            assert not {'run_id','conversation_id','draft_outcome','budget_exhausted_stage'} & payload.keys()
                            report.setdefault('auth_events', []).append(dict(case=case_id,expired=True,status=response.status_code,
                                error=payload['error']['code'],private_result_absent=True))
                            save(); value = {}
                        elif parsed.path == '/release':
                            with lock: specs[query['case'][0]]['release'].set()
                            value = {}
                        else: raise ValueError('unknown control')
                        body = json.dumps(value).encode(); self.send_response(200)
                        self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(body)
                    except Exception as error:
                        report.setdefault('control_errors', []).append(type(error).__name__); save()
                        self.send_response(500); self.end_headers(); self.wfile.write(type(error).__name__.encode())
            control = ThreadingHTTPServer(('127.0.0.1', 0), Control)
            threading.Thread(target=control.serve_forever, daemon=True).start()
            try:
                spec = importlib.util.spec_from_file_location('trip_acceptance', ROOT / 'scripts/check_ios_trip_confirm.py')
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                builder = object.__new__(module.XCTestDriver); builder.directory = output / 'project'; builder.directory.mkdir(); builder.write_project(0)
                (builder.directory / 'G2CControl.swift').write_text((HERE / 'DevelopmentRunUITests.swift').read_text().replace('__FIXTURE_URL__', f'http://127.0.0.1:{control.server_port}'))
                project = builder.directory / 'G2CAcceptance.xcodeproj'; pbx = project / 'project.pbxproj'
                text = pbx.read_text().replace('space.go2china.foundation.local', BUNDLE).replace('space.go2china.foundation.control', BUNDLE + '.control')
                entitlements = builder.directory / 'Development.entitlements'; entitlements.write_bytes(plistlib.dumps({'application-identifier': BUNDLE, 'keychain-access-groups': [BUNDLE]}))
                text = text.replace(json.dumps(str(ROOT / 'ios/App/Development.entitlements')), json.dumps(str(entitlements)))
                line = next(l for l in text.splitlines() if l.startswith('A00000000000000000000004 = {isa = XCBuildConfiguration; name = Debug;'))
                text = text.replace(line, line + '\n' + line.replace('A00000000000000000000004', 'A0000000000000000000000C', 1).replace('name = Debug;', 'name = Release;', 1)).replace('buildConfigurations = (A00000000000000000000004);', 'buildConfigurations = (A00000000000000000000004, A0000000000000000000000C);')
                pbx.write_text(text)
                suite = CASES + DRAFT_CASES + BUDGET_CASES + AUTH_CASES
                cases = [args.diagnostic_test] if args.diagnostic_test else suite + ['testReleaseClosed']
                if args.diagnostic_test: report['unrun'] += [c for c in suite + ['testReleaseClosed'] if c not in cases]
                for case in cases:
                    configuration = 'Release' if case == 'testReleaseClosed' else 'Debug'
                    result = output / (case + '.xcresult')
                    command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-configuration', configuration,
                        '-destination', 'platform=iOS Simulator,id=' + args.simulator, '-derivedDataPath', str(build), '-resultBundlePath', str(result),
                        '-scmProvider', 'system', '-skipPackageUpdates', '-onlyUsePackageVersionsFromResolvedFile', '-parallel-testing-enabled', 'NO',
                        '-collect-test-diagnostics', 'never', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES', 'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-',
                        '-only-testing:G2CControl/DevelopmentRunUITests/' + case, 'test']
                    print('Running ' + case, flush=True)
                    run = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1200)
                    log = run.stdout
                    for token in private_tokens: log = log.replace(token, '<redacted-local-token>')
                    (output / (case + '.log')).write_text(log); run.check_returncode()
                    summary = json.loads(subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)], env=env))
                    (output / (case + '-summary.json')).write_text(json.dumps(summary, indent=2))
                    assert summary['passedTests'] == 1 and summary['failedTests'] == 0 and summary['skippedTests'] == 0
                    report['cases'][case] = 'PASS'; save()
                report['database_proofs'] = {cid: proof(cid) for cid in specs}
                report['cross_account_reads'] = {}
                with TestClient(app) as client:
                    for cid, spec in specs.items():
                        original = report['database_proofs'][cid]['message_id']
                        if original is None: continue
                        other = 'B' if spec['choice'] == 'A' else 'A'
                        response = client.get('/v2/run-draft-status', params={'message_id': original}, headers={'Authorization': 'Bearer ' + tokens[other]})
                        assert response.status_code != 200 and not {'draft_outcome','run_id','conversation_id','budget_exhausted_stage'} & response.json().keys()
                        report['cross_account_reads'][cid] = dict(status=response.status_code, private_result_absent=True)
                assert not errors
                container = Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', args.simulator, BUNDLE, 'data'], env=env, text=True).strip())
                for path in container.rglob('*'):
                    if path.is_file() and not path.is_symlink():
                        data = path.read_bytes()
                        assert not any(t.encode() in data for t in private_tokens), 'token in App files'
                        assert b'-----BEGIN PRIVATE KEY-----' not in data
                        assert not any(s['prompt'].encode() in data for s in specs.values()), 'plaintext original in App files'
                report['app_file_token_scan'] = 'PASS'
                report['app_plaintext_key_scan'] = 'PASS'
                report['status'] = 'PARTIAL_PASS'  # One actual scenario; the orchestrator checks the complete set.
            except BaseException as error:
                report['status'] = 'FAIL'; report['error'] = type(error).__name__
                report['failure_proofs'] = {}
                for cid in specs:
                    try: report['failure_proofs'][cid] = proof(cid)
                    except Exception as diagnostic: report['failure_proofs'][cid] = dict(error=type(diagnostic).__name__)
                with lock:
                    report['request_audit'] = list(audit)
                    report['response_audit'] = list(responses)
                    report['stream_frames'] = list(stream_frames)
                raise
            finally:
                stop.set()
                with lock:
                    for spec in specs.values(): spec['release'].set()
                    for held in held_reads.values(): held['release'].set()
                worker_thread.join(timeout=10); server.should_exit = True; api_thread.join(timeout=10)
                control.shutdown(); control.server_close()
                subprocess.run(['xcrun', 'simctl', 'terminate', args.simulator, BUNDLE], env=env, capture_output=True)
                leaked = [str(p.relative_to(output)) for p in output.rglob('*') if p.is_file() and not p.is_symlink()
                          and (any(t.encode() in p.read_bytes() for t in private_tokens) or b'-----BEGIN PRIVATE KEY-----' in p.read_bytes())]
                report['artifact_token_scan'] = 'FAIL' if leaked else 'PASS'
                if leaked: report['status'] = 'FAIL'; report['token_artifacts'] = leaked
                if worker_thread.is_alive() or api_thread.is_alive(): report['status'] = 'FAIL'; report['shutdown'] = 'thread still alive'
                report['worker_errors'] = list(errors)
                with lock:
                    report['request_audit'] = list(audit)
                    report['response_audit'] = list(responses)
                    report['stream_frames'] = list(stream_frames)
                save()
    print(json.dumps({k: report[k] for k in ('status', 'cases', 'unrun', 'artifact_token_scan')}, indent=2))
    if report['status'] == 'FAIL': raise SystemExit(1)


if __name__ == '__main__': main()
