"""Shared C private-PG native4 bootstrap; grants no production API authority."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
import time
from unittest.mock import patch
import psycopg
from deploy.hk import native4_usage
from lio_exploration_flow_pg import (SUBJECT,OUTSIDE,ISSUER,dev_auth,load_run_context,LocalDatabase,
    Runtime,scope_for,checkpoint,demo_accounts,TypedRuntimeConfiguration,AuthorizationBudget,DEMO_DEADLINE)


@dataclass(frozen=True)
class NativeFixture:
    auth: Path
    database: object
    context: object
    memory: object
    subjects: frozenset
    scope: str
    journal: object


def prepare(root,conninfo):
    auth=root/'auth';dev_auth.init(auth,[SUBJECT,OUTSIDE])
    config=root/'connection.json';config.write_text(json.dumps(conninfo));now=int(time.time())
    meter=root/'meter.json';meter.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(
        unit='provider_call',budget=200,period_start=now-60,period_end=int(DEMO_DEADLINE.timestamp()),
        max_steps=24,max_tools=12,max_output=65536,max_seconds=600),
        output_limits=dict(model=12000,tool=48000,memory=12000)),history=[])))
    context=load_run_context(meter);database=LocalDatabase(config,run_context=context,travel_context=True,needs_context=True)
    profile=dict(subjects=['self'],slots={'travel.pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    policy=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at='2099-01-01T00:00:00Z',profiles={SUBJECT:profile}),travel_contexts={SUBJECT:[]})
    memory=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=policy,
        selections={SUBJECT:dict(subject='self',slots=['travel.pace'],max_bytes=1000)})).encode())
    subjects=frozenset({SUBJECT});scope=scope_for(ISSUER,SUBJECT)
    runtime=Runtime(auth,context,meter,[],memory_runtime=memory,subjects=subjects,demo_subjects=subjects);runtime._database=database
    control=root/'control';operation=root/'operations';operation.mkdir(mode=0o700)
    @contextmanager
    def operator():
        with psycopg.connect(**conninfo,autocommit=True) as connection:yield connection,conninfo
    with patch.object(checkpoint,'operator',operator):
        checkpoint.bootstrap(control,lambda _:None)
        invite='D1-0123456789ab.'+'x'*22
        demo_accounts.manage(runtime,'bootstrap',SUBJECT,control,operation,
            (sha256(invite.encode()).hexdigest(),datetime.now(timezone.utc)+timedelta(hours=1)))
        demo_accounts.manage(runtime,'insert',SUBJECT,control,operation)
        # Use the accepted platform qualification, not a fixture-only bypass.
        with checkpoint.lock(control),operator()as(connection,_),connection.transaction():
            preview=native4_usage.qualify(connection,runtime,SUBJECT,control)
            assert preview['status']=='NATIVE4_USAGE_PREFLIGHT_ONLY'
            qualified=native4_usage.qualify(connection,runtime,SUBJECT,control,apply=True)
            assert qualified['status']=='NATIVE4_USAGE_QUALIFIED_TRANSACTION_PENDING'
            assert all(account['new_budget_units']==0 for account in qualified['accounts'])
    journal=AuthorizationBudget(root/'native4-flow-journal',clock=lambda:datetime(2026,11,9,tzinfo=timezone.utc))
    return NativeFixture(auth,database,context,memory,subjects,scope,journal)
