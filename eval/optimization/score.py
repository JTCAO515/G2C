"""Offline scoring over a frozen task set and observations from a trusted runner."""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from eval.judge import judge
from evaluation.cj028.evaluate import fields, nonempty, ratio, read_json, require

VERSION = 'G2C-dialogue-score.1'
DATASET_VERSION = 'G2C-dialogue-cases.1'
LANGUAGES = ('zh', 'en')
SPLITS = ('development', 'validation')
STATUSES = ('PASS', 'FAIL', 'UNKNOWN', 'UNRUN')
RUN_FIELDS = ('candidate_id', 'adapter_version', 'model_version', 'prompt_version', 'tools_version')
STATE_RULES = {
    'direct_answer': {},
    'clarification': {},
    'correction': {},
    'local_edit': {},
    'cancel': {'run_status': 'cancelled', 'late_publications': 0, 'dispatches_after_cancel': 0},
    'tool_failure': {'tool_status': 'failed', 'original_dispatches': 1},
    'save': {'confirmed_commits': 1},
    'undo': {'undo_commits': 1, 'restored_draft': True},
    'cross_owner': {'foreign_trip_rows': 0, 'foreign_trip_mutations': 0, 'foreign_reply_hits': 0},
    'deleted_recall': {
        'withdrawal_commits': 1, 'stop_use_fenced': True, 'deleted_context_hits': 0,
        'deleted_reply_hits': 0, 'retained_context_hits': 1, 'deleted_item_eligible': False,
    },
}
EFFECT_PROOFS = {
    'trip_saved': {'formal_trip_count': 1, 'formal_trip_version': 1, 'confirmed_commits': 1},
    'draft_undone': STATE_RULES['undo'],
    'run_cancelled': {'run_status': 'cancelled'},
    'memory_withdrawn': {'withdrawal_commits': 1, 'stop_use_fenced': True, 'deleted_item_eligible': False},
    'tool_succeeded': {'tool_status': 'succeeded'},
}
EFFECT_STATE_FIELDS = {field for proof in EFFECT_PROOFS.values() for field in proof}
UNMATCHED_CLAIM = 'unmatched_execution_claim'


def dataset():
    """Read the public development and validation tasks shipped with this version."""
    data = Path(__file__).with_name('cases.v1.json').read_bytes()
    document = read_json(data)
    require(document['version'] == DATASET_VERSION, 'unsupported dataset version')
    tasks = document['tasks']
    require(len({task['id'] for task in tasks}) == len(tasks), 'duplicate task ID')
    splits_by_family = {}
    for task in tasks:
        family = task['trip_family']
        split = task['split']
        require(nonempty(family) and split in SPLITS, 'invalid public task allocation')
        require(splits_by_family.setdefault(family, split) == split, 'trip family crosses splits')
        require(set(task['variants']) == set(LANGUAGES), 'task must contain both languages')
    return document, sha256(data).hexdigest()


def _reference(value):
    return nonempty(value) and not value.strip().upper().startswith(('UNKNOWN', 'UNRUN'))


def _evidence(record, source, keys):
    section = record.get(source)
    if section is None:
        return {}, None
    fields(section, {'attempt_id', 'ref', 'values'}, source)
    require(type(section['values']) is dict and section['values'].keys() <= keys,
            f'invalid {source} evidence fields')
    if section['attempt_id'] != record['attempt_id'] or not _reference(section['ref']):
        return {}, None
    return section['values'], section['ref']


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _check(name, actual, expected, ref, *, hard=True):
    if actual is None:
        status, reason = 'UNKNOWN', 'missing correlated evidence'
    elif _json(actual) != _json(expected):
        status, reason = 'FAIL', 'observed value differs from required value'
    else:
        status, reason = 'PASS', None
    return dict(name=name, hard=hard, status=status, expected=expected, actual=actual,
                evidence_ref=ref, reason=reason)


def _effects(value, allowed):
    if value is not None:
        require(type(value) is list and all(type(effect) is str and effect in allowed for effect in value)
                and len(set(value)) == len(value), 'invalid execution effect list')
    return value


def _candidate_bytes(state, ref):
    hashes = [state.get(key) for key in ('formal_content_sha256', 'candidate_content_sha256')]
    have_hashes = all(type(value) is str and len(value) == 64
                      and all(char in '0123456789abcdef' for char in value) for value in hashes)
    actual, expected = hashes if have_hashes else (None, None)
    return _check('formal_candidate_bytes', actual, expected, ref)


