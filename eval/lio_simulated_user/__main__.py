"""Offline planning/reporting entry; no --real or implicit provider selection."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from .core import PERSONAS, load_profiles, plan, read_json, report


def markdown(value):
    lines = ['# #936 simulated-user report', '',
             f"Candidate: {value['candidate'] or 'UNRUN'}; evidence: {value['evidence_layer'] or 'UNRUN'}.", '',
             'G2: 0 forbidden questions. G3: at least 80% correct factors. No threshold override.', '',
             '|Scope|Planned|G2|Known / refused / inferable questions|G3|Matched / factor denominator|Unavailable factors|',
             '|---|---:|---|---|---|---|---:|']
    for label, group in [('all', value['overall']), *value['by_language'].items()]:
        counts = group['G2']['category_counts']
        lines.append(f"|{label}|{group['planned']}|{group['G2']['status']}|{counts['known']}/{counts['rejected']}/{counts['inferable']} observed|{group['G3']['status']}|{group['G3']['matched']}/{group['G3']['denominator']}|{group['G3']['unavailable']}|")
    lines += ['', '|Profile|Attempt|Outcome|G2|G3|Conservative CNY|Token estimate CNY|Actual paid CNY|',
              '|---|---:|---|---|---|---|---|---|']
    for row in value['results']:
        cost = row['cost']
        money = ['UNKNOWN' if cost[k] is None else cost[k]
                 for k in ('conservative_cny', 'token_estimate_cny', 'actual_paid_cny')]
        lines.append(f"|{row['profile_id']}|{row['attempt']}|{row['outcome']}|{row['G2']['status']}|{row['G3']['status']}|" + '|'.join(money) + '|')
    lines += ['', 'Missing attempts/factors remain in the denominator; attempts are never best-of-three.',
              'The scorer does not authenticate imported evidence. No release, cloud, real-model or App claim follows from local fixtures.', '']
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('plan', 'report'))
    p.add_argument('--profiles', type=Path, default=PERSONAS)
    p.add_argument('--traces', type=Path, nargs='*', default=[])
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    dataset, digest = load_profiles(args.profiles)
    originals = [(path, *read_json(path)) for path in args.traces]
    traces = [value for _, _, value in originals]
    if args.command == 'plan' and traces:
        p.error('plan does not consume observations')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'plan.json').write_text(json.dumps(plan(dataset, digest), ensure_ascii=False, indent=2) + '\n')
    result = report(dataset, digest, traces)
    result['source_traces'] = [dict(ref=str(path), sha256=sha256(raw).hexdigest())
                               for path, raw, _ in originals]
    (args.output / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    (args.output / 'report.md').write_text(markdown(result))
    print(json.dumps(dict(planned=result['overall']['planned'], outcomes=result['overall']['outcomes'],
                          G2=result['overall']['G2']['status'], G3=result['overall']['G3']['status'],
                          output=str(args.output)), ensure_ascii=False))


if __name__ == '__main__':
    main()
