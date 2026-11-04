"""One non-restored OSS allowance. Absence/loss never creates a new quota.

The operator installs the signed authorization and zero usage exactly once,
only after JT confirms free coverage or the capped paid allowance. Every SDK
request consumes an intent first; failures and unknown replies never refund it.
"""
from datetime import datetime,timezone
import hashlib
import os
from pathlib import Path
import stat

from . import checkpoint
from .configuration import authorization

GIB=1024**3
ROOT=Path('/control/oss-quota')


def require_persistent_control():
    control=Path('/control');info=control.lstat()
    if (os.getuid()!=10001 or not stat.S_ISDIR(info.st_mode) or info.st_uid!=10001
            or stat.S_IMODE(info.st_mode)!=0o755):raise ValueError('owned_OSS_control_required')
    mounted=False
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields,_,filesystem=line.partition(' - ');parts=fields.split()
        if parts[4]=='/control/oss-quota' or parts[4].startswith('/control/oss-quota/'):
            raise ValueError('OSS_quota_submount_refused')
        if (parts[4]=='/control' and parts[3]=='/srv/g2c-beta/control' and 'rw' in parts[5].split(',')
                and filesystem.split()[0] in ('ext4','xfs','btrfs')):mounted=True
    if not mounted:raise ValueError('persistent_nonrestored_OSS_control_required')


class Client:
    def __init__(self,wrapped,*,root=ROOT):self.wrapped=wrapped;self.root=Path(root)

    def reserve(self,request,*,byte_count=0):
        from .oss_backup import BUCKET,object_limit
        authorization()
        if request.bucket!=BUCKET:raise ValueError('fixed_backup_bucket_required')
        maximum=object_limit(request.key)
        if type(byte_count) is not int or not 0<=byte_count<=maximum:raise ValueError('bounded_original_object_required')
        if self.root.is_symlink():raise ValueError('original_OSS_quota_directory_required')
        with checkpoint.lock(self.root):
            directory=self.root.lstat()
            if directory.st_uid!=os.getuid() or stat.S_IMODE(directory.st_mode)!=0o700:
                raise ValueError('private_original_OSS_quota_required')
            for name in ('authorization.json','usage.json'):
                info=(self.root/name).lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600):
                    raise ValueError('private_original_OSS_budget_record_required')
            policy=checkpoint.verified(self.root/'authorization.json')
            state=checkpoint.verified(self.root/'usage.json')
            if (set(policy)!={'version','mode','source','request_limit','byte_limit','hold_limit_fen','expires_at'}
                    or policy['version']!='g2c-beta-oss-authorization.1' or policy['mode'] not in ('paid_capped','free_confirmed')
                    or type(policy['source']) is not str or not 1<=len(policy['source'])<=1024
                    or policy['request_limit']!=300 or policy['byte_limit']!=2*GIB
                    or type(policy['hold_limit_fen']) is not int or policy['hold_limit_fen']!=(1000 if policy['mode']=='paid_capped' else 0)
                    or policy['expires_at']!='2026-11-30T16:00:00+00:00'):
                raise ValueError('explicit_JT_OSS_allowance_required')
            if datetime.now(timezone.utc)>=datetime.fromisoformat(policy['expires_at']):raise ValueError('OSS_allowance_expired')
            identity=hashlib.sha256(checkpoint.canonical(policy)).hexdigest()
            if (set(state)!={'version','authorization_sha256','requests','reserved_bytes'}
                    or state['version']!='g2c-beta-oss-usage.1' or state['authorization_sha256']!=identity
                    or any(type(state[name]) is not int or state[name]<0 for name in ('requests','reserved_bytes'))):
                raise ValueError('original_OSS_usage_required')
            count=state['requests']+1;size=state['reserved_bytes']+byte_count
            # Conservative holds, not an invoice: 2 fen/request + 200 fen/GiB.
            hold=2*count+(size*200+GIB-1)//GIB if policy['mode']=='paid_capped' else 0
            if count>300 or size>2*GIB or hold>policy['hold_limit_fen']:
                raise ValueError('OSS_allowance_exhausted')
            state.update(requests=count,reserved_bytes=size)
            checkpoint.atomic(self.root/'usage.json',state)

    def head_object(self,request):
        self.reserve(request)
        return self.wrapped.head_object(request)

    def get_object_acl(self,request):
        self.reserve(request)
        return self.wrapped.get_object_acl(request)

    def put_object(self,request):
        self.reserve(request,byte_count=request.content_length)
        return self.wrapped.put_object(request)

    def get_object(self,request):
        from .oss_backup import object_limit
        self.reserve(request,byte_count=object_limit(request.key))
        return self.wrapped.get_object(request)
