"""Versioned evaluation inputs, simulator choices and G2/G3 accounting.

Hidden answers belong only to the simulator/scorer. A DUT receives ordinary
traveler text. This module neither authenticates nor calls a provider.
"""
from collections import Counter
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
from cj_strict_json import compact, reject_duplicates

FACTORS = ('city', 'duration_days', 'season', 'first_visit', 'party_type',
           'interests', 'pace', 'lodging_tier', 'dietary', 'must_see', 'avoid',
           'mobility', 'arrival', 'departure')
STATES = ('known', 'not_needed', 'inferred', 'default', 'from_memory')
FORBIDDEN = frozenset(('known', 'not_needed', 'inferred', 'from_memory'))
ATTEMPTS = (1, 2, 3)
DATASET_VERSION = 'LIO-simulated-users.1'
TRACE_VERSION = 'LIO-simulated-user-trace.1'
ROOT = Path(__file__).parent
PERSONAS = ROOT / 'profiles.v1.json'
SIMULATOR_SYSTEM = (
    'Simulate the traveler described in the data, not Lio. Return only JSON '
    'with answers (factor keys) and action (continue or direct). Select answers '
    'to the latest actual questions using the behavior rules. Do not disclose '
    'all hidden answers. Do not invent facts. A repeated question may receive '
    'the same answer. For direct_after, request a plan. The host renders the '
    'chosen natural traveler wording; hidden instructions never reach Lio.')


def actor_output_schema():
    """Fresh machine-readable choice shape; behavior/source checks stay in code."""
    return dict(type='object', additionalProperties=False, required=['answers', 'action'],
                properties=dict(answers=dict(type='array', maxItems=4, uniqueItems=True,
                    items=dict(type='string', enum=list(FACTORS))),
                    action=dict(type='string', enum=['continue', 'direct'])))


class InputError(ValueError):
    pass


def _nonfinite(_):
    raise InputError('nonfinite JSON')


def read_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > 4_000_000:
        raise InputError('bounded evaluation file required')
    return raw, json.loads(raw, object_pairs_hook=reject_duplicates(InputError, 'duplicate JSON field'),
                           parse_constant=_nonfinite)


def _facts(facts, text):
    if type(facts) is not list:
        raise InputError('explicit disclosed facts required')
    seen = set()
    for fact in facts:
        if (type(fact) is not dict or set(fact) != {'factor', 'value', 'state', 'quote'}
                or fact['factor'] not in FACTORS or fact['factor'] in seen
                or fact['state'] not in STATES or type(fact['quote']) is not str
                or not fact['quote'] or fact['quote'] not in text):
            raise InputError('fact must bind a unique factor and an actual utterance quote')
        seen.add(fact['factor'])


def load_profiles(path=PERSONAS):
    raw, data = read_json(path)
    if (data['version'] != DATASET_VERSION or data['issue'] != 936
            or data['attempts'] != list(ATTEMPTS) or len(data['profiles']) != 20):
        raise InputError('fixed #936 twenty-by-three dataset required')
    ids = set()
    for profile in data['profiles']:
        if (profile['id'] in ids or profile['locale'] not in ('zh', 'en')
                or set(profile['hidden_answers']) != set(FACTORS)
                or profile['hidden_answers']['city']['value'] != profile['city']
                or not profile['opening']):
            raise InputError('unique single-city persona with all hidden factor answers required')
        ids.add(profile['id'])
        _facts(profile['initial_disclosures'], profile['opening'])
        for factor, answer in profile['hidden_answers'].items():
            if (set(answer) != {'value', 'state', 'text'} or answer['state'] not in STATES
                    or not isinstance(answer['text'], str) or not answer['text']):
                raise InputError('bounded natural-language hidden answer required')
        behavior = profile['behavior']
        if (behavior['reply_style'] not in ('brief', 'full', 'partial', 'proactive')
                or type(behavior['direct_after']) is not int
                or not 1 <= behavior['direct_after'] <= 4):
            raise InputError('explicit simulator behavior required')
    if Counter(p['locale'] for p in data['profiles']) != {'zh': 10, 'en': 10}:
        raise InputError('ten Chinese and ten English profiles required')
    return data, sha256(raw).hexdigest()


