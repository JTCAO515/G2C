"""python -B -m eval.basic_chain prepare|run (no implicit real execution)."""
import argparse
from pathlib import Path

from .plan import decode, make_plan
from .runner import execute, private_read, save


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    prepare=commands.add_parser('prepare',help='offline new run/slots; grants no capability')
    prepare.add_argument('--app',required=True,help='owner-only App pin JSON')
    prepare.add_argument('--old-chats',required=True,help='owner-only locale to actual synthetic CID JSON')
    prepare.add_argument('--first-setup',action='store_true')
    prepare.add_argument('--output',required=True)
    run=commands.add_parser('run',help='one serial real smoke, requires qualified A/B adapters')
    run.add_argument('--plan',required=True);run.add_argument('--host',required=True)
    run.add_argument('--output-directory',required=True)
    run.add_argument('--execute',required=True,action='store_true')
    args=parser.parse_args()
    if args.command=='prepare':
        plan=make_plan(app=decode(private_read(args.app)),old_chats=decode(private_read(args.old_chats)),
                       first_setup=args.first_setup)
        save(Path(args.output),plan)
        print('UNRUN: plan prepared; no calls, claims or spending authority created.')
        return 0
    report=execute(decode(private_read(args.plan)),decode(private_read(args.host)),args.output_directory)
    print(f'{report["status"]}: {report["success_rate"]}; conservative/token/paid = '
          f'{report["cost"]["conservative_cny"]}/{report["cost"]["token_estimate_cny"]}/{report["cost"]["actual_paid_cny"]}')
    return 0 if report['release_allowed']else 1


if __name__=='__main__':raise SystemExit(main())
