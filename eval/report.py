"""Reuse the accepted CJ028 matrix/cost/UNKNOWN accounting, adding call counts."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'evaluation/cj028'))
from evaluate import summarize, latency, require, number, amount, exact_sum, nonempty
from gates import profile_gate, acceptance, hard_status


def real_fees(rows):
    subtotals = {basis: {} for basis in ('billed', 'estimated', 'reserved')}
    complete = 0
    unknown_components = 0
    for row in rows:
        cost = row.get('cost') if row else None
        if cost is None:
            continue
        all_billed = bool(cost['components'])
        for component in cost['components']:
            basis = component.get('basis')
            known = component.get('amount') is not None
            if basis == 'billed' and not nonempty(component.get('receipt_ref')):
                basis = None
            if basis in subtotals and known:
                subtotals[basis].setdefault(component['currency'], []).append(amount(component['amount']))
            else:
                unknown_components += 1
            all_billed = all_billed and basis == 'billed' and known
        complete += bool(cost['complete'] and all_billed)
    return dict(status='PASS' if complete == len(rows) else 'UNKNOWN',
                subtotals_by_basis={basis: {currency: str(exact_sum(values)) for currency, values in totals.items()}
                                   for basis, totals in subtotals.items()},
                complete_billed_attempt_n=complete, unknown_or_missing_attempt_n=len(rows)-complete,
                unknown_component_n=unknown_components, planned_attempt_n=len(rows),
                note='Reported fee provenance only; estimates/reservations are not actual bills or dispatch authorization')


def report(plan, observations):
    result = summarize(plan, observations)
    for row in observations:
        for field in ('model_calls', 'tool_calls', 'memory_calls'):
            calls = row.get(field)
            require(calls is None or type(calls) is int and calls >= 0, field+' must be a nonnegative integer or null')
        for field in ('api_task_seconds', 'full_answer_seconds'):
            elapsed = row.get(field)
            require(elapsed is None or number(elapsed), 'invalid '+field)
        review = row.get('serious_error_review')
        if review is not None:
            require(isinstance(review, dict) and review.get('kind') in ('human','program','model')
                    and type(review.get('independent')) is bool and nonempty(review.get('ref'))
                    and review.get('outcome') in ('PASS','FAIL','UNKNOWN'), 'invalid serious error review')
        proof = row.get('independent_judgment')
        if proof is not None:
            require(isinstance(proof, dict), 'invalid independent judgment')
            checks = proof.get('checks', [])
            require(isinstance(checks, list) and all(isinstance(c, dict) and c.get('status') in ('PASS','FAIL','UNKNOWN') for c in checks),
                    'invalid independent program checks')
        cost = row.get('cost')
        for component in cost['components'] if cost is not None else []:
            require(component.get('basis') is None or isinstance(component['basis'], str), 'invalid fee basis')
            require(component.get('receipt_ref') is None or nonempty(component['receipt_ref']), 'invalid fee receipt ref')
    for group in result['groups']:
        rows = [a['observation'] for a in group['attempts']]
        counts = [r.get('model_calls') for r in rows if r is not None]
        group['model_calls'] = dict(known_total=sum(c for c in counts if c is not None),
                                    known_attempt_n=sum(c is not None for c in counts),
                                    unknown_or_unrun_attempt_n=len(rows)-sum(c is not None for c in counts))
        group['api_task_seconds'] = latency(rows, 'api_task_seconds')
        group['full_answer_seconds'] = latency([r if r is not None and r['status']!='missing' else None for r in rows], 'full_answer_seconds')
        group['latency_scope'] = 'signed API submit through original worker and final authoritative read; not UI first-body timing'
        def hard(row):
            if row is None or row['status']=='missing': return 'UNRUN'
            return hard_status(row)
        group['hard_outcomes'] = {status:sum(hard(r)==status for r in rows)
                                  for status in ('PASS','FAIL','UNKNOWN','UNRUN')}
    profiles = []
    for candidate in plan['candidates']:
        for language in ('zh','en'):
            for network in plan['networks']:
                groups = [g for g in result['groups'] if g['candidate_id']==candidate['id']
                          and g['language']==language and g['network_id']==network['id']]
                rows = [a['observation'] for g in groups for a in g['attempts']]
                # Missing observations never contribute timing or money, even if
                # an externally supplied 'missing' record contains other fields.
                rows = [r if r is not None and r['status']!='missing' else None for r in rows]
                counts = {s:sum(g['outcomes'][s] for g in groups) for s in ('PASS','FAIL','UNKNOWN','UNRUN')}
                errors = [e for g in groups for e in g['serious_errors']]
                profile = dict(candidate_id=candidate['id'],language=language,network_id=network['id'],network=network,
                               outcomes=counts,planned_attempt_n=len(rows),
                               real_fees=real_fees(rows),
                               **profile_gate(counts=counts,rows=rows,first_body=latency(rows,'first_body_seconds'),
                                              full_answer=latency(rows,'full_answer_seconds'),serious_errors=errors,
                                              real=plan['evidence_layer']=='real'))
                profile['call_volume'] = {}
                for field in ('model_calls','tool_calls','memory_calls'):
                    values = [r.get(field) for r in rows if r is not None]
                    profile['call_volume'][field] = dict(known_total=sum(v for v in values if v is not None),
                        known_attempt_n=sum(v is not None for v in values),
                        unknown_or_missing_attempt_n=len(rows)-sum(v is not None for v in values))
                profiles.append(profile)
    result['quality_acceptance'] = acceptance(profiles,plan)
    # Preserve the original plan and global release authority distinction, while
    # removing the old reporter's now-superseded unconfirmed-threshold notice.
    result['release_blockers'] = [reason for reason in result['release_blockers'] if reason != 'thresholds unconfirmed']
    return result


def markdown(result):
    lines = ['# G2C M4 evaluation', '',
             f"Dataset: {result['plan']['sample_set_version']}",
             f"Product scenarios: {result['independent_product_scenario_n']}; fixed holdout: {result['holdout_product_scenario_n']}",
             f"Evaluation quality decision: {result['quality_acceptance']['evaluation_release_decision']}",
             f"Other release prerequisites: {result['release_decision']}",
             'JT 2026-11-04: each language completion >=90%, serious errors0, first-body p95<=5s, full-answer p95<=90s.', '',
             '| Candidate | Language | Network | Completion | Serious errors | First-body p95 | Full-answer p95 | Real quality decision |',
             '|---|---|---|---|---|---|---|---|']
    for profile in result['quality_acceptance']['profiles']:
        c=profile['criteria']; rate=c['completion_rate']
        lines.append(f"| {profile['candidate_id']} | {profile['language']} | {profile['network_id']} | "
                     f"{rate['status']} {rate['numerator']}/{rate['denominator']} | "
                     f"{c['serious_errors']['status']} n={c['serious_errors']['observed_n']} | "
                     f"{c['first_body_p95']['status']} {c['first_body_p95']['p95']}s | "
                     f"{c['full_answer_p95']['status']} {c['full_answer_p95']['p95']}s | {profile['evaluation_release_decision']} |")
    lines += ['', '| Language | Network | Actual billed currency subtotals | Estimated / reserved | Fee completeness | Model / tool / memory calls (known; unknown attempts) |',
              '|---|---|---|---|---|---|']
    for profile in result['quality_acceptance']['profiles']:
        fees=profile['real_fees']; totals=fees['subtotals_by_basis']
        volume=profile['call_volume']
        counts=' / '.join(f"{volume[k]['known_total']}; {volume[k]['unknown_or_missing_attempt_n']} UNKNOWN" for k in ('model_calls','tool_calls','memory_calls'))
        lines.append(f"| {profile['language']} | {profile['network_id']} | {totals['billed'] or 'UNKNOWN'} | "
                     f"{totals['estimated'] or 'UNKNOWN'} / {totals['reserved'] or 'UNKNOWN'} | "
                     f"{fees['status']}, {fees['unknown_or_missing_attempt_n']} unknown/missing attempts | {counts} |")
    lines += ['', 'Fake/local/synthetic rows validate formatting only; their real quality decision is UNRUN.', '',
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
