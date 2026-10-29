"""Complete #167 native matrix, each case in its own protected private DB/scope.

Consumes explicit operator configuration files; never rewrites quotas or periods.
Stops on the first failure and retains every child report and xcresult.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from check_runs import CASES, DRAFT_CASES, BUDGET_CASES, ROOT, HERE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--budget-one-context', required=True, type=Path)
    parser.add_argument('--budget-two-context', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--build-dir', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT): raise ValueError('External evidence only')
    output.mkdir(parents=True)  # Never overwrite prior evidence.
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT): raise ValueError('Commit the reviewed candidate first')
    contexts = {}
    for budget, source in ((1,args.budget_one_context),(2,args.budget_two_context)):
        raw = source.read_bytes(); value = json.loads(raw)
        if value['version'] != 'CJ-LOCAL-RUN@1' or value['current']['meter']['budget'] != budget or value['current']['meter']['unit'] != 'provider_call':
            raise ValueError('Explicit documented provider_call profile required')
        target = output / f'context-{budget}.json'; target.write_bytes(raw); contexts[budget] = target
    cases = CASES + DRAFT_CASES + BUDGET_CASES + ['testReleaseClosed']
    assert len(cases) == len(set(cases)) == 23
    report = dict(status='RUNNING', head=head, cases={}, required_cases=cases,
        unrun=['real tools', 'real model/fees', 'cloud', 'physical device/VoiceOver', 'release deployment'],
        scope='Formal protected local host, operator CLI, runtime PG, FakeProvider subclass, native App; no quota/response injection')
    def save(): (output / 'report.json').write_text(json.dumps(report, indent=2))
    save()
    try:
        for case in cases:
            if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=head or subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):
                raise RuntimeError('Candidate changed during acceptance')
            budget = 1 if 'Budget' in case else 2
            child = output / case
            command = [sys.executable, '-B', str(HERE/'check_runs.py'), '--simulator', args.simulator,
                '--run-context', str(contexts[budget]), '--diagnostic-test', case,
                '--output', str(child), '--build-dir', str(args.build_dir.resolve())]
            print('Native case: '+case, flush=True)
            with (output/(case+'-driver.log')).open('w') as log:
                result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode: raise RuntimeError('Native case failed: '+case)
            evidence = json.loads((child/'report.json').read_text())
            assert evidence['status']=='PARTIAL_PASS' and evidence['cases']=={case:'PASS'}
            assert evidence['head']==head and evidence['working_tree_dirty'] is False
            assert evidence['run_context']==json.loads(contexts[budget].read_text())
            assert evidence['app_file_token_scan']==evidence['artifact_token_scan']=='PASS'
            assert evidence['worker_errors']==[]
            for path,digest in evidence['source_hashes'].items():
                assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
            assert all(p['runtime_role']=='cj_m1_runtime' and p['pending_deliveries']==0 and p['forbidden_writes']==0 and p['tool_steps']==0 for p in evidence['database_proofs'].values())
            if case!='testReleaseClosed':
                assert evidence['worker_restarts'] and evidence['cross_account_reads']
            if 'Published' in case:
                assert evidence['native_foreign_account_checks']
            report['cases'][case]=dict(status='PASS', budget=budget, report=str((child/'report.json').relative_to(output)))
            save()
        report['status']='PASS'
    except BaseException as error:
        report['status']='FAIL'; report['error']=str(error); raise
    finally: save()
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
