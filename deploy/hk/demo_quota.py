"""Raise the approved HK synthetic quotas without replacing any Meter ledger."""
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from cj_api.local_app import ISSUER, scope_for
from cj_api.local_run_context import load_run_context
from cj_run.step_usage import ledger_scope_for
from cj_usage.codec import decode

from .configuration import authorization, beta_subjects, demo_periods


PREVIOUS_BUDGET = 80
APPROVED_BUDGET = 800


def policy_digest(raw, budget):
    value = json.loads(raw)
    meter = value['current']['meter']
    if meter['budget'] != budget:
        raise ValueError('explicit HK synthetic quota configuration required')
    meter['budget'] = APPROVED_BUDGET
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def original_policy():
    subjects, demo = beta_subjects()
    roster = json.dumps([sorted(subjects), sorted(demo)], separators=(',', ':')).encode()
    return (policy_digest(os.environ['CJ_BETA_RUN_CONTEXT_JSON'], PREVIOUS_BUDGET),
            sha256(roster).hexdigest())


def _existing_ledgers(db, budget, *, resume):
    authorization()
    subjects, demo = beta_subjects()
    with TemporaryDirectory(prefix='g2c-demo-quota-') as directory:
        path = Path(directory) / 'run.json'
        path.write_text(os.environ['CJ_BETA_RUN_CONTEXT_JSON'])
        original = load_run_context(path, require_active=False)
    now = original.current.meter.period_start if resume else time.time()
    current, following = demo_periods(original, now)
    if (not demo or following is None or current.version != 'CJ-LOCAL-RUN@2'
            or current.current.meter.budget != PREVIOUS_BUDGET):
        raise ValueError('explicit original HK synthetic quota window required')
    keys = []
    for context, roster in ((current, subjects), (following, demo)):
        previous = context.current.meter
        expected = replace(previous, budget=budget)
        for subject in sorted(roster):
            key = ledger_scope_for(scope_for(ISSUER, subject), previous)
            row = db.execute('SELECT format_version,ledger FROM cj_usage_ledger_candidate '
                             'WHERE scope_id=%s FOR UPDATE', (key,)).fetchone()
            if row is None or row[0] != 1 or decode(row[1]).config != expected:
                raise ValueError('original HK synthetic quota ledger unavailable')
            keys.append(key)
    return keys, len(subjects), len(demo)


def upgrade(db, *, resume=False):
    keys, current, following = _existing_ledgers(db, PREVIOUS_BUDGET, resume=resume)
    db.execute("UPDATE cj_usage_ledger_candidate SET revision=revision+1,"
               "ledger=jsonb_set(ledger,'{config,budget}',to_jsonb(%s::bigint),false) "
               "WHERE scope_id=ANY(%s)", (APPROVED_BUDGET, keys))
    return current, following


def verify_applied(db):
    _existing_ledgers(db, APPROVED_BUDGET, resume=True)
