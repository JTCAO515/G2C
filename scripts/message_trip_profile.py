"""Local-only, one-way MESSAGE-send.3 activation; no key or account creation."""
import argparse
from pathlib import Path
import psycopg
from cj_api.local_app import LocalDatabase, local_conninfo, scope_for, ISSUER
from cj_api.local_run_context import load_run_context
from cj_message.trip_context import ABI, PROFILE


def activate(conninfo, subject, context, consumer_abi):
    if consumer_abi != ABI or context.version != 'CJ-LOCAL-RUN@2':
        raise ValueError('explicit compatible M2 consumer required')
    scope=scope_for(ISSUER,subject)
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,trip_context=True)
    database.require_budget_account(scope)
    with psycopg.connect(**local_conninfo(conninfo)) as connection:
        connection.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(scope,))
        if connection.execute('SELECT version FROM cj_message_context_profile WHERE scope=%s',(scope,)).fetchone()!=('message-travel.1',):
            raise ValueError('activate compatible original travel consumer first')
        existing=connection.execute('SELECT version FROM cj_message_trip_profile WHERE scope=%s',(scope,)).fetchone()
        if existing is not None:
            if existing!=(PROFILE,):raise ValueError('unknown formal Trip profile')
            return 'existing'
        connection.execute('INSERT INTO cj_message_trip_profile(scope,version) VALUES(%s,%s)',(scope,PROFILE))
    return 'activated'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--conninfo-json',type=Path,required=True)
    parser.add_argument('--subject',required=True)
    parser.add_argument('--run-context',type=Path,required=True)
    parser.add_argument('--consumer-abi',choices=[ABI],required=True)
    args=parser.parse_args()
    print(activate(args.conninfo_json,args.subject,load_run_context(args.run_context),args.consumer_abi))


if __name__=='__main__':main()