def plan(dataset, dataset_sha256):
    return dict(version='LIO-simulated-user-plan.1', issue=936, dataset_sha256=dataset_sha256,
                specification='https://github.com/JTCAO515/G2C/issues/922',
                thresholds=dict(G2_max_forbidden_questions=0, G3_min_factor_percent=80),
                slots=[dict(profile_id=p['id'], locale=p['locale'], attempt=a)
                       for p in dataset['profiles'] for a in ATTEMPTS])


def simulator_messages(profile, public_history, attempt):
    """Only an approved simulator host may consume this hidden-side payload.

    The model selects answer keys; code renders the dataset's natural wording.
    This makes disclosure fidelity verifiable without a model judging itself.
    """
    if attempt not in ATTEMPTS:
        raise InputError('fixed attempt required')
    return [dict(role='system', content=SIMULATOR_SYSTEM),
        dict(role='user', content=compact(dict(profile=profile, history=public_history,
             attempt=attempt)).decode('utf-8'))]


def render_choice(profile, choice, questions, round_number):
    """Validate the simulator boundary, then release only ordinary traveler text."""
    if (type(choice) is not dict or set(choice) != {'answers', 'action'}
            or choice['action'] not in ('continue', 'direct')
            or type(choice['answers']) is not list
            or any(type(k) is not str or k not in FACTORS for k in choice['answers'])
            or len(set(choice['answers'])) != len(choice['answers'])):
        raise InputError('invalid simulator selection')
    if type(round_number) is not int or round_number < 1:
        raise InputError('positive simulator round required')
    keys = choice['answers']
    if len(keys) > 4:
        raise InputError('incremental disclosure permits at most four answers')
    asked = None if questions is None else {q['factor'] for q in questions}
    style = profile['behavior']['reply_style']
    if style != 'proactive' and asked is not None and not set(keys) <= asked:
        raise InputError('simulator disclosed an unasked factor')
    if style == 'brief' and len(keys) > 1:
        raise InputError('brief simulator answered more than one factor')
    if style == 'partial' and len(keys) > (2 if asked is None else max(1, len(asked) // 2)):
        raise InputError('partial simulator answered too many factors')
    if choice['action'] == 'continue' and asked:
        if not keys or style == 'full' and set(keys) != asked:
            raise InputError('simulator did not follow its declared answer behavior')
    if round_number >= profile['behavior']['direct_after'] and choice['action'] != 'direct':
        raise InputError('simulator did not honor its declared exit behavior')
    if round_number < profile['behavior']['direct_after'] and choice['action'] == 'direct':
        raise InputError('simulator exited before its declared behavior point')
    pieces, facts = [], []
    for key in keys:
        answer = profile['hidden_answers'][key]
        pieces.append(answer['text'])
        facts.append(dict(factor=key, value=answer['value'], state=answer['state'], quote=answer['text']))
    if choice['action'] == 'direct':
        pieces.append('直接出方案。' if profile['locale'] == 'zh' else 'Please give me a plan now.')
    if not pieces:
        pieces.append('请继续。' if profile['locale'] == 'zh' else 'Please continue.')
    return dict(speaker='user', text=' '.join(pieces), disclosures=facts)


def _visible_disclosures(profile, turn, first):
    """Derive the oracle from actual released wording, not actor annotations."""
    if first:
        if turn['text'] != profile['opening']:
            raise InputError('trajectory must start with the fixed public opening')
        expected = profile['initial_disclosures']
    else:
        remaining = turn['text']
        expected = []
        for factor, answer in profile['hidden_answers'].items():
            if answer['text'] in remaining:
                expected.append(dict(factor=factor, value=answer['value'], state=answer['state'], quote=answer['text']))
                remaining = remaining.replace(answer['text'], '')
        for control in ('直接出方案。', 'Please give me a plan now.', '请继续。', 'Please continue.'):
            remaining = remaining.replace(control, '')
        if remaining.strip():
            raise InputError('simulator wording outside the declared answer/control vocabulary')
    if {x['factor']: x for x in turn['disclosures']} != {x['factor']: x for x in expected}:
        raise InputError('disclosure annotation omitted or changed an actual answer')
    return expected


def _update(known, facts):
    # The oracle tracks what the traveler actually disclosed, never all hidden
    # answers. Inference must not replace an explicit statement/refusal.
    for fact in facts:
        previous = known.get(fact['factor'])
        if (fact['state'] == 'inferred' and previous is not None
                and previous['state'] in ('known', 'not_needed', 'from_memory')):
            continue
        known[fact['factor']] = fact


def _same(value, expected, factor):
    if factor in ('interests', 'must_see', 'avoid'):
        return (type(value) is list and type(expected) is list
                and all(type(v) is str for v in value + expected) and sorted(value) == sorted(expected))
    # JSON booleans must not equal integer factor values.
    return type(value) is type(expected) and value == expected


def assess(profile, trace):
    known = {}
    violations, questions_seen = [], 0
    memory = trace.get('memory_observation')
    question_complete = False
    if memory is not None:
        if (memory['origin'] not in ('accepted_injected', 'fixture', 'advisory', 'unavailable')
                or type(memory['complete']) is not bool or not memory['ref']):
            raise InputError('explicit original injected-memory observation required')
        if memory['origin'] == 'fixture' and trace['evidence_layer'] != 'L0':
            raise InputError('fixture memory cannot certify L1/L2')
        if memory['complete'] and memory['origin'] not in ('accepted_injected', 'fixture'):
            raise InputError('advisory memory cannot prove complete known factors')
        _facts(memory['facts'], memory['text'])
        if any(fact['state'] != 'from_memory' for fact in memory['facts']):
            raise InputError('injected-memory facts must retain their source state')
        if memory['origin'] in ('accepted_injected', 'fixture'):
            _update(known, memory['facts'])
        question_complete = memory['complete']
    final_profile = None
    final_profile_complete = False
    terminal = False
    user_seen = False
    expected_speaker = 'user'
    for index, turn in enumerate(trace['turns']):
        if terminal or turn['speaker'] != expected_speaker:
            raise InputError('one alternating dialogue ending at its first exploration boundary required')
        expected_speaker = 'assistant' if turn['speaker'] == 'user' else 'user'
        if type(turn['text']) is not str or not turn['text'].strip():
            raise InputError('original turn text required')
        if turn['speaker'] == 'user':
            _facts(turn['disclosures'], turn['text'])
            _update(known, _visible_disclosures(profile, turn, not user_seen))
            user_seen = True
            continue
        if not user_seen:
            raise InputError('assistant observation cannot precede the public opening')
        if turn['speaker'] != 'assistant':
            raise InputError('original user/assistant turn required')
        if (type(turn['questions_complete']) is not bool or type(turn['profile_complete']) is not bool
                or type(turn['questions']) is not list):
            raise InputError('explicit observation completeness required')
        question_origin = turn['question_evidence']
        profile_origin = turn['profile_evidence']
        if (question_origin not in ('native_structured', 'independent_annotation', 'advisory', 'unavailable', 'fixture')
                or profile_origin not in ('accepted_context', 'accepted_partial', 'advisory', 'unavailable', 'fixture')):
            raise InputError('explicit observer origin required')
        if ((question_origin == 'fixture' or profile_origin == 'fixture') and trace['evidence_layer'] != 'L0'):
            raise InputError('checker fixtures cannot certify L1/L2 observations')
        if (turn['questions_complete'] and question_origin not in ('native_structured', 'independent_annotation', 'fixture')
                or turn['profile_complete'] and profile_origin not in ('accepted_context', 'fixture')):
            raise InputError('advisory/unavailable data cannot certify a complete observation')
        question_complete &= turn['questions_complete']
        if not turn['observation_ref']:
            raise InputError('native/annotation observation reference required')
        question_spans = set()
        for question in turn['questions']:
            factor, start, end = question['factor'], question['start'], question['end']
            if (factor not in FACTORS or type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(turn['text'])):
                raise InputError('question must bind actual answer span and known factor')
            identity = factor, start, end
            if identity in question_spans:
                raise InputError('duplicate question annotation')
            question_spans.add(identity)
            questions_seen += 1
            if factor in known and known[factor]['state'] in FORBIDDEN:
                violations.append(dict(turn=index, factor=factor, reason=known[factor]['state'],
                                       question=turn['text'][start:end], source=known[factor]['quote']))
        if type(turn['exploration_complete']) is not bool:
            raise InputError('explicit observed exploration boundary required')
        if turn['exploration_complete']:
            terminal = True
            final_profile = turn['profile']
            final_profile_complete = turn['profile_complete']
    complete = trace['outcome'] == 'completed' and terminal
    g2 = ('FAIL' if violations else 'PASS' if complete and question_complete else 'UNKNOWN')
    matches, incorrect, unavailable = [], [], []
    if final_profile is not None and type(final_profile) is not dict:
        raise InputError('observed profile must be an object or unavailable')
    for factor, answer in profile['hidden_answers'].items():
        actual = None if final_profile is None else final_profile.get(factor)
        if actual is None:
            (incorrect if final_profile_complete and complete else unavailable).append(factor)
        elif (type(actual) is not dict or actual.get('state') not in STATES or 'value' not in actual):
            raise InputError('versioned normalized profile observation required')
        elif _same(actual['value'], answer['value'], factor):
            matches.append(factor)
        else:
            incorrect.append(factor)
    diagnostic = dict(matched_factors=matches, incorrect_factors=incorrect)
    if not complete or not final_profile_complete:
        # An advisory extractor or incomplete projection is not the accepted
        # end-of-exploration profile, even when its values happen to match.
        matches, incorrect, unavailable = [], [], list(FACTORS)
    maximum = len(matches) + len(unavailable)
    g3 = ('FAIL' if maximum * 100 < 80 * len(FACTORS) else
          'UNKNOWN' if not complete or unavailable else
          'PASS' if len(matches) * 100 >= 80 * len(FACTORS) else 'FAIL')
    categories = dict(known=sum(v['reason'] in ('known', 'from_memory') for v in violations),
                      rejected=sum(v['reason'] == 'not_needed' for v in violations),
                      inferable=sum(v['reason'] == 'inferred' for v in violations))
    return dict(outcome=trace['outcome'], G2=dict(status=g2, forbidden_question_count=len(violations),
                category_counts=categories,
                observed_questions=questions_seen, observation_complete=question_complete and complete,
                violations=violations), G3=dict(status=g3, matched=len(matches), denominator=len(FACTORS),
                matched_factors=matches, incorrect_factors=incorrect, unavailable_factors=unavailable,
                diagnostic_unconfirmed_profile=diagnostic if unavailable else None,
                factor_percent=str(Decimal(len(matches)) * 100 / len(FACTORS)) if not unavailable and complete else None))


def report(dataset, dataset_sha256, traces):
    frozen = plan(dataset, dataset_sha256)
    by_id = {p['id']: p for p in dataset['profiles']}
    observations = {}
    candidate = layer = None
    for trace in traces:
        if trace['version'] != TRACE_VERSION or trace['dataset_sha256'] != dataset_sha256:
            raise InputError('trace does not bind this frozen dataset/version')
        key = (trace['profile_id'], trace['attempt'])
        if key[0] not in by_id or type(key[1]) is not int or key[1] not in ATTEMPTS or key in observations:
            raise InputError('foreign, duplicate or replacement attempt')
        if trace['outcome'] not in ('completed', 'failed', 'unknown'):
            raise InputError('actual completed/failed/unknown outcome required')
        if trace['evidence_layer'] not in ('L0', 'L1', 'L2') or not trace['candidate']:
            raise InputError('actual evidence layer and fixed candidate required')
        identity = (trace['candidate'], trace['evidence_layer'])
        if candidate is not None and identity != (candidate, layer):
            raise InputError('cannot pool candidates or evidence layers')
        candidate, layer = identity
        observations[key] = trace
    rows = []
    for slot in frozen['slots']:
        key = (slot['profile_id'], slot['attempt'])
        trace = observations.get(key)
        result = dict(outcome='UNRUN', G2=dict(status='UNRUN', forbidden_question_count=None,
                      category_counts=dict(known=None, rejected=None, inferable=None)),
                      G3=dict(status='UNRUN', matched=0, denominator=len(FACTORS),
                              unavailable_factors=list(FACTORS))) if trace is None else assess(by_id[key[0]], trace)
        # Monetary observations are original accounting inputs; never invent a
        # zero amount for absent paid evidence or create another spending ledger.
        result['cost'] = dict(conservative_cny=None, token_estimate_cny=None, actual_paid_cny=None) if trace is None else trace['cost']
        if set(result['cost']) != {'conservative_cny', 'token_estimate_cny', 'actual_paid_cny'}:
            raise InputError('all three distinct cost columns required')
        for amount in result['cost'].values():
            if amount is not None and (type(amount) is not str or len(amount) > 64
                    or re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', amount) is None):
                raise InputError('cost must be an exact nonnegative decimal string or unavailable')
        result['evidence_refs'] = ([] if trace is None else
            [turn['observation_ref'] for turn in trace['turns'] if turn['speaker'] == 'assistant'])
        result['end_reason'] = None if trace is None else trace.get('end_reason')
        result['failure_owner'] = None if trace is None else trace.get('failure_owner')
        result['accounting_status'] = 'UNRUN' if trace is None else trace.get('accounting_status', 'provided')
        rows.append(dict(slot, **result))

    def group(values):
        states = Counter(v['outcome'] for v in values)
        denominator = len(values) * len(FACTORS)
        matched = sum(v['G3']['matched'] for v in values)
        unavailable = sum(len(v['G3']['unavailable_factors']) for v in values)
        violation = sum(v['G2']['forbidden_question_count'] or 0 for v in values)
        categories = {key: sum(v['G2']['category_counts'][key] or 0 for v in values)
                      for key in ('known', 'rejected', 'inferable')}
        g2 = 'FAIL' if violation else 'PASS' if all(v['G2']['status'] == 'PASS' for v in values) else 'UNRUN' if states['UNRUN'] == len(values) else 'UNKNOWN'
        g3 = ('FAIL' if (matched + unavailable) * 100 < 80 * denominator else 'UNRUN' if states['UNRUN'] == len(values)
              else 'UNKNOWN' if unavailable or any(v['G3']['status'] in ('UNKNOWN', 'UNRUN') for v in values)
              else 'PASS' if matched * 100 >= 80 * denominator else 'FAIL')
        costs = {}
        for key in ('conservative_cny', 'token_estimate_cny', 'actual_paid_cny'):
            amounts = [v['cost'].get(key) for v in values]
            costs[key] = dict(known_subtotal=str(sum((Decimal(x) for x in amounts if x is not None), Decimal(0))),
                              unknown_or_unrun=sum(x is None for x in amounts),
                              total=None if any(x is None for x in amounts) else str(sum(map(Decimal, amounts))))
        return dict(planned=len(values), outcomes=dict(states), G2=dict(status=g2,
                    forbidden_question_count=violation, category_counts=categories),
                    G3=dict(status=g3, matched=matched, denominator=denominator, unavailable=unavailable,
                            factor_percent=None if unavailable else str(Decimal(matched) * 100 / denominator)), costs=costs)
    return dict(version='LIO-simulated-user-report.1', plan=frozen, candidate=candidate,
                evidence_layer=layer, overall=group(rows), by_language={lang: group([r for r in rows if r['locale'] == lang])
                for lang in ('zh', 'en')}, results=rows, product_release='UNRUN',
                note='Baseline measurements are not release approval; fixtures are not real-model quality.')
