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


def markdown(result):
    lines = ['# G2C M4 evaluation', '',
             f"Dataset: {result['plan']['sample_set_version']}",
             f"Product scenarios: {result['independent_product_scenario_n']}; fixed holdout: {result['holdout_product_scenario_n']}",
             f"Release: {result['release_decision']} (thresholds, real services and target networks remain separate)", '',
             '| Language | Network | Split | Task | N | PASS | FAIL | UNKNOWN | UNRUN | PASS / started | API p50 / p95 (s) | Model calls known / unknown attempts |',
             '|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|']
    for group in result['groups']:
        counts = group['outcomes']; elapsed = group['api_task_seconds']; calls = group['model_calls']
        lines.append(f"| {group['language']} | {group['network_id']} | {group['split']} | {group['task_kind']} | "
                     f"{group['planned_attempt_n']} | {counts['PASS']} | {counts['FAIL']} | {counts['UNKNOWN']} | {counts['UNRUN']} | "
                     f"{group['pass_rate']['numerator']} / {group['pass_rate']['denominator']} | "
                     f"{elapsed['p50']} / {elapsed['p95']} | {calls['known_total']} / {calls['unknown_or_unrun_attempt_n']} |")
    lines += ['', 'API latency includes the scenario\'s signed operations, original worker and final authoritative read; it is not UI first-body latency.',
              'Unavailable first-body/draft visibility and missing networks stay UNKNOWN/UNRUN. Repeated attempts are separate rows in report.json.',
              'Cost details retain known currency subtotals and incomplete-attempt counts in report.json; absent monetary receipts are UNKNOWN.', '',
              f"Serious errors: {len(result['serious_errors'])}. An unresolved serious error cannot be cancelled by a mean or another language.", '']
    for error in result['serious_errors']:
        lines.append(f"- {error['attempt_key']}: {error['description']} (resolved={error['resolved']})")
    return '\n'.join(lines) + '\n'


def main():
    import argparse,json
    from evaluate import read_json,InputError
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--observations',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--markdown',type=Path)
    args=parser.parse_args()
    plan=read_json(args.plan.read_bytes());observations=read_json(args.observations.read_bytes())
    try:
        result=report(plan,observations)
        code=0
    except InputError as error:
        result=dict(validation='FAIL',error=str(error),release_decision='UNKNOWN',plan=plan,raw_observations=observations)
        code=2
    with args.output.open('x') as output:output.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if args.markdown and code==0:
        with args.markdown.open('x') as output:output.write(markdown(result))
    return code


if __name__=='__main__':raise SystemExit(main())
