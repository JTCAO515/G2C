"""Fake-only full scenario runner. Real provider selection belongs to an authorized host."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time
import traceback
from runtime import ROOT, private_database
from cases import run_case, case_session
from judge import judge
from report import report, markdown


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--attempts',type=int,nargs='+',default=[1,2])
    parser.add_argument('--only',nargs='+')
    args=parser.parse_args()
    scenarios_path=Path(__file__).with_name('scenarios.json')
    raw=scenarios_path.read_bytes();scenarios=json.loads(raw)
    if args.only and set(args.only)-{s['id'] for s in scenarios}:parser.error('unknown scenario')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    plan=dict(schema_version=1,sample_set_id='g2c-m4-synthetic-33',sample_set_version='2:'+sha256(raw).hexdigest(),
              provenance='Synthetic only, paired zh/en, eleven fixed holdout; original ten unchanged, no prompt/model tuning.',
              evidence_layer='local',approved_thresholds=None,attempts=args.attempts,
              candidates=[dict(id=commit,commit=commit,config_version='eval-local-signed.1 / existing legacy and typed APIs; no product changes',
                               model_version='FakeProvider@'+commit,source_as_of='synthetic; no current external source')],
              networks=[dict(id='local-asgi',description='Local ASGI signed API/private Unix-socket PG; not overseas/China target network')],scenarios=scenarios)
    # Reuse validation before any execution/output mutation.
    report(plan,[])
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'raw').mkdir()
    (args.output/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    observations=[]
    for attempt in args.attempts:
        with private_database('evaluation-'+str(attempt)), case_session() as fixture:
            for scenario in scenarios:
                if args.only and scenario['id'] not in args.only:continue
                for language in ('zh','en'):
                    key=f"{scenario['id']}-{language}-{attempt}"
                    row=dict(candidate_id=commit,scenario_id=scenario['id'],language=language,network_id='local-asgi',attempt=attempt,
                             purpose='holdout' if scenario['split']=='holdout' else 'evaluation',
                             attempt_source='eval/run.py actual local signed API/PG/original worker',
                             observed_at=datetime.now(timezone.utc).isoformat(),source_as_of='synthetic; no real source',
                             raw_evidence_ref='raw/'+key+'.json',first_body_seconds=None,draft_seconds=None,
                             cost=dict(complete=False,components=[dict(name='monetary receipt',amount=None,currency='UNKNOWN',source='No real provider/tool billing receipt')]))
                    started=time.monotonic()
                    try:
                        observed,expected=run_case(scenario,language,fixture)
                        judgment=judge(scenario,observed,expected)
                        evidence=dict(observed=observed,expected=expected,judgment=judgment,input_sha256=sha256(scenario['inputs'][language].encode()).hexdigest())
                        row.update(status='success',model_calls=observed['model_calls'],
                                   api_task_seconds=observed.get('api_task_seconds'),independent_judgment=judgment,
                                   judgment=dict(kind='program',independent=True,outcome=judgment['task_outcome'],ref='eval/judge.py'),serious_errors=judgment['serious_errors'])
                    except Exception:
                        evidence=dict(traceback=traceback.format_exc(),failure_kind='execution_or_evaluation_error; inspect original evidence')
                        row.update(status='failure',model_calls=None,api_task_seconds=None,
                                   judgment=dict(kind='program',independent=True,outcome='FAIL',ref='eval/run.py execution error'),serious_errors=[])
                    row['scenario_wall_seconds']=time.monotonic()-started
                    (args.output/row['raw_evidence_ref']).write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
                    observations.append(row)
                    (args.output/'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2)+'\n')
                    summary=report(plan,observations)
                    (args.output/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
                    (args.output/'report.md').write_text(markdown(summary))
                    print(key,row['status'],row['judgment']['outcome'],flush=True)
    return int(any(row['status']=='failure' or row['judgment']['outcome']=='FAIL' for row in observations))


if __name__=='__main__':raise SystemExit(main())
