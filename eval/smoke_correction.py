"""JT's one-case completion of the sealed C body-prefix false negative.

The original phase remains immutable. This separate once-only claim permits
only its never-started English FACT cell, followed by the normal full gate.
"""
import argparse
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import time

import hk
import real_phase
import smoke
from real_budget import estimate, verified_journal

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'eval/smoke_correction.json'


def read(path):
    return json.loads(path.read_bytes())


def correction_path(policy):
    return real_phase.PHASES / (policy['adapter_identity']['pin'] + '-smoke-correction-1.json')


def validate_original():
    """Recheck the specific approved bytes, source applicability and live receipts."""
    policy = read(POLICY)
    if policy['version'] != 'C-SMOKE-CORRECTION.1':
        raise ValueError('approved_correction_version_required')
    if (real_phase.adapter_identity() != policy['adapter_identity']
            or hk.source_info()['backend_commit'] != policy['backend_commit']):
        raise ValueError('unchanged_approved_B_candidate_required')
    dependencies = dict(policy['unchanged_eval_sha256'])
    dependencies['eval/real.py'] = policy['approved_body_file_sha256']
    for name, digest in dependencies.items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError('approved_checker_and_unchanged_evaluation_dependencies_required')
    original = Path(policy['original_output'])
    claim_path = real_phase.path_for('smoke')
    result_path = claim_path.with_suffix('.result.json')
    if (sha256(claim_path.read_bytes()).hexdigest() != policy['claim_sha256']
            or sha256(result_path.read_bytes()).hexdigest() != policy['result_sha256']):
        raise ValueError('original_sealed_failed_phase_required')
    claim, result = read(claim_path), read(result_path)
    if (claim['output'] != str(original.resolve())
            or claim['candidate_id'] != policy['original_candidate']
            or claim['adapter_identity'] != policy['adapter_identity']
            or result['candidate_id'] != policy['original_candidate']
            or result['status'] != 'FAIL'):
        raise ValueError('specific_original_false_negative_required')
    sealed = {name: (original / name).read_bytes() for name in policy['original_file_sha256']}
    for name, digest in policy['original_file_sha256'].items():
        if sha256(sealed[name]).hexdigest() != digest:
            raise ValueError('immutable_original_smoke_bytes_required')
    plan, rows = json.loads(sealed['plan.json']), json.loads(sealed['observations.json'])
    if (plan['candidate_id'] != policy['original_candidate']
            or plan['execution_source'] != dict(runner_commit=policy['original_candidate'],
                backend_commit=policy['backend_commit'],
                manifest_sha256=policy['original_manifest_sha256'])):
        raise ValueError('original_execution_provenance_required')
    missing = policy['missing_cell']
    expected = {(c['id'], language) for c in plan['cases'] for language in ('zh', 'en')}
    completed = {(r['case_id'], r['language']) for r in rows}
    starts = json.loads(sealed['case-starts.json'])
    if (missing != dict(case_id='fact', language='en') or policy['max_new_cases'] != 1
            or len(rows) != 5 or completed != expected - {('fact', 'en')}
            or len(starts) != 5 or {(s['case_id'], s['language']) for s in starts} != completed
            or any(s['attempt'] != 1 for s in starts)):
        raise ValueError('only_never_started_English_FACT_may_complete')
    records = verified_journal()
    actual = {r['attempt_id']: r for r in records}
    for old in json.loads(sealed['budget-after.json']):
        if actual.get(old['attempt_id']) != old:
            raise ValueError('original_authorization_snapshot_changed')
    assessment = smoke.summarize(plan, rows, original)
    if ([r['status'] for r in assessment['outcomes']] != ['PASS'] * 5 + ['UNRUN']
            or assessment['full66_authorized_to_start']):
        raise ValueError('all_five_original_complete_chains_must_revalidate')
    return policy, sealed, plan, rows, records


def remaining_forecast(records):
    # The only missing smoke cell permits FACT, which has no paid-tool hold.
    forecast = estimate(records, include_smoke=False)
    forecast['basis'] = 'JT-approved original five reused; two model rounds for unrun FACT plus original137/54 full forecast'
    forecast['additional_estimate_cny']['model'] += 2
    forecast['projected_conservative_cny']['model'] += 2
    after = forecast['projected_conservative_cny']
    forecast['within_stop_lines'] = all(after[k] < forecast['stop_cny'][k] for k in after)
    forecast['within_budget'] = all(after[k] <= forecast['budget_cny'][k] for k in after)
    forecast['within_authorization'] = forecast['within_stop_lines'] and forecast['within_budget']
    return forecast


