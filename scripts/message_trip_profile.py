"""Local-only, one-way MESSAGE-send.3 activation; no key or account creation."""
import argparse
from pathlib import Path
import psycopg
from cj_api.local_app import LocalDatabase, local_conninfo, scope_for, ISSUER
from cj_api.local_run_context import load_run_context
from cj_message.trip_context import ABI, PROFILE


def activate(conninfo, subject, context, consumer_abi,*,formal_memory_configuration=None,auth_dir=None):
    if consumer_abi != ABI or context.version != 'CJ-LOCAL-RUN@2':
        raise ValueError('explicit compatible M2 consumer required')
    scope=scope_for(ISSUER,subject)
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,trip_context=True)
    database.require_budget_account(scope)
    admit=None
    if formal_memory_configuration is not None:
        from cj_api.local_formal_memory import configuration
        from cj_api.local_account_admission_v2 import account_checker_for
        from cj_auth.interfaces import AdmissionStatus
        from cj_memory.runtime import RuntimeDenied,RuntimeUnknown
        from cj_message.travel_reference import MessageContextAuthority
        import dev_auth
        config=configuration(formal_memory_configuration)
        if auth_dir is None:raise ValueError('existing local AUTH directory required for explicit formal consumer')
        credential=dev_auth.token(Path(auth_dir),subject,5)
        checker=account_checker_for(Path(auth_dir),database)
        first=checker.check(credential)
        if first.status is AdmissionStatus.UNKNOWN:raise RuntimeUnknown('formal activation admission uncertain')
        if first.status is not AdmissionStatus.ALLOWED:raise RuntimeDenied('formal activation owner unavailable')
        def admit():
            current=checker.check(credential)
            if current.status is AdmissionStatus.UNKNOWN:raise RuntimeUnknown('formal activation admission uncertain')
            if (current.status is not AdmissionStatus.ALLOWED or current.principal!=first.principal
                    or scope_for(current.principal.issuer,current.principal.subject)!=scope):
                raise RuntimeDenied('formal activation owner unavailable')
            return current.principal
        config.bind_readonly(database,scope,subject,admit,message_context=MessageContextAuthority(database.message_repository(scope),admit))
    with psycopg.connect(**local_conninfo(conninfo)) as connection:
        if admit is not None:
            admit()
            connection.execute("SELECT set_config('cj.formal_memory_consumer','CJ-MESSAGE-FORMAL-MEMORY@1',true)")
        connection.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(scope,))
        if connection.execute('SELECT version FROM cj_message_context_profile WHERE scope=%s',(scope,)).fetchone()!=('message-travel.1',):
            raise ValueError('activate compatible original travel consumer first')
        existing=connection.execute('SELECT version FROM cj_message_trip_profile WHERE scope=%s',(scope,)).fetchone()
        if existing is not None:
            if existing!=(PROFILE,):raise ValueError('unknown formal Trip profile')
            outcome='existing'
        else:
            connection.execute('INSERT INTO cj_message_trip_profile(scope,version) VALUES(%s,%s)',(scope,PROFILE))
            outcome='activated'
    if admit is not None:admit()
    return outcome


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--conninfo-json',type=Path,required=True)
    parser.add_argument('--subject',required=True)
    parser.add_argument('--run-context',type=Path,required=True)
    parser.add_argument('--consumer-abi',choices=[ABI],required=True)
    parser.add_argument('--formal-memory-run-policy',type=Path)
    parser.add_argument('--auth-dir',type=Path)
    args=parser.parse_args()
    config=None
    if args.formal_memory_run_policy is not None:
        from cj_memory.formal_runtime import load_formal_runtime_configuration
        config=load_formal_runtime_configuration(args.formal_memory_run_policy)
    print(activate(args.conninfo_json,args.subject,load_run_context(args.run_context),args.consumer_abi,
                   formal_memory_configuration=config,auth_dir=args.auth_dir))


if __name__=='__main__':main()
