"""JT's approved M4 quality rules; no provider calls or release side effects."""
import math
from fractions import Fraction
from judge import required_checks


POLICY = dict(id='JT-2026-11-04-M4', source='docs/scope.md; #495; PR518',
              completion_rate_minimum=0.90, serious_errors_maximum=0,
              first_body_p95_maximum_seconds=5, full_answer_p95_maximum_seconds=90,
              required_target_phases=['overseas_pretrip','china_travel'])

VISIBLE_PROGRESS_POLICY = dict(POLICY, id='JT-2026-11-07-M4',
    source='https://github.com/JTCAO515/G2C/issues/495#issuecomment-6708986558',
    first_visible_progress_p95_maximum_seconds=5, first_body_p95_maximum_seconds=15)
QUALITY_POLICIES = {policy['id']: policy for policy in (POLICY, VISIBLE_PROGRESS_POLICY)}

# Explicit opt-in for newly frozen plans. Historical plans keep POLICY above.
MAC_VPN_NETWORK = dict(id='JT-2026-11-06-M4-NETWORK', source='#32 JT 2026-11-06; PR568',
                      required_target_phases=['china_travel'],
                      client_device='codex_development_mac', client_location='china_mainland', vpn='on',
                      measurement_scope='user_submission_to_answer', clock='client_monotonic')


def known_reference(value):
    return (isinstance(value,str) and bool(value.strip())
            and not value.strip().upper().startswith(('UNKNOWN','UNRUN')))


def _combine(statuses):
    if 'FAIL' in statuses:
        return 'FAIL'
    if 'UNKNOWN' in statuses:
        return 'UNKNOWN'
    if 'UNRUN' in statuses:
        return 'UNRUN'
    return 'PASS'


def program_proof(row):
    """Use independent program evidence, never a model's hard-success claim."""
    verdict = row.get('judgment') or {}
    proof = row.get('independent_judgment') or {}
    program = (proof.get('kind') == 'program' and proof.get('independent') is True
               and proof.get('ref') == 'eval/judge.py')
    legacy = (not any(k in proof for k in ('kind','independent','ref'))
              and verdict.get('kind') == 'program' and verdict.get('independent') is True
              and verdict.get('ref') == 'eval/judge.py')
    return bool((program or legacy) and known_reference(row.get('raw_evidence_ref')))


def check_status(check, scenario=None):
    if check['status'] != 'PASS':
        return check['status']
    if 'actual' not in check or 'expected' not in check or check['actual'] is None:
        return 'UNKNOWN'
    actual, expected = check['actual'], check['expected']
    fixed = {}
    if scenario is not None:
        recipe = scenario.get('recipe','')
        fixed = dict(restricted_role='cj_m1_runtime',foreign_read=0,foreign_write=0,
                     unconfirmed_memory_write_count=0,original_memory_presence=1,
                     formal_write_count=1 if recipe=='accept' else 0,formal_version=1)
        if recipe.startswith('memory-'):
            fixed['persisted_memory_kind']=scenario.get('memory_kind','preference')
            fixed['persisted_memory_status']='disabled' if recipe=='memory-pause' else 'withdrawn' if recipe=='memory-stop' else 'active'
            if recipe in ('memory-pause','memory-stop'):
                fixed['current_memory_context']=[]
        fixed.update({k:dict(maximum=scenario[k]) for k in ('max_days','max_daily_items','budget_limit') if k in scenario})
        if 'transfer_minutes' in scenario:
            fixed['verified_transfer_feasibility']=False
    required_expected = fixed.get(check.get('name'),expected)
    mismatch = expected != required_expected
    expected = required_expected
    if isinstance(expected, dict) and set(expected) == {'maximum'}:
        if (type(actual) not in (int,float) or not math.isfinite(actual)
                or type(expected['maximum']) not in (int,float) or not math.isfinite(expected['maximum'])):
            return 'UNKNOWN'
        return 'FAIL' if actual > expected['maximum'] else 'UNKNOWN' if mismatch else 'PASS'
    if type(actual) is not type(expected):
        return 'UNKNOWN'
    return 'FAIL' if actual != expected else 'UNKNOWN' if mismatch else 'PASS'


def hard_status(row, scenario):
    """Check complete scenario coverage and serialized proof consistency."""
    proof = row.get('independent_judgment') or {}
    if not program_proof(row):
        return 'UNKNOWN'
    checks = proof.get('checks', [])
    if proof.get('hard_outcome') == 'FAIL' or any(check_status(c,scenario) == 'FAIL' for c in checks):
        return 'FAIL'
    required = required_checks(scenario)
    if required is None or not required <= {c.get('name') for c in checks}:
        return 'UNKNOWN'
    if any(check_status(c,scenario) != 'PASS' for c in checks):
        return 'UNKNOWN'
    return 'PASS' if proof.get('hard_outcome') == 'PASS' else 'UNKNOWN'


