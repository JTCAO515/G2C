"""One isolated rehearsal in a new private PG17 cluster owned by this process.

Arbitrary target URIs/old clusters are never accepted. After validating restored
physical state, revoke that target before resuming the unchanged primary source.
"""
import argparse
import os
import re
import stat
from pathlib import Path
import subprocess
import sys

import psycopg
from . import checkpoint,staging
from .configuration import authorization,load_secret_environment

REHEARSALS=Path('/rehearsals')


def persistent_target(identity):
    if re.fullmatch('[0-9a-f]{32}',identity) is None:raise ValueError('fixed_rehearsal_id_required')
    if REHEARSALS.resolve()!=REHEARSALS:raise ValueError('persistent_volume_symlink_refused')
    metadata=REHEARSALS.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid!=os.getuid() or stat.S_IMODE(metadata.st_mode)!=0o700:
        raise ValueError('owned_private_rehearsal_volume_required')
    mounted=False
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields,_,filesystem=line.partition(' - ')
        parts=fields.split();kind=filesystem.split()[0]
        if (parts[4]==str(REHEARSALS) and parts[3]=='/srv/g2c-beta/rehearsals'
                and kind in ('ext4','xfs','btrfs') and 'rw' in parts[5].split(',')):mounted=True
    if not mounted:raise ValueError('explicit_persistent_rehearsal_bind_mount_required')
    target=REHEARSALS/identity
    if target.is_symlink() or target.exists() and target.resolve()!=target:raise ValueError('original_rehearsal_path_required')
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True);parser.add_argument('--safety',type=Path,required=True)
    parser.add_argument('--rehearsal-id',required=True)
    parser.add_argument('--resume',action='store_true',help='finish only the same signed original target; never restore again')
    args=parser.parse_args();load_secret_environment('recovery');authorization()
    target_control=persistent_target(args.rehearsal_id);target_control.mkdir(mode=0o700,exist_ok=True)
    source_control=Path('/control')
    with staging.cluster(root=target_control/'pg',resume=args.resume) as target:
        if not args.resume:checkpoint.restore(target,args.base,args.safety,source_control,target_control)
        result=checkpoint.finish_rehearsal(target,source_control,target_control)
    print('PASS fresh Unix PG17 restored exact rows/sequences/fences; '+result)


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,psycopg.Error,subprocess.SubprocessError):
        print('ALERT beta_recovery_unavailable_original_checkpoint_retained',file=sys.stderr)
        raise SystemExit(1) from None
