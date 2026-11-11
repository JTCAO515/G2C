"""Lio v2 scoring. v1 remains a frozen historical scoring interface."""
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path

from evaluation.cj028.evaluate import fields, nonempty, read_json, require
from . import score as legacy

VERSION = 'G2C-dialogue-score.2'
DATASET_VERSION = 'G2C-dialogue-cases.2'
MUTATION_TASKS = {'dev-local-edit', 'val-undo', 'val-confirm-save'}
REVISED_TASKS = MUTATION_TASKS | {'dev-required-date', 'dev-tool-failure'}
MUTATION_RULES = {
    'local_edit': dict(before_formal_version=1, formal_trip_version=2, write_commits=1, locked_items_changed=0, unrelated_trip_mutations=0),
    'undo': dict(before_formal_version=2, formal_trip_version=3, write_commits=1,
                 undo_commits=1, undo_target_version=1, locked_items_changed=0, unrelated_trip_mutations=0),
    'save': dict(before_formal_version=0, formal_trip_version=1, write_commits=1,
                 discussion_turns_observed=2, discussion_write_commits=0, unrelated_trip_mutations=0),
}
MUTATION_FIELDS = {
    'before_formal_version', 'formal_trip_version', 'write_commits', 'discussion_turns_observed',
    'discussion_write_commits', 'undo_commits', 'undo_target_version', 'locked_items_changed',
    'before_trip_id', 'formal_trip_id', 'receipt_trip_id', 'receipt_version',
    'request_message_id', 'committed_message_id', 'request_run_id', 'committed_run_id',
    'request_action_id', 'receipt_action_id', 'formal_content_sha256', 'operation_content_sha256',
    'history_before', 'history_after', 'unrelated_trip_mutations', 'weather_request_day', 'weather_query_day',
}
EFFECT_PROOFS = {name: proof for name, proof in legacy.EFFECT_PROOFS.items()
                 if name not in ('trip_saved', 'draft_undone')}
EFFECT_PROOFS.update(
    trip_saved=dict(formal_trip_count=1, write_commits=1),
    trip_updated=dict(formal_trip_count=1, write_commits=1),
    trip_undone=dict(formal_trip_count=1, write_commits=1, undo_commits=1),
)
WRITE_PROOF_NAMES = {
    'formal_version', 'before_formal_version', 'write_commits', 'receipt_version',
    'existing_trip_identity', 'receipt_trip_binding', 'operation_message_binding',
    'operation_run_binding', 'undo_action_binding', 'committed_operation_bytes',
    'current_history_bytes', 'undo_restored_content', 'undo_target_version',
}


def dataset():
    raw = Path(__file__).with_name('cases.v2.json').read_bytes()
    document = read_json(raw)
    require(document['version'] == DATASET_VERSION, 'unsupported v2 dataset version')
    old, _ = legacy.dataset()
    require([(t['id'], t['split'], t['trip_family']) for t in document['tasks']] ==
            [(t['id'], t['split'], t['trip_family']) for t in old['tasks']],
            'v2 task allocation differs from the retained v1 denominator')
    for task in document['tasks']:
        require(set(task['variants']) == set(legacy.LANGUAGES), 'task needs both languages')
        for variant in task['variants'].values():
            if task['id'] not in MUTATION_TASKS:
                require('steps' not in variant and type(variant['turns']) is list and bool(variant['turns'])
                        and all(nonempty(turn) for turn in variant['turns']), 'invalid retained task turns')
                continue
            require('turns' not in variant and type(variant['steps']) is list and bool(variant['steps']),
                    'native task steps are required')
            for step in variant['steps']:
                require(type(step) is dict and 'kind' in step, 'invalid task step')
                if step['kind'] == 'message':
                    fields(step, {'kind', 'text'}, 'message step')
                    require(nonempty(step['text']), 'message text is required')
                else:
                    fields(step, {'kind'}, 'Lio action step')
                    require(task['kind'] == 'undo' and step['kind'] == 'lio_undo_current_trip',
                            'unsupported Lio action step')
    return document, sha256(raw).hexdigest()


