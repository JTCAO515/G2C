"""#498: one reproducible bilingual App acceptance matrix, reusing owning suites.

This driver runs local signed API/private PG/FakeProvider/Simulator evidence.
Each slice retains its own identities and source proofs. It is a journey matrix,
not a claim that different fixture accounts are one continuous user session.
Physical-device and VoiceOver execution are separately recorded under #29.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

# (id, owner harness, selected args, required context budget or None).
# A selected native case is required in full; no assertion or AX filter changes.
STEPS = [
    ('accounts', 'check_development_accounts.py', [], None),
    ('needs-en', 'check_needs.py', ['--case', 'testEnglish'], 16),
    ('needs-zh', 'check_needs.py', ['--case', 'testChineseLarge'], 16),
    ('timezones', 'check_needs.py', ['--case', 'testDeviceTimezones'], 16),
    ('plan-accept', 'check_manual_trips.py', ['--case', 'testNeedsPlanningAccept', '--largest-recovery'], 16),
    ('manual-edit', 'check_manual_trips.py', ['--case', 'testNeedsManualTitleSave'], 16),
    ('typed-en', 'check_typed_memory.py', ['--case', 'testEnglishSaveReadAndOwnedTravel'], 16),
    ('typed-zh', 'check_typed_memory.py', ['--case', 'testChineseLargeSaveReadAndRecall'], 16),
    ('manage-en', 'check_memory_lifecycle.py', ['--case', 'testEnglish'], 16),
    ('manage-zh', 'check_memory_lifecycle.py', ['--case', 'testChineseLarge'], 16),
    ('candidate-en', 'check_memory_candidate.py', ['--case', 'testConfirmCandidateEnglish'], 2),
    ('candidate-zh', 'check_memory_candidate.py', ['--case', 'testConfirmCandidateChinese'], 2),
    ('erase-en', 'check_memory_erasure.py', ['--case', 'testMemoryErasureEnglish'], 4),
    ('erase-zh', 'check_memory_erasure.py', ['--case', 'testMemoryErasureChinese'], 4),
    ('feedback-en', 'check_feedback.py', ['--case', 'testAnswerAndGeneralEnglish'], 16),
    ('feedback-zh', 'check_feedback.py', ['--case', 'testAnswerAndGeneralChinese'], 16),
    ('offline', 'check_offline_trips.py', ['--case', 'testReopenLanguageAndReadOnly'], 16),
    ('account-cleanup', 'check_account_cleanup_component.py',
     ['--native-device', '--all-provided', '--case', 'testActualAllProvidedDomains'], 4),
    ('structure', 'check_shell_structure.py', ['--suite', 'structure'], None),
    ('accessibility', 'check_shell_structure.py', ['--suite', 'accessibility'], None),
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--simulator', required=True)
    p.add_argument('--run-context', required=True, type=Path,
                   help='explicit CJ-LOCAL-RUN@2 profile; budget16; no real providers')
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--build-dir', required=True, type=Path)
    p.add_argument('--step', choices=[s[0] for s in STEPS], action='append',
                   help='diagnostic subset; overall result remains PARTIAL_PASS')
    args = p.parse_args()
    output, build = args.output.resolve(), args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):
        raise ValueError('external evidence/build directories required')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT):
        raise ValueError('commit candidate before acceptance')
    output.mkdir(parents=True, exist_ok=False)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    context = json.loads(args.run_context.read_text())
    if context['version'] != 'CJ-LOCAL-RUN@2' or context['current']['meter']['budget'] != 16:
        raise ValueError('explicit @2/budget16 matrix profile required')
    contexts = {}
    for budget in (2, 4, 16):
        value = json.loads(json.dumps(context))
        # Fresh, separately provisioned subjects/clusters per owning driver.
        # No existing ledger or account is changed or reset.
        value['current']['meter']['budget'] = budget
        path = output / f'run-context-{budget}.json'
        path.write_text(json.dumps(value, indent=2)); contexts[budget] = path
    report = dict(status='RUNNING', head=head, required_steps=[s[0] for s in STEPS],
                  steps={s[0]:dict(status='UNRUN') for s in STEPS},
                  evidence_layer='L0/L1 local signed API + restricted PG + FakeProvider + native Simulator',
                  unrun=['real OTP/accounts/providers/target network', 'physical device/VoiceOver #29', 'TestFlight #33'],
                  os_activity_mode='disable')
    def save():
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    save()
    env = dict(os.environ, OS_ACTIVITY_MODE='disable')
    selected = [s for s in STEPS if not args.step or s[0] in args.step]
    for name, harness, flags, budget in selected:
        if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != head:
            report.update(status='FAIL', error='candidate head changed between steps'); save()
            raise SystemExit(1)
        destination = output / name
        command = [sys.executable, '-B', str(HERE / harness), '--simulator', args.simulator,
                   '--output', str(destination), '--build-dir', str(build / name), *flags]
        if budget:
            command += ['--run-context', str(contexts[budget])]
        if harness in ('check_feedback.py', 'check_memory_candidate.py', 'check_memory_erasure.py', 'check_account_cleanup_component.py'):
            command += ['--backend-source', str(ROOT), '--backend-head', head]
        elif harness == 'check_manual_trips.py':
            command += ['--backend-root', str(ROOT), '--backend-head', head]
        print('M4 START ' + name, flush=True)
        report['steps'][name] = dict(status='RUNNING'); save()
        run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=5400)
        (output / (name + '.log')).write_bytes(run.stdout + run.stderr)
        path = destination / 'report.json'
        child = json.loads(path.read_text()) if path.exists() else {}
        # The owning harness checks actual XCTest counts, skips, runtime proofs
        # and its case assertions before reporting these statuses.
        accepted_statuses = ('PASS_APP_WITH_PINNED_CANDIDATE_BACKEND',) if harness == 'check_manual_trips.py' else ('PASS', 'PARTIAL_PASS')
        passed = run.returncode == 0 and child.get('status') in accepted_statuses
        report['steps'][name] = dict(status='PASS' if passed else 'FAIL', exit_code=run.returncode,
            owner_status=child.get('status', 'UNKNOWN'), evidence=str(path.relative_to(output)),
            report_sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None)
        save(); print('M4 ' + name + ' ' + report['steps'][name]['status'], flush=True)
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != head:
        report.update(status='FAIL', error='candidate head changed during final step')
    elif any(s['status'] == 'FAIL' for s in report['steps'].values()):
        report['status'] = 'FAIL'
    else:
        report['status'] = 'PARTIAL_PASS' if args.step else 'PASS'
    save()
    print(json.dumps(dict(status=report['status'], steps={k:v['status'] for k,v in report['steps'].items()}), indent=2))
    if report['status'] == 'FAIL':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
