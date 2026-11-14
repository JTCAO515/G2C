"""Original operator actions for selected Demo scopes; only digests reach PG."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re

from cj_api.local_app import ISSUER,scope_for
from . import assembly_profiles,checkpoint
from .configuration import Runtime,load_secret_environment,local_database_target

DECISION='JT #495/6730538594 demo subject'
DEADLINE=datetime.fromisoformat('2027-01-01T00:00:00+08:00')


def invitation(digest,expires_at):
    if digest is None or re.fullmatch('[a-f0-9]{64}',digest) is None or expires_at is None:
        raise ValueError('explicit digest and expiry required')
    expires=datetime.fromisoformat(expires_at)
    if expires.tzinfo is None or not datetime.now(timezone.utc)<expires<=DEADLINE:
        raise ValueError('bounded demo invitation expiry required')
    return digest,expires


def state(connection,scope):
    return connection.execute("""SELECT demo_invite_digest,demo_revoked_at,
        demo_invite_expires_at,public.cj_account_scope_current(scope)
        FROM public.cj_message_scope WHERE scope=%s""",(scope,)).fetchone()


def manage(runtime,mode,subject,control,operation,new=None):
    if not local_database_target() or subject not in runtime.demo_subjects:
        raise ValueError('explicit authorized HK demo subject required')
    scope=scope_for(ISSUER,subject)
    if mode=='bootstrap':
        return assembly_profiles.run(runtime,mode,subject,control,operation,demo_invitation=new)
    if mode=='insert':
        return assembly_profiles.run(runtime,mode,subject,control,operation)
    with checkpoint.lock(control):
        with checkpoint.operator() as (connection,_),connection.transaction():
            connection.execute('SELECT pg_advisory_xact_lock(%s)',(checkpoint.RELEASE_LOCK,))
            checkpoint.require_release(connection,control)
            row=state(connection,scope)
            if row is None or row[0] is None or not row[3]:
                raise ValueError('original active demo scope unavailable')
            digest,revoked,expiry,_=row
            if mode=='inspect':
                return 'revoked' if revoked is not None else 'active' if expiry>datetime.now(timezone.utc) else 'expired'
            if mode=='revoke':
                if revoked is not None:return 'revoked'
                assembly_profiles.intent(operation/(subject+'.revoke.'+digest+'.intent'),DECISION)
                if connection.execute("""UPDATE public.cj_message_scope SET demo_revoked_at=clock_timestamp()
                    WHERE scope=%s AND demo_invite_digest=%s AND demo_revoked_at IS NULL""",(scope,digest)).rowcount!=1:
                    raise ValueError('original demo revoke unresolved')
                target='revoked'
            elif mode=='rotate':
                if (digest,expiry)==new and revoked is None:return 'active'
                if revoked is None or digest==new[0]:
                    raise ValueError('revoke original before issuing a different invitation')
                if connection.execute("""SELECT EXISTS(SELECT 1 FROM public.cj_message_delivery
                    WHERE scope=%s AND NOT acknowledged) OR EXISTS(SELECT 1 FROM public.cj_run_record
                    WHERE scope=%s AND status IN ('queued','running'))""",(scope,scope)).fetchone()!=(False,):
                    raise ValueError('original demo work still in flight')
                assembly_profiles.intent(operation/(subject+'.rotate.'+new[0]+'.intent'),DECISION)
                if connection.execute("""UPDATE public.cj_message_scope SET demo_invite_digest=%s,demo_invite_expires_at=%s,
                    demo_revoked_at=NULL,demo_session_floor=ceil(extract(epoch FROM clock_timestamp()))::bigint
                    WHERE scope=%s AND demo_invite_digest=%s AND demo_revoked_at IS NOT NULL""",
                    (*new,scope,digest)).rowcount!=1:
                    raise ValueError('original demo rotation unresolved')
                target='active'
            else:
                raise ValueError('explicit original demo action required')
        with checkpoint.operator() as (connection,_):
            checkpoint.require_release(connection,control)
            observed=state(connection,scope)
            if (observed is None or not observed[3] or (target=='revoked' and (observed[0]!=digest or observed[1] is None))
                    or (target=='active' and ((observed[0],observed[2])!=new or observed[1] is not None))):
                raise ValueError('original demo action readback unavailable')
        return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('bootstrap','insert','inspect','revoke','rotate'))
    parser.add_argument('subject')
    parser.add_argument('--digest')
    parser.add_argument('--expires-at')
    args=parser.parse_args()
    runtime=None
    try:
        load_secret_environment('migrate')
        worker=args.mode in ('bootstrap','insert')
        if worker:load_secret_environment('worker')
        runtime=Runtime.load('/tmp/g2c-demo-operator',worker=worker)
        new=invitation(args.digest,args.expires_at) if args.mode in ('bootstrap','rotate') else None
        result=manage(runtime,args.mode,args.subject,Path(os.environ['CJ_DEPLOY_CONTROL']),Path('/operation'),new)
        print(json.dumps(dict(subject=args.subject,result=result)))
    except Exception as error:
        print(json.dumps(dict(result='HOLD_READ_ORIGINAL',error_type=type(error).__name__)))
        raise SystemExit(1) from None
    finally:
        if runtime is not None:runtime.close()


if __name__=='__main__':main()
