"""Local operator scaffolding only; never runtime credentials or product selection semantics."""
import argparse
import json
import os
from pathlib import Path
import sys
import psycopg
from cj_api.local_app import local_conninfo, ISSUER, scope_for
from cj_api.local_run_context import load_run_context
from cj_message.needs_binding import needs_scope_for
from cj_run.step_usage import ledger_scope_for
from cj_usage.core import Ledger
from cj_usage.codec import encode, decode, CorruptLedger
from cj_needs.domain import Command, Denied, Conflict, CommitUnknown
from cj_needs.postgres import Repository as NeedsRepository


def invited(auth_dir, subject):
    value=json.loads((Path(auth_dir)/'invited.json').read_text())
    if type(value) is not list or subject not in value:
        raise Denied('explicit invited local subject required')


def provision_budget(conninfo, context, subject):
    scope=scope_for(ISSUER,subject)
    account=ledger_scope_for(scope,context.current.meter)
    with psycopg.connect(**local_conninfo(conninfo)) as connection:
        connection.execute('INSERT INTO cj_message_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',(scope,))
        connection.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(scope,))
        activated=connection.execute('SELECT version FROM cj_local_run_protection WHERE scope=%s',(scope,)).fetchone()
        if activated is None:
            if context.version=='CJ-LOCAL-RUN@1' and connection.execute('SELECT 1 FROM cj_message_delivery WHERE scope=%s AND NOT acknowledged LIMIT 1',(scope,)).fetchone():
                raise ValueError('original pending legacy work prevents activation')
            connection.execute("INSERT INTO cj_local_run_protection VALUES(%s,'local-budget-needs.1')",(scope,))
        elif activated!=('local-budget-needs.1',):
            raise ValueError('original protection unavailable')
        if context.version=='CJ-LOCAL-RUN@2':
            # The DB activation boundary owns the idle-work checks exactly once.
            connection.execute("INSERT INTO cj_local_metered_profile VALUES(%s,'registered-exit.1') ON CONFLICT DO NOTHING",(scope,))
        row=connection.execute('SELECT format_version,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s FOR UPDATE',(account,)).fetchone()
        if row is None:
            connection.execute('INSERT INTO cj_usage_ledger_candidate(scope_id,revision,format_version,ledger) VALUES(%s,0,1,%s::jsonb)',
                               (account,encode(Ledger(config=context.current.meter))))
            return 'created'
        if row[0]!=1 or decode(row[1]).config!=context.current.meter:
            raise ValueError('existing original budget differs; refusing reset')
        return 'existing'


def put_needs(conninfo, auth_dir, subject, raw):
    scope=needs_scope_for(scope_for(ISSUER,subject))
    config=local_conninfo(conninfo)
    with psycopg.connect(**config) as connection:
        connection.execute('INSERT INTO cj_needs_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',(scope,))
    repository=NeedsRepository(lambda:psycopg.connect(**config),scope,lambda stage:invited(auth_dir,subject))
    receipt=repository.act(Command(raw))
    return {'action_id':receipt.action_id,'needs_id':receipt.needs_id,'version':receipt.version}


def bind_needs(conninfo, subject, conversation_id, needs_id):
    scope=scope_for(ISSUER,subject); needs_scope=needs_scope_for(scope)
    with psycopg.connect(**local_conninfo(conninfo)) as connection:
        if connection.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(scope,)).fetchone() is None:
            raise ValueError('original conversation scope unavailable')
        chat=connection.execute('SELECT generation FROM cj_message_chat WHERE scope=%s AND conversation_id=%s AND active',
                                (scope,conversation_id)).fetchone()
        if chat is None or connection.execute('SELECT 1 FROM cj_needs_record WHERE scope=%s AND needs_id=%s',(needs_scope,needs_id)).fetchone() is None:
            raise ValueError('explicit conversation/NEEDS unavailable')
        old=connection.execute('SELECT needs_scope,needs_id FROM cj_message_needs_selection WHERE message_scope=%s AND conversation_id=%s AND generation=%s',
                               (scope,conversation_id,chat[0])).fetchone()
        if old is not None:
            if old!=(needs_scope,needs_id): raise ValueError('selection exists; refusing overwrite')
            return 'existing'
        connection.execute('INSERT INTO cj_message_needs_selection VALUES(%s,%s,%s,%s,%s)',
                           (scope,conversation_id,chat[0],needs_scope,needs_id))
        return 'created'


def main():
    if os.environ.get('CJ_ENV')!='local': raise SystemExit('CJ_ENV=local is required')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--conninfo-json',type=Path,required=True)
    parser.add_argument('--run-context',type=Path,required=True)
    parser.add_argument('--auth-dir',type=Path,required=True)
    parser.add_argument('--subject',required=True)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init-budget')
    put=sub.add_parser('put-needs');put.add_argument('--input-json',type=Path,required=True)
    bind=sub.add_parser('bind-needs');bind.add_argument('--conversation-id',required=True);bind.add_argument('--needs-id',required=True)
    args=parser.parse_args()
    context=load_run_context(args.run_context)
    invited(args.auth_dir,args.subject)
    if args.command=='init-budget': result={'status':provision_budget(args.conninfo_json,context,args.subject)}
    elif args.command=='put-needs': result=put_needs(args.conninfo_json,args.auth_dir,args.subject,args.input_json.read_bytes())
    else: result={'status':bind_needs(args.conninfo_json,args.subject,args.conversation_id,args.needs_id)}
    print(json.dumps(result,separators=(',',':')))


if __name__=='__main__':
    try: main()
    except (psycopg.Error,CommitUnknown) as error:
        print(json.dumps({'outcome':'unknown','error':type(error).__name__}),file=sys.stderr)
        raise SystemExit(1)
    except (ValueError,Denied,Conflict,CorruptLedger) as error:
        print(json.dumps({'outcome':'unknown' if getattr(error,'commit_possible',False) else 'failed',
                          'error':type(error).__name__}),file=sys.stderr)
        raise SystemExit(1)
