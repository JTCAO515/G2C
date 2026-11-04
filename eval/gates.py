"""JT's approved M4 quality rules; no provider calls or release side effects."""
import math
from fractions import Fraction


POLICY = dict(id='JT-2026-11-04-M4', source='docs/scope.md; #495; PR518',
              completion_rate_minimum=0.90, serious_errors_maximum=0,
              first_body_p95_maximum_seconds=5, full_answer_p95_maximum_seconds=90)


def _combine(statuses):
    if 'FAIL' in statuses:
        return 'FAIL'
    if 'UNKNOWN' in statuses:
        return 'UNKNOWN'
    if 'UNRUN' in statuses:
        return 'UNRUN'
    return 'PASS'


def hard_status(row):
    """Use independent program evidence, never a model's hard-success claim."""
    verdict = row.get('judgment', {})
    proof = row.get('independent_judgment', {})
    program = (proof.get('kind') == 'program' and proof.get('independent') is True
               and proof.get('ref') == 'eval/judge.py')
    legacy = (not any(k in proof for k in ('kind','independent','ref'))
              and verdict.get('kind') == 'program' and verdict.get('independent') is True
              and verdict.get('ref') == 'eval/judge.py')
    if not (program or legacy) or not row.get('raw_evidence_ref'):
        return 'UNKNOWN'
    checks = proof.get('checks', [])
    if proof.get('hard_outcome') == 'FAIL' or any(c['status'] == 'FAIL' for c in checks):
        return 'FAIL'
    if not checks or any(c['status'] != 'PASS' for c in checks):
        return 'UNKNOWN'
    return 'PASS' if proof.get('hard_outcome') == 'PASS' else 'UNKNOWN'


def _reviewed(row):
    review = row.get('serious_error_review')
    return bool(review and review['kind'] in ('human', 'program')
                and review['independent'] and review['ref'] and review['outcome'] == 'PASS')


def _timing(stats, rows, field, limit, started):
    planned = stats['planned_n']
    # Even if every missing observation were fast, enough known slow attempts
    # can already prove the full planned population's p95 fails.
    slow = sum(r is not None and r.get(field) is not None and r[field] > limit for r in rows)
    if slow > planned - math.ceil(.95 * planned):
        status = 'FAIL'
    elif stats['known_n'] != planned:
        status = 'UNKNOWN' if started else 'UNRUN'
    else:
        status = 'PASS' if stats['p95'] <= limit else 'FAIL'
    return dict(status=status, passed=True if status == 'PASS' else False if status == 'FAIL' else None,
                maximum_seconds=limit, known_slow_n=slow, **stats)


def profile_gate(*, counts, rows, first_body, full_answer, serious_errors, real):
    planned = len(rows)
    started = planned - counts['UNRUN']
    minimum = Fraction(str(POLICY['completion_rate_minimum']))
    if not started:
        completion = 'UNRUN'
    elif counts['PASS'] * minimum.denominator < started * minimum.numerator:
        completion = 'FAIL'
    elif started != planned:
        completion = 'UNKNOWN'
    else:
        completion = 'PASS'
    current = [r for r in rows if r is not None]
    hard_failures = [r['raw_evidence_ref'] for r in current if hard_status(r) == 'FAIL']
    hard_unknown_n = sum(hard_status(r) == 'UNKNOWN' for r in current)
    reviewed = sum(_reviewed(r) for r in current)
    review_failures = [r['serious_error_review']['ref'] for r in current
                      if r.get('serious_error_review') and r['serious_error_review']['kind'] in ('human', 'program')
                      and r['serious_error_review']['independent'] and r['serious_error_review']['outcome'] == 'FAIL']
    # A resolved flag does not erase a serious error seen at this same candidate.
    if serious_errors or hard_failures or review_failures:
        severe = 'FAIL'
    elif not started:
        severe = 'UNRUN'
    elif reviewed != planned or hard_unknown_n or started != planned:
        severe = 'UNKNOWN'
    else:
        severe = 'PASS'
    criteria = dict(
        completion_rate=dict(status=completion, passed=True if completion == 'PASS' else False if completion == 'FAIL' else None,
                             minimum=POLICY['completion_rate_minimum'], numerator=counts['PASS'], denominator=started,
                             value=counts['PASS'] / started if started else None, planned_n=planned,
                             **counts),
        serious_errors=dict(status=severe, passed=True if severe == 'PASS' else False if severe == 'FAIL' else None,
                            maximum=POLICY['serious_errors_maximum'], observed_n=len(serious_errors), errors=serious_errors,
                            hard_failure_refs=hard_failures, review_failure_refs=review_failures,
                            reviewed_n=reviewed, hard_unknown_n=hard_unknown_n, planned_n=planned),
        first_body_p95=_timing(first_body, rows, 'first_body_seconds', POLICY['first_body_p95_maximum_seconds'], started),
        full_answer_p95=_timing(full_answer, rows, 'full_answer_seconds', POLICY['full_answer_p95_maximum_seconds'], started))
    diagnostic = _combine([c['status'] for c in criteria.values()])
    return dict(criteria=criteria, diagnostic_status=diagnostic,
                evaluation_release_decision=diagnostic if real else 'UNRUN',
                evidence_scope='real evaluation' if real else 'format-only; not a real quality conclusion')


def acceptance(profiles, plan):
    candidates = []
    for candidate in plan['candidates']:
        groups = [p for p in profiles if p['candidate_id'] == candidate['id']]
        candidates.append(dict(candidate_id=candidate['id'],
                               evaluation_release_decision=_combine([p['evaluation_release_decision'] for p in groups])))
    return dict(policy=POLICY, profiles=profiles, candidates=candidates,
                evaluation_release_decision=candidates[0]['evaluation_release_decision'] if len(candidates) == 1 else 'UNKNOWN',
                scope='M4 evaluated candidate/language/network only; does not close other release prerequisites',
                multi_candidate_rule='Never average or select the best across candidate versions')
