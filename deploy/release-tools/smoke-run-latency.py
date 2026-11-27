"""Link B smoke POST request refs and original RUN metadata for #630."""
from datetime import datetime
import json
from math import ceil
import os
from pathlib import Path
import sys

from deploy.hk import checkpoint
from deploy.hk.configuration import load_secret_environment


def event_times(db, message_id):
    return db.execute("""
        SELECT min(e.diagnostic_at) FILTER (WHERE e.kind='started'),
               min(e.diagnostic_at) FILTER (WHERE e.kind='effect_committed'
                   AND starts_with(e.value, 'lio_progress.1:')),
               min(e.diagnostic_at) FILTER (WHERE e.kind='text_delta'),
               min(e.diagnostic_at) FILTER (WHERE e.kind='completed')
        FROM cj_message_receipt m
        JOIN cj_run_event e ON (e.scope,e.run_id)=(m.scope,m.run_id)
        WHERE m.message_id=%s
        GROUP BY m.scope,m.run_id
    """, (message_id,)).fetchall()


def elapsed_ms(event_at,start):
    if event_at is None or start is None:
        return None
    value=(event_at-start).total_seconds()*1000
    return round(value,3) if value>=0 else None


def summarize(values):
    measured=sorted(value for value in values if value is not None)
    if not measured:
        return dict(samples=0,p50_ms=None,p95_ms=None)
    return dict(samples=len(measured),p50_ms=measured[ceil(len(measured)*0.5)-1],
                p95_ms=measured[ceil(len(measured)*0.95)-1])


def main():
    # These are only already-captured metadata from the currently pinned smoke
    # and its uniquely identified POST exchange, without prompts or bodies.
    cases=json.load(sys.stdin)
    load_secret_environment('migrate')
    with checkpoint.operator() as (db,_),db.transaction():
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        db.execute("SET LOCAL statement_timeout='8s'")
        checkpoint.require_release(db,Path(os.environ['CJ_DEPLOY_CONTROL']))
        observations=[]
        for case in cases:
            rows=event_times(db,case['message_id']) if case['api_started_at'] is not None else []
            if len(rows)!=1:
                observations.append(dict(case=case['case'],started_ms=None,progress_ms=None,
                                         body_ms=None,completed_ms=None))
                continue
            started=datetime.fromisoformat(case['api_started_at'])
            run_started,progress,body,completed=rows[0]
            observations.append(dict(case=case['case'],started_ms=elapsed_ms(run_started,started),
                progress_ms=elapsed_ms(progress,started),
                body_ms=elapsed_ms(body,started),completed_ms=elapsed_ms(completed,started)))
    summary={metric:summarize([row[metric] for row in observations])
             for metric in ('started_ms','progress_ms','body_ms','completed_ms')}
    print(json.dumps(dict(kind='synthetic_server_smoke',basis='api_post_start_to_persisted_run_event',
                          quantile='nearest-rank',cases=observations,summary=summary)))


if __name__=='__main__':
    main()
