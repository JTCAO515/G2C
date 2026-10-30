"""#244: actual native @2 registered limits and immutable original recovery.

The operator supplies budgets/periods. No quota injection or manufactured HTTP
refusal. Existing #167 @1 cases and their assertions remain unchanged.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from check_runs import BUDGET_CASES, AUTH_CASES, ROOT, HERE

REGISTERED_CASES = BUDGET_CASES + ['testStopEnglish', 'testStopChinese'] + AUTH_CASES + ['testReleaseClosed']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--budget-one-context', type=Path, required=True)
    parser.add_argument('--budget-two-context', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--case', choices=REGISTERED_CASES)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT): raise ValueError('External evidence only')
    output.mkdir(parents=True)
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT): raise ValueError('Commit candidate before acceptance')
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    contexts = {}
    for budget, source in [(1,args.budget_one_context),(2,args.budget_two_context)]:
        raw=source.read_bytes(); value=json.loads(raw)
        if (value['version']!='CJ-LOCAL-RUN@2' or value['current']['meter']['budget']!=budget
                or value['current']['meter']['unit']!='provider_call'):
            raise ValueError('Explicit @2 provider_call operator profiles required')
        target=output/('context-'+str(budget)+'.json'); target.write_bytes(raw); contexts[budget]=target
    cases=[args.case] if args.case else REGISTERED_CASES
    report=dict(status='RUNNING',head=head,cases={},required_cases=REGISTERED_CASES,
        scope='Actual signed local API/runtime-role PG/formal run_once and worker CLI/FakeProvider; original @2 registered operations',
        unrun=['real tools/background business producers','real model/services/fees/cloud','physical device/VoiceOver','deployment'])
    if args.case: report['unrun'] += [c for c in REGISTERED_CASES if c!=args.case]
    def save(): (output/'report.json').write_text(json.dumps(report,indent=2))
    save()
    try:
        for case in cases:
            if (subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=head
                    or subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)):
                raise RuntimeError('Candidate changed during acceptance')
            budget=1 if 'Budget' in case or case in AUTH_CASES else 2
            child=output/case
            command=[sys.executable,'-B',str(HERE/'check_runs.py'),'--simulator',args.simulator,
                '--run-context',str(contexts[budget]),'--diagnostic-test',case,
                '--output',str(child),'--build-dir',str(args.build_dir.resolve())]
            print('Registered native: '+case,flush=True)
            with (output/(case+'-driver.log')).open('w') as log:
                subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            evidence=json.loads((child/'report.json').read_text())
            assert evidence['head']==head and not evidence['working_tree_dirty']
            assert evidence['status']=='PARTIAL_PASS' and evidence['cases']=={case:'PASS'}
            assert evidence['run_context']==json.loads(contexts[budget].read_text())
            assert evidence['app_file_token_scan']==evidence['artifact_token_scan']==evidence['app_plaintext_key_scan']=='PASS'
            assert evidence['worker_errors']==[]
            for path,digest in evidence['source_hashes'].items(): assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
            for path,tree in evidence['git_trees'].items():
                assert subprocess.check_output(['git','rev-parse',head+':'+path],cwd=ROOT,text=True).strip()==tree
            for proof in evidence['database_proofs'].values():
                assert proof['runtime_role']=='cj_m1_runtime' and proof['pending_deliveries']==0 and proof['forbidden_writes']==0
                assert proof['registered_fingerprint'] is not None
                if case!='testReleaseClosed': assert proof['registered_operations']>0
            if case!='testReleaseClosed': assert evidence['worker_restarts'] and evidence['cross_account_reads']
            if case=='testRegisteredSwitchOriginal': assert evidence['held_originals']
            if case=='testRegisteredRevokedOriginal':
                assert evidence['held_originals'] and any(event.get('allowed') is False for event in evidence['auth_events'])
            if case=='testRegisteredExpiredOriginal':
                assert any(event.get('expired') is True and event['status']==401 for event in evidence['auth_events'])
            report['cases'][case]=dict(status='PASS',budget=budget,report=str((child/'report.json').relative_to(output)))
            save()
        report['status']='PARTIAL_PASS' if args.case else 'PASS'
    except BaseException as error:
        report['status']='FAIL'; report['error']=type(error).__name__; raise
    finally: save()
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
