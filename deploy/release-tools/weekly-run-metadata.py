"""Read at deployment preflight using the signed release's operator role."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

from deploy.hk import checkpoint
from deploy.hk.configuration import load_secret_environment

load_secret_environment('migrate')
end = datetime.now(timezone.utc)
start = end - timedelta(days=7)
with checkpoint.operator() as (db, _), db.transaction():
    db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    db.execute("SET LOCAL statement_timeout='8s'")
    checkpoint.require_release(db, Path(os.environ['CJ_DEPLOY_CONTROL']))
    result = db.execute("""
        WITH terminals AS (
          SELECT e.scope, e.run_id, e.kind AS state
          FROM cj_run_event e
          JOIN cj_run_record r ON (r.scope,r.run_id)=(e.scope,e.run_id)
          WHERE e.diagnostic_at >= %s AND e.diagnostic_at < %s
            AND e.kind IN ('completed','failed','unknown','cancelled','context_invalid')
            AND e.kind = r.status
            AND EXISTS (
              SELECT 1 FROM cj_message_receipt m
              WHERE (m.scope,m.run_id)=(e.scope,e.run_id)
            )
        ),
        reasons AS (
          SELECT t.state,
                 CASE
                   WHEN b.value IN ('answer','draft') THEN 'budget_denied:' || b.value
                   WHEN d.value IN ('validation_failed','provider_failed','provider_unknown',
                                    'budget_exhausted','validation_unknown','publication_unknown')
                     THEN 'draft_outcome:' || d.value
                   WHEN t.state = 'context_invalid' THEN 'context_invalid'
                   WHEN t.state = 'cancelled' THEN 'cancelled'
                   WHEN t.state IN ('failed','unknown') THEN 'reason_not_persisted'
                   ELSE 'none'
                 END AS reason
          FROM terminals t
          LEFT JOIN cj_run_event b ON (b.scope,b.run_id)=(t.scope,t.run_id) AND b.kind='budget_denied'
          LEFT JOIN cj_run_event d ON (d.scope,d.run_id)=(t.scope,t.run_id) AND d.kind='draft_outcome'
        )
        SELECT state,reason,count(*) FROM reasons GROUP BY state,reason
        ORDER BY count(*) DESC,state,reason
    """, (start, end)).fetchall()
    bounds = db.execute("""
        SELECT min(diagnostic_at),max(diagnostic_at)
        FROM cj_run_event WHERE diagnostic_at IS NOT NULL
    """).fetchone()
print(json.dumps(dict(start=start.isoformat(),end=end.isoformat(),
    event_bounds=[t.isoformat() if t is not None else None for t in bounds],
    state_reasons=result), separators=(',',':')))