def verify_corrected_smoke(output, candidate):
    policy, _, _, _, _ = validate_original()
    path = correction_path(policy)
    claim, result = read(path), read(path.with_suffix('.result.json'))
    if (claim['version'] != policy['version'] or claim['approval_ref'] != policy['approval_ref']
            or claim['candidate_id'] != candidate or result['candidate_id'] != candidate
            or claim['output'] != str(output.resolve()) or result['status'] != 'PASS'
            or claim['adapter_identity'] != policy['adapter_identity']
            or claim['original_result_sha256'] != policy['result_sha256']
            or claim['new_case'] != policy['missing_cell']
            or claim['execution_source'] != hk.source_info()):
        raise ValueError('same_candidate_approved_correction_PASS_required')
    expected = {'plan.json', 'observations.json', 'summary.json',
                'original-plan.json', 'original-observations.json', 'original-summary.json'}
    expected.update('raw/' + case + '-' + language + '.json'
                    for case in ('place-route', 'weather', 'fact') for language in ('zh', 'en'))
    if set(result['hashes']) != expected:
        raise ValueError('complete_correction_seal_required')
    for name, digest in result['hashes'].items():
        if sha256((output / name).read_bytes()).hexdigest() != digest:
            raise ValueError('original_correction_evidence_changed')
    for name, digest in policy['original_file_sha256'].items():
        if name.startswith('raw/'):
            if sha256((output / name).read_bytes()).hexdigest() != digest:
                raise ValueError('reused_raw_bytes_changed')
    for name in ('plan.json', 'observations.json', 'summary.json'):
        if sha256((output / ('original-' + name)).read_bytes()).hexdigest() != policy['original_file_sha256'][name]:
            raise ValueError('original_negative_evidence_changed')


