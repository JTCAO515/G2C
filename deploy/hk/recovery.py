"""Explicit new Unix-cluster recovery; never promote or replace the cloud DB."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

import psycopg
from cj_api.local_app import local_conninfo
from . import checkpoint
from .configuration import authorization


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-json',type=Path,required=True)
    parser.add_argument('--base',type=Path,required=True);parser.add_argument('--safety',type=Path,required=True)
    parser.add_argument('--source-control',type=Path,required=True);parser.add_argument('--target-control',type=Path,required=True)
    args=parser.parse_args();authorization()
    checkpoint.restore(local_conninfo(args.target_json),args.base,args.safety,args.source_control,args.target_control)
    print('PASS restored latest complete checkpoint into isolated Unix cluster; cloud target unchanged')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,psycopg.Error,subprocess.SubprocessError):
        print('ALERT beta_recovery_unavailable_original_checkpoint_retained',file=sys.stderr)
        raise SystemExit(1) from None
