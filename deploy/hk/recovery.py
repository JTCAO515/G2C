"""One isolated rehearsal in a new private PG17 cluster owned by this process.

Arbitrary target URIs/old clusters are never accepted. After validating restored
physical state, revoke that target before resuming the unchanged primary source.
"""
import argparse
from pathlib import Path
import subprocess
import sys

import psycopg
from . import checkpoint,staging
from .configuration import authorization,load_secret_environment


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True);parser.add_argument('--safety',type=Path,required=True)
    parser.add_argument('--source-control',type=Path,required=True);parser.add_argument('--target-control',type=Path,required=True)
    parser.add_argument('--resume',action='store_true',help='finish only the same signed original target; never restore again')
    args=parser.parse_args();load_secret_environment('recovery');authorization()
    args.target_control.mkdir(mode=0o700,parents=True,exist_ok=True)
    with staging.cluster(root=args.target_control/'pg',resume=args.resume) as target:
        if not args.resume:checkpoint.restore(target,args.base,args.safety,args.source_control,args.target_control)
        result=checkpoint.finish_rehearsal(target,args.source_control,args.target_control)
    print('PASS fresh Unix PG17 restored exact rows/sequences/fences; '+result)


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,psycopg.Error,subprocess.SubprocessError):
        print('ALERT beta_recovery_unavailable_original_checkpoint_retained',file=sys.stderr)
        raise SystemExit(1) from None