def _digest_check(name, actual, expected, ref):
    # Reuse the frozen digest/type check, with v2's native operation terminology.
    check = legacy._candidate_bytes(dict(formal_content_sha256=actual, candidate_content_sha256=expected), ref)
    check['name'] = name
    return check


def _binding(name, actual, expected, ref):
    value = actual if nonempty(actual) and nonempty(expected) else None
    return legacy._check(name, value, expected, ref)


def _history(value):
    if type(value) is not dict:
        return None
    for version, digest in value.items():
        if (type(version) is not str or not version.isdigit() or version.startswith('0') or
                type(digest) is not str or len(digest) != 64 or
                any(char not in '0123456789abcdef' for char in digest)):
            return None
    return value


def _mutation_checks(task, state, ref):
    kind = task['kind']
    rules = MUTATION_RULES[kind]
    checks = [legacy._check('formal_version' if field == 'formal_trip_version' else field,
                            state.get(field), expected, ref) for field, expected in rules.items()]
    checks.append(legacy._check('receipt_version', state.get('receipt_version'), rules['formal_trip_version'], ref))
    checks.append(_binding('receipt_trip_binding', state.get('receipt_trip_id'), state.get('formal_trip_id'), ref))
    if rules['before_formal_version']:
        checks.append(_binding('existing_trip_identity', state.get('formal_trip_id'), state.get('before_trip_id'), ref))
    if kind == 'undo':
        checks.append(_binding('undo_action_binding', state.get('receipt_action_id'), state.get('request_action_id'), ref))
    else:
        checks.extend((
            _binding('operation_message_binding', state.get('committed_message_id'), state.get('request_message_id'), ref),
            _binding('operation_run_binding', state.get('committed_run_id'), state.get('request_run_id'), ref),
        ))
    checks.append(_digest_check('committed_operation_bytes', state.get('formal_content_sha256'),
                                state.get('operation_content_sha256'), ref))
    before = _history(state.get('history_before'))
    after = _history(state.get('history_after'))
    old_versions = [str(v) for v in range(1, rules['before_formal_version'] + 1)]
    new_versions = [str(v) for v in range(1, rules['formal_trip_version'] + 1)]
    checks.append(legacy._check('history_versions_before', sorted(before) if before is not None else None,
                                old_versions, ref))
    checks.append(legacy._check('history_versions_after', sorted(after) if after is not None else None,
                                new_versions, ref))
    preserved = {version: after.get(version) for version in before} if before is not None and after is not None else None
    checks.append(legacy._check('previous_versions_immutable', preserved, before, ref))
    current = after.get(str(rules['formal_trip_version'])) if after is not None else None
    checks.append(_digest_check('current_history_bytes', state.get('formal_content_sha256'), current, ref))
    if kind == 'undo':
        target = before.get('1') if before is not None else None
        checks.append(_digest_check('undo_restored_content', state.get('formal_content_sha256'), target, ref))
    return checks


def _execution_claims(task, reply, reply_ref, state, state_ref, checks):
    claims = legacy._effects(reply.get('claimed_effects'), EFFECT_PROOFS.keys() | {legacy.UNMATCHED_CLAIM})
    verified = legacy._effects(state.get('verified_effects'), EFFECT_PROOFS)
    unsupported, unproven = [], []
    for claim in sorted(claims or []):
        if claim == legacy.UNMATCHED_CLAIM or verified is not None and claim not in verified:
            unsupported.append(claim)
            continue
        proof = [legacy._check(field, state.get(field), expected, state_ref)['status']
                 for field, expected in EFFECT_PROOFS[claim].items()]
        if claim in ('trip_saved', 'trip_updated', 'trip_undone') and task['id'] in MUTATION_TASKS:
            proof.extend(check['status'] for check in checks if check['name'] in WRITE_PROOF_NAMES)
        if 'FAIL' in proof:
            unsupported.append(claim)
        elif verified is None or 'UNKNOWN' in proof:
            unproven.append(claim)
    actual = None if claims is None or unproven and not unsupported else unsupported
    result = legacy._check('unsupported_execution_claims', actual, [], [ref for ref in (reply_ref, state_ref) if ref])
    if unproven:
        result['unproven_effects'] = unproven
    return result


