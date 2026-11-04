"""Reuse the accepted CJ028 matrix/cost/UNKNOWN accounting, adding call counts."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'evaluation/cj028'))
from evaluate import summarize, latency


def report(plan, observations):
    result = summarize(plan, observations)
    for group in result['groups']:
        rows = [a['observation'] for a in group['attempts']]
        counts = [r.get('model_calls') for r in rows if r is not None]
        group['model_calls'] = dict(known_total=sum(c for c in counts if c is not None),
                                    known_attempt_n=sum(c is not None for c in counts),
                                    unknown_or_unrun_attempt_n=len(rows)-sum(c is not None for c in counts))
        group['api_task_seconds'] = latency(rows, 'api_task_seconds')
        group['latency_scope'] = 'signed API submit through original worker and final authoritative read; not UI first-body timing'
        group['hard_outcomes'] = {status:sum(r is not None and r.get('independent_judgment',{}).get('hard_outcome')==status for r in rows)
                                  for status in ('PASS','FAIL','UNKNOWN')}
    return result


def main():
    import argparse,json
    from evaluate import read_json,InputError
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--observations',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    plan=read_json(args.plan.read_text());observations=read_json(args.observations.read_text())
    try:
        result=report(plan,observations)
        code=0
    except InputError as error:
        result=dict(validation='FAIL',error=str(error),release_decision='UNKNOWN',plan=plan,raw_observations=observations)
        code=2
    with args.output.open('x') as output:output.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return code


if __name__=='__main__':raise SystemExit(main())
