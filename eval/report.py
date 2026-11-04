"""Reuse the accepted CJ028 matrix/cost/UNKNOWN accounting, adding call counts."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'evaluation/cj028'))
from evaluate import summarize, latency, require, number


def report(plan, observations):
    for row in observations:
        calls = row.get('model_calls')
        require(calls is None or type(calls) is int and calls >= 0, 'model_calls must be a nonnegative integer or null')
        elapsed = row.get('api_task_seconds')
        require(elapsed is None or number(elapsed), 'invalid API task latency')
    result = summarize(plan, observations)
    for group in result['groups']:
        rows = [a['observation'] for a in group['attempts']]
        counts = [r.get('model_calls') for r in rows if r is not None]
        group['model_calls'] = dict(known_total=sum(c for c in counts if c is not None),
                                    known_attempt_n=sum(c is not None for c in counts),
                                    unknown_or_unrun_attempt_n=len(rows)-sum(c is not None for c in counts))
        group['api_task_seconds'] = latency(rows, 'api_task_seconds')
        group['latency_scope'] = 'signed API submit through original worker and final authoritative read; not UI first-body timing'
        def hard(row):
            if row is None or row['status']=='missing': return 'UNRUN'
            verdict=row.get('judgment',{})
            if (verdict.get('kind')!='program' or verdict.get('independent') is not True
                    or verdict.get('ref')!='eval/judge.py' or not row.get('raw_evidence_ref')):
                return 'UNKNOWN'
            value=row.get('independent_judgment',{}).get('hard_outcome')
            return value if value in ('PASS','FAIL','UNKNOWN') else 'UNKNOWN'
        group['hard_outcomes'] = {status:sum(hard(r)==status for r in rows)
                                  for status in ('PASS','FAIL','UNKNOWN','UNRUN')}
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