def _score_task(task, variant, record):
    changed = task['id'] in MUTATION_TASKS
    rules = ({} if changed else legacy.STATE_RULES[task['kind']]) | variant.get('state', {})
    state, state_ref = legacy._evidence(record, 'state', rules.keys() | MUTATION_FIELDS | {
        'runtime_role', 'foreign_message_rows', 'foreign_mutations', 'memory_item_count',
        'formal_trip_count', 'run_status', 'tool_status', 'verified_effects',
    })
    reply, reply_ref = legacy._evidence(record, 'reply', variant['behavior'].keys() | {'claimed_effects'})
    # C's count/owner checks remain authoritative. Lio version checks replace the
    # M1-only first-version/confirmation checks in this new scoring version.
    baseline = legacy.judge({'recipe': 'accept' if changed else 'answer'}, state, {})
    checks = [legacy._check(check['name'], check['actual'], check['expected'], state_ref)
              for check in baseline['checks'] if check['name'] not in ('formal_version', 'formal_candidate_bytes')]
    checks.extend(legacy._check(name, state.get(name), expected, state_ref) for name, expected in rules.items())
    if changed:
        checks.extend(_mutation_checks(task, state, state_ref))
    if 'weather_day_offset' in task:
        request_day = state.get('weather_request_day')
        require(request_day is None or type(request_day) is str, 'invalid original weather request day')
        target_day = (date.fromisoformat(request_day) + timedelta(days=task['weather_day_offset'])).isoformat() if request_day else None
        actual_day = state.get('weather_query_day') if target_day is not None else None
        checks.append(legacy._check('weather_query_day', actual_day, target_day, state_ref))
    checks.extend(legacy._check(name, reply.get(name), expected, reply_ref, hard=False)
                  for name, expected in variant['behavior'].items())
    checks.append(_execution_claims(task, reply, reply_ref, state, state_ref, checks))
    return checks


def score(split, batch):
    """Score every planned v2 cell, preserving the full v1 allocation."""
    require(split in legacy.SPLITS, 'only development or validation may be scored')
    fields(batch, {'version', 'dataset_version', 'dataset_sha256', 'run', 'observations'}, 'batch')
    require(batch['version'] == VERSION and batch['dataset_version'] == DATASET_VERSION,
            'unsupported v2 scoring or dataset version')
    fields(batch['run'], set(legacy.RUN_FIELDS), 'run')
    require(all(nonempty(batch['run'][key]) for key in legacy.RUN_FIELDS), 'run provenance is required')
    document, digest = dataset()
    require(batch['dataset_sha256'] == digest, 'v2 dataset digest mismatch')
    planned = {(task['id'], language): task for task in document['tasks'] if task['split'] == split
               for language in legacy.LANGUAGES}
    records, attempts = {}, set()
    require(type(batch['observations']) is list, 'observations must be an array')
    for record in batch['observations']:
        require(type(record) is dict and record.keys() <= {'task_id', 'language', 'attempt_id', 'state', 'reply'},
                'invalid observation fields')
        require(all(nonempty(record.get(key)) for key in ('task_id', 'language', 'attempt_id')), 'observation identity required')
        key = record['task_id'], record['language']
        require(key in planned and key not in records and record['attempt_id'] not in attempts,
                'unplanned or duplicate observation')
        records[key] = record
        attempts.add(record['attempt_id'])
    rows = []
    for (task_id, language), task in planned.items():
        record = records.get((task_id, language))
        checks = _score_task(task, task['variants'][language], record or {})
        if record is None:
            for check in checks:
                check.update(status='UNRUN', reason='no observation submitted')
        rows.append(dict(task_id=task_id, trip_family=task['trip_family'], kind=task['kind'], language=language,
                         attempt_id=record['attempt_id'] if record else None,
                         status=legacy._status([check['status'] for check in checks]),
                         hard_status=legacy._status([check['status'] for check in checks if check['hard']]), checks=checks))
    return dict(version=VERSION, dataset_version=DATASET_VERSION, dataset_sha256=digest, split=split, run=batch['run'],
                **legacy._counts(rows),
                by_language={language: legacy._counts([row for row in rows if row['language'] == language])
                             for language in legacy.LANGUAGES}, rows=rows)