def reused_rows(original, rows):
    result = deepcopy(rows)
    for row in result:
        raw = read(original / row['raw_evidence_ref'])
        receipt = raw['observed']['message_receipt']
        if row['first_body_seconds'] is None:
            row['original_first_body_seconds'] = None
            row['first_body_seconds'] = next(e['client_seconds'] for e in raw['events']
                if e.get('data', {}).get('run_id') == receipt['run_id']
                and e['data'].get('message_id') == receipt['message_id']
                and smoke.body_available(e['data'].get('text', '')))
            row['timing_source'] = 'original recorded client_seconds, corrected body recognition'
        row['reused_original_evidence'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not hk.active() or os.environ.get('CJ_M4_SYNTHETIC_ONLY') != '1':
        raise ValueError('approved_HK_synthetic_execution_required')
    hk.require_output(args.output)
    policy = read(POLICY)
    path = correction_path(policy)
    if args.output.exists() or path.exists() or real_phase.claimed('full'):
        print('READ_ONLY: original correction/full claim retained; no dispatch')
        return 0
    policy, sealed, original_plan, original_rows, records = validate_original()
    forecast = remaining_forecast(records)
    if not forecast['within_authorization']:
        raise ValueError('remaining_FACT_plus_full_exceeds_authorization_report_495')
    candidate = hk.source_candidate()
    claim = dict(version=policy['version'], approval_ref=policy['approval_ref'],
        candidate_id=candidate, execution_source=hk.source_info(),
        output=str(args.output.resolve()), adapter_identity=policy['adapter_identity'],
        original_result_sha256=policy['result_sha256'], new_case=policy['missing_cell'])
    # Preserve even an incomplete claim. This authorization can never replay.
    real_phase.PHASES.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        real_phase.exclusive(path, claim)
    except FileExistsError:
        print('READ_ONLY: correction already claimed; no dispatch')
        return 0
    case = next(c for c in original_plan['cases'] if c['id'] == 'fact')
    subject = 'm4-synthetic-r2-smoke-fact-en'
    plan = dict(original_plan, candidate_id=candidate, execution_source=hk.source_info(),
        correction=claim, original_execution_source=original_plan['execution_source'])
    args.output.mkdir(parents=True, mode=0o700)
    (args.output / 'raw').mkdir(mode=0o700)
    for name in ('plan.json', 'observations.json', 'summary.json'):
        (args.output / ('original-' + name)).write_bytes(sealed[name])
    for row in original_rows:
        target = args.output / row['raw_evidence_ref']
        target.write_bytes(sealed[row['raw_evidence_ref']])
        target.chmod(0o600)
    rows = reused_rows(args.output, original_rows)
    starts = json.loads(sealed['case-starts.json'])
    smoke.save(args.output / 'plan.json', plan)
    smoke.save(args.output / 'estimate.json', forecast)
    smoke.save(args.output / 'budget-before.json', records)
    smoke.save(args.output / 'packages.json', {p: version(p) for p in ('httpx', 'psycopg', 'uvicorn', 'fastapi')})
    smoke.save(args.output / 'observations.json', rows)
    smoke.save(args.output / 'case-starts.json', starts)
    summary = smoke.summarize(plan, rows, args.output)
    if [r['status'] for r in summary['outcomes']] != ['PASS'] * 5 + ['UNRUN']:
        raise ValueError('copied_original_chains_must_revalidate_before_dispatch')
    smoke.save(args.output / 'summary.json', summary)
    smoke.write_progress('smoke', plan, rows, args.output, summary, starts)
    services = smoke.create_real_services(frozenset((subject,)))
    budget = services.model.authorization
    budget.check_date()
    with redirect_stdout(io.StringIO()), smoke.private_database('real-smoke-correction') as conninfo:
        auth = conninfo.parent / 'auth'
        smoke.dev_auth.init(auth, [subject])
        now = int(time.time())
        config = json.loads(sealed['runtime-config.json'])
        config['current']['meter'].update(period_start=now-60, period_end=now+7200)
        profile = conninfo.parent / 'run.json'
        smoke.save(profile, config)
        smoke.save(args.output / 'runtime-config.json', config)
        context = smoke.load_run_context(profile)
        smoke.local_run_context.provision_budget(conninfo, context, subject)
        smoke.dev_auth.activate_travel(conninfo, subject, context, smoke.ABI)
        database = smoke.LocalDatabase(conninfo, run_context=context, travel_context=True, needs_context=True)
        app = smoke.create_local_app(conninfo_path=conninfo, auth_dir=auth, run_context=context,
            travel_context=True, needs_profile='manual-v1',
            confirmation_signer=smoke.ConfirmationSigner((auth / 'trip-confirmation.key').read_bytes()))
        with smoke.tcp_app(app) as client:
            starts.append(dict(case_id='fact', language='en', attempt=1,
                started_at=datetime.now(timezone.utc).isoformat()))
            smoke.save(args.output / 'case-starts.json', starts)
            smoke.write_progress('smoke', plan, rows, args.output, summary, starts)
            evidence = dict(input_sha256=sha256(case['inputs']['en'].encode()).hexdigest(), execution_stage='run_case')
            row = dict(case_id='fact', language='en', raw_evidence_ref='raw/fact-en.json',
                first_body_seconds=None, full_answer_seconds=None, reused_original_evidence=False)
            scenario = dict(case, id='smoke-fact', recipe='answer')
            try:
                with smoke.capture_failure(evidence):
                    observed, expected, first, full = smoke.run_case(client, database, conninfo, auth,
                        context, services, scenario, 'en', subject, evidence,
                        allowed_native=frozenset(case['native']))
                evidence.update(observed=observed, expected=expected)
                row.update(first_body_seconds=first, full_answer_seconds=full)
            except Exception as error:
                evidence['error_kind'] = type(error).__name__
            evidence['operations'] = smoke.original_operations(database, subject)
            ids = {op['attempt_id'] for op in evidence['operations']}
            evidence['authorization_attempts'] = [r for r in budget.inspect() if r['attempt_id'] in ids]
            smoke.save(args.output / row['raw_evidence_ref'], evidence)
            rows.append(row)
    smoke.save(args.output / 'observations.json', rows)
    smoke.save(args.output / 'budget-after.json', budget.inspect())
    summary = smoke.summarize(plan, rows, args.output)
    smoke.save(args.output / 'summary.json', summary)
    smoke.write_progress('smoke', plan, rows, args.output, summary, starts)
    files = ['plan.json', 'observations.json', 'summary.json',
             'original-plan.json', 'original-observations.json', 'original-summary.json']
    files.extend(r['raw_evidence_ref'] for r in rows)
    status = summary['status']
    real_phase.exclusive(path.with_suffix('.result.json'), dict(candidate_id=candidate, status=status,
        hashes={name: sha256((args.output / name).read_bytes()).hexdigest() for name in files}))
    print('fact en ' + status)
    return 0 if status == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