def _execution_claims(reply, reply_ref, state, state_ref, byte_check):
    claims = _effects(reply.get('claimed_effects'), EFFECT_PROOFS.keys() | {UNMATCHED_CLAIM})
    verified = _effects(state.get('verified_effects'), EFFECT_PROOFS)
    unsupported = []
    unproven = []
    for claim in sorted(claims or []):
        if claim == UNMATCHED_CLAIM or verified is not None and claim not in verified:
            unsupported.append(claim)
            continue
        proof = [_check(field, state.get(field), expected, state_ref)['status']
                 for field, expected in EFFECT_PROOFS[claim].items()]
        if claim == 'trip_saved':
            proof.append(byte_check['status'])
        if 'FAIL' in proof:
            unsupported.append(claim)
        elif verified is None or 'UNKNOWN' in proof:
            unproven.append(claim)
    actual = None if claims is None or unproven and not unsupported else unsupported
    refs = [ref for ref in (reply_ref, state_ref) if ref]
    result = _check('unsupported_execution_claims', actual, [], refs)
    if unproven:
        result['unproven_effects'] = unproven
    return result


def _score_task(task, variant, record):
    save = task['kind'] == 'save'
    state_rules = STATE_RULES[task['kind']] | variant.get('state', {})
    state, state_ref = _evidence(record, 'state', state_rules.keys() | EFFECT_STATE_FIELDS | {
        'runtime_role', 'foreign_message_rows', 'foreign_mutations', 'memory_item_count',
        'formal_trip_count', 'formal_trip_version', 'formal_content_sha256',
        'candidate_content_sha256', 'verified_effects',
    })
    reply_rules = variant['behavior']
    reply, reply_ref = _evidence(record, 'reply', reply_rules.keys() | {'claimed_effects'})

    # Preserve the existing C state judge and its expected values. Do not consume its
    # product verdict or let a missing candidate hash turn into a byte-match PASS.
    baseline = judge({'recipe': 'accept' if save else 'answer'}, state, {})
    checks = [_check(check['name'], check['actual'], check['expected'], state_ref)
              for check in baseline['checks'] if check['name'] != 'formal_candidate_bytes']
    byte_check = _candidate_bytes(state, state_ref)
    if save:
        checks.append(byte_check)
    checks.extend(_check(name, state.get(name), expected, state_ref)
                  for name, expected in state_rules.items())
    checks.extend(_check(name, reply.get(name), expected, reply_ref, hard=False)
                  for name, expected in reply_rules.items())

    checks.append(_execution_claims(reply, reply_ref, state, state_ref, byte_check))
    return checks


def _counts(rows):
    counts = Counter(row['status'] for row in rows)
    return dict(counts={status: counts[status] for status in STATUSES},
                pass_per_planned=ratio(counts['PASS'], len(rows)),
                hard_failures=sum(row['hard_status'] == 'FAIL' for row in rows))


def _status(checks):
    for status in ('FAIL', 'UNKNOWN', 'UNRUN'):
        if status in checks:
            return status
    return 'PASS'


def score(split, batch):
    """Return results for every planned task/language cell of one public split."""
    require(split in SPLITS, 'only development or validation may be scored')
    fields(batch, {'version', 'dataset_version', 'dataset_sha256', 'run', 'observations'}, 'batch')
    require(batch['version'] == VERSION and batch['dataset_version'] == DATASET_VERSION,
            'unsupported scoring or dataset version')
    run = batch['run']
    fields(run, set(RUN_FIELDS), 'run')
    require(all(nonempty(run[key]) for key in RUN_FIELDS),
            'run provenance is required')
    document, dataset_sha = dataset()
    require(batch['dataset_sha256'] == dataset_sha, 'dataset digest mismatch')
    planned = {(task['id'], language): task for task in document['tasks']
               if task['split'] == split for language in LANGUAGES}
    records = {}
    attempts = set()
    require(type(batch['observations']) is list, 'observations must be an array')
    for record in batch['observations']:
        require(type(record) is dict and record.keys() <= {'task_id', 'language', 'attempt_id', 'state', 'reply'},
                'invalid observation fields')
        require(all(nonempty(record.get(key)) for key in ('task_id', 'language', 'attempt_id')),
                'observation identity is required')
        key = record['task_id'], record['language']
        require(key in planned and key not in records, 'unplanned or duplicate task/language')
        require(record['attempt_id'] not in attempts, 'duplicate attempt ID')
        records[key] = record
        attempts.add(record['attempt_id'])

    rows = []
    for (task_id, language), task in planned.items():
        record = records.get((task_id, language))
        variant = task['variants'][language]
        checks = _score_task(task, variant, record or {})
        if record is None:
            for check in checks:
                check.update(status='UNRUN', reason='no observation submitted')
        rows.append(dict(task_id=task_id, trip_family=task['trip_family'], kind=task['kind'],
                         language=language, attempt_id=record['attempt_id'] if record else None,
                         status=_status([check['status'] for check in checks]),
                         hard_status=_status([check['status'] for check in checks if check['hard']]),
                         checks=checks))
    return dict(version=VERSION, dataset_version=DATASET_VERSION, dataset_sha256=dataset_sha,
                split=split, run=run, **_counts(rows),
                by_language={language: _counts([row for row in rows if row['language'] == language])
                             for language in LANGUAGES}, rows=rows)
