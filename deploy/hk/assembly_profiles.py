"""Explicit operator entry for the approved HK assembly pair, with single dispatch."""
import argparse
import json
import os
from pathlib import Path

import dev_auth
from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.local_app import ISSUER,scope_for
from cj_auth.interfaces import AdmissionStatus
from cj_message.travel import PROFILE
from cj_message.travel_reference import MessageContextAuthority
from local_run_context import provision_budget_connection

from . import checkpoint
from .configuration import Runtime,load_secret_environment


def inspect(connection,control,scope):
    checkpoint.require_release(connection,control)
    pending,running,profile,namespace=connection.execute(
        "SELECT (SELECT count(*) FROM public.cj_message_delivery WHERE NOT acknowledged),"
        "(SELECT count(*) FROM public.cj_run_record WHERE status IN ('queued','running')),"
        "(SELECT version FROM public.cj_message_context_profile WHERE scope=%s),"
        "EXISTS(SELECT 1 FROM public.cj_message_scope WHERE scope=%s)",(scope,scope)).fetchone()
    if pending or running:
        raise ValueError('original_delivery_or_run_in_flight')
    if profile not in (None,PROFILE):
        raise ValueError('unexpected_original_profile')
    return profile,namespace


def typed_preflight(runtime,subject,scope,*,provision=False):
    database=runtime.database()
    database.require_budget_account(scope)
    credential=dev_auth.token(runtime.auth,subject,5)
    checker=account_checker_for(runtime.auth,database)

    def admit():
        result=checker.check(credential)
        if (result.status is not AdmissionStatus.ALLOWED
                or scope_for(result.principal.issuer,result.principal.subject)!=scope):
            raise ValueError('canonical_owner_admission')
        return result.principal

    authority=MessageContextAuthority(database.message_repository(scope),admit)
    if provision:
        runtime.memory_runtime.bind(database,scope,subject,admit,message_context=authority)
    runtime.memory_runtime.bind_readonly(database,scope,subject,admit,message_context=authority)


def intent(path,decision='JT #495/6717962974 assembly subject'):
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'wb') as output:
        output.write((decision+'\n').encode('ascii'))
        output.flush()
        os.fsync(output.fileno())
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)


def run(runtime,mode,subject,control,operation,*,demo_invitation=None):
    if subject not in runtime.planning_subjects:
        raise ValueError('explicit_assembly_subject_required')
    demo=subject in runtime.demo_subjects
    if (demo and mode=='bootstrap')!=(demo_invitation is not None):
        raise ValueError('explicit_demo_bootstrap_invitation_required')
    decision='JT #495/6730538594 demo subject' if demo else 'JT #495/6717962974 assembly subject'
    scope=scope_for(ISSUER,subject)
    with checkpoint.lock(control):
        with checkpoint.operator() as (connection,_),connection.transaction():
            profile,namespace=inspect(connection,control,scope)
        if mode=='inspect' or profile==PROFILE:
            return 'existing' if profile==PROFILE else 'absent'
        if mode=='insert':
            typed_preflight(runtime,subject,scope)
        with checkpoint.operator() as (connection,_),connection.transaction():
            connection.execute('SELECT pg_advisory_xact_lock(%s)',(checkpoint.RELEASE_LOCK,))
            profile,namespace=inspect(connection,control,scope)
            if profile==PROFILE:
                return 'existing'
            if mode=='bootstrap':
                if namespace:
                    raise ValueError('bootstrap_original_namespace_exists_inspect_only')
                intent(operation/(subject+'.bootstrap.intent'),decision)
                provision_budget_connection(connection,runtime.context,subject)
                if demo:
                    if runtime.demo_next_context is not None:
                        provision_budget_connection(connection,runtime.demo_next_context,subject)
                    if connection.execute("""UPDATE public.cj_message_scope
                        SET demo_invite_digest=%s,demo_invite_expires_at=%s,demo_session_floor=0
                        WHERE scope=%s AND demo_invite_digest IS NULL""",(*demo_invitation,scope)).rowcount!=1:
                        raise ValueError('original demo invitation scope unavailable')
            else:
                if not namespace:
                    raise ValueError('original_namespace_required')
                intent(operation/(subject+'.profile.intent'),decision)
                result=connection.execute(
                    'INSERT INTO public.cj_message_context_profile(scope,version) VALUES (%s,%s)',(scope,PROFILE))
                if result.rowcount!=1:
                    raise ValueError('unexpected_profile_rowcount')
        if mode=='bootstrap':
            typed_preflight(runtime,subject,scope,provision=True)
            return 'bootstrapped'
        with checkpoint.operator() as (connection,_):
            if inspect(connection,control,scope)!=(PROFILE,True):
                raise ValueError('original_profile_readback_unavailable')
        typed_preflight(runtime,subject,scope)
        return 'activated'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('bootstrap','insert','inspect'))
    parser.add_argument('subject')
    args=parser.parse_args()
    runtime=None
    try:
        load_secret_environment('migrate')
        if args.mode!='inspect':
            load_secret_environment('worker')
        runtime=Runtime.load('/tmp/g2c-assembly-profile',worker=args.mode!='inspect')
        result=run(runtime,args.mode,args.subject,Path(os.environ['CJ_DEPLOY_CONTROL']),Path('/operation'))
        print(json.dumps(dict(subject=args.subject,result=result)))
    except Exception as error:
        print(json.dumps(dict(result='HOLD_READ_ORIGINAL',error_type=type(error).__name__)))
        raise SystemExit(1) from None
    finally:
        if runtime is not None:runtime.close()


if __name__=='__main__':main()