def _reviewed(row):
    review = row.get('serious_error_review')
    return bool(review and review['kind'] in ('human', 'program')
                and review['independent'] and known_reference(review['ref']) and review['outcome'] == 'PASS')


def _timing(stats, rows, field, limit, started):
    planned = stats['planned_n']
    # Even if every missing observation were fast, enough known slow attempts
    # can already prove the full planned population's p95 fails.
    slow = sum(r is not None and r['_measurement_available'] and r.get(field) is not None and r[field] > limit for r in rows)
    if slow > planned - math.ceil(.95 * planned):
        status = 'FAIL'
    elif stats['known_n'] != planned:
        status = 'UNKNOWN' if started else 'UNRUN'
    else:
        status = 'PASS' if stats['p95'] <= limit else 'FAIL'
    return dict(status=status, passed=True if status == 'PASS' else False if status == 'FAIL' else None,
                maximum_seconds=limit, known_slow_n=slow, **stats)


def network_status(network, network_policy=POLICY):
    proof = network.get('measurement') or {}
    if (network.get('kind') not in ('local_real_services','target_network')
            or proof.get('kind') not in ('human','program') or proof.get('independent') is not True
            or proof.get('outcome') != 'PASS' or not known_reference(proof.get('ref'))
            or not known_reference(network.get('client_environment')) or not known_reference(network.get('endpoint'))):
        return 'UNKNOWN'
    if network['kind'] == 'target_network' and network['endpoint'] != 'https://api-beta.go2china.space':
        return 'UNKNOWN'
    if network['kind'] == 'target_network' and network.get('travel_phase') not in network_policy['required_target_phases']:
        return 'UNKNOWN'
    if network['kind'] == 'target_network' and network_policy is MAC_VPN_NETWORK:
        if (any(network.get(k) != network_policy[k] for k in ('client_device','client_location','vpn'))
                or proof.get('scope') != network_policy['measurement_scope']
                or proof.get('clock') != network_policy['clock']):
            return 'UNKNOWN'
    return 'PASS'


def profile_gate(*, counts, rows, first_body, full_answer, serious_errors, real, scenarios, network,
                 network_policy=POLICY, quality_policy=POLICY, first_visible_progress=None):
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
    hard_failures = [r['raw_evidence_ref'] for r in current if hard_status(r,scenarios[r['scenario_id']]) == 'FAIL']
    hard_unknown_n = sum(hard_status(r,scenarios[r['scenario_id']]) == 'UNKNOWN' for r in current)
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
        first_body_p95=_timing(first_body, rows, 'first_body_seconds', quality_policy['first_body_p95_maximum_seconds'], started),
        full_answer_p95=_timing(full_answer, rows, 'full_answer_seconds', POLICY['full_answer_p95_maximum_seconds'], started))
    if first_visible_progress is not None:
        criteria['first_visible_progress_p95'] = _timing(first_visible_progress, rows, 'first_visible_progress_seconds',
            quality_policy['first_visible_progress_p95_maximum_seconds'], started)
    diagnostic = _combine([c['status'] for c in criteria.values()])
    net = network_status(network,network_policy)
    real_decision = _combine([diagnostic,net]) if real and started else 'UNRUN'
    return dict(criteria=criteria, diagnostic_status=diagnostic,
                network_evidence_status=net,
                evaluation_release_decision=real_decision,
                evidence_scope='real evaluation' if real else 'format-only; not a real quality conclusion')


def acceptance(profiles, plan, network_policy=POLICY, quality_policy=POLICY):
    candidates = []
    for candidate in plan['candidates']:
        groups = [p for p in profiles if p['candidate_id'] == candidate['id']]
        target = any(p['network'].get('kind') == 'target_network' for p in groups)
        phases = {p['network'].get('travel_phase') for p in groups if p['network'].get('kind')=='target_network'}
        missing = [phase for phase in network_policy['required_target_phases'] if phase not in phases]
        status = _combine([p['evaluation_release_decision'] for p in groups])
        if plan['evidence_layer'] == 'real' and missing and status != 'FAIL':
            status = 'UNKNOWN' if any(p['criteria']['completion_rate']['denominator'] for p in groups) else 'UNRUN'
        candidates.append(dict(candidate_id=candidate['id'],
                               target_network_planned=target,
                               missing_target_phases={phase:'UNRUN' for phase in missing},
                               evaluation_release_decision=status))
    reported_policy = (quality_policy if network_policy is POLICY else
                       dict(quality_policy,required_target_phases=network_policy['required_target_phases'],
                            network_policy=network_policy))
    return dict(policy=reported_policy, profiles=profiles, candidates=candidates,
                evaluation_release_decision=candidates[0]['evaluation_release_decision'] if len(candidates) == 1 else 'UNKNOWN',
                scope='M4 evaluated candidate/language/network only; does not close other release prerequisites',
                multi_candidate_rule='Never average or select the best across candidate versions')
