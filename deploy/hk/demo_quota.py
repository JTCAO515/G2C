"""Raise the approved HK synthetic quotas without replacing any Meter ledger."""
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


def upgrade(db):
    authorization()
    subjects, demo = beta_subjects()
    with TemporaryDirectory(prefix='g2c-demo-quota-') as directory:
        path = Path(directory) / 'run.json'
        path.write_text(os.environ['CJ_BETA_RUN_CONTEXT_JSON'])
        original = load_run_context(path, require_active=False)
    current, following = demo_periods(original, time.time())
    if (not demo or following is None or current.version != 'CJ-LOCAL-RUN@2'
            or current.current.meter.budget != PREVIOUS_BUDGET):
        raise ValueError('explicit original HK synthetic quota window required')
    for context, roster in ((current, subjects), (following, demo)):
        previous = context.current.meter
        for subject in sorted(roster):
            key = ledger_scope_for(scope_for(ISSUER, subject), previous)
            row = db.execute('SELECT format_version,ledger FROM cj_usage_ledger_candidate '
                             'WHERE scope_id=%s FOR UPDATE', (key,)).fetchone()
            if row is None or row[0] != 1 or decode(row[1]).config != previous:
                raise ValueError('original HK synthetic quota ledger unavailable')
            db.execute("UPDATE cj_usage_ledger_candidate SET revision=revision+1,"
                       "ledger=jsonb_set(ledger,'{config,budget}',to_jsonb(%s::bigint),false) "
                       "WHERE scope_id=%s", (APPROVED_BUDGET, key))
    return len(subjects), len(demo)
