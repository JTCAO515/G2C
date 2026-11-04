"""Root-installed OSS authority, append-only consumption, no implicit new quota.

Approval is a root-owned read-only host file outside runtime's writable control.
The recovery signer can record consumption, never install the fee authority.
"""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from cj_strict_json import reject_duplicates
from . import checkpoint
from .configuration import authorization

GIB=1024**3
ROOT=Path('/control/oss-quota')
AUTHORITY=Path('/run/authorizations/oss.json')


def require_persistent_control():
    control=Path('/control');info=control.lstat()
    if (os.getuid()!=10001 or not stat.S_ISDIR(info.st_mode) or info.st_uid!=10001
            or stat.S_IMODE(info.st_mode)!=0o755):raise ValueError('owned_OSS_control_required')
    mounted=authority=False
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields,_,filesystem=line.partition(' - ');parts=fields.split();kind=filesystem.split()[0]
        if parts[4]=='/control/oss-quota' or parts[4].startswith('/control/oss-quota/'):
            raise ValueError('OSS_quota_submount_refused')
        if (parts[4]=='/control' and parts[3]=='/srv/g2c-beta/control' and 'rw' in parts[5].split(',')
                and kind in ('ext4','xfs','btrfs')):mounted=True
        if (parts[4]=='/run/authorizations' and parts[3]=='/srv/g2c-beta/authorizations' and 'ro' in parts[5].split(',')
                and kind in ('ext4','xfs','btrfs')):authority=True
    if not mounted or not authority:raise ValueError('persistent_control_and_readonly_root_authority_required')


def read_authority():
    descriptor=os.open(AUTHORITY,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o644:
            raise ValueError('root_owned_OSS_authority_required')
        raw=source.read(4097)
    if len(raw)>4096:raise ValueError('bounded_OSS_authority_required')
    return json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate_OSS_authority'))


def policy():
    value=read_authority()
    if (set(value)!={'version','mode','source','request_limit','byte_limit','hold_limit_fen','expires_at'}
            or value['version']!='g2c-beta-oss-authorization.1' or value['mode'] not in ('paid_capped','free_confirmed')
            or type(value['source']) is not str or not 1<=len(value['source'])<=1024
            or value['request_limit']!=300 or value['byte_limit']!=2*GIB
            or type(value['hold_limit_fen']) is not int or value['hold_limit_fen']!=(1000 if value['mode']=='paid_capped' else 0)
            or value['expires_at']!='2026-11-30T16:00:00+00:00'):
        raise ValueError('explicit_JT_OSS_allowance_required')
    if datetime.now(timezone.utc)>=datetime.fromisoformat(value['expires_at']):raise ValueError('OSS_allowance_expired')
    return value,hashlib.sha256(checkpoint.canonical(value)).hexdigest()


def private(path,mode):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=mode:
        raise ValueError('private_original_OSS_budget_record_required')


class Client:
    def __init__(self,wrapped,*,root=ROOT):self.wrapped=wrapped;self.root=Path(root)

    def reserve(self,request,kind,*,byte_count=0):
        from .oss_backup import BUCKET,object_limit
        authorization()
        if request.bucket!=BUCKET:raise ValueError('fixed_backup_bucket_required')
        maximum=object_limit(request.key)
        if type(byte_count) is not int or not 0<=byte_count<=maximum:raise ValueError('bounded_original_object_required')
        if self.root.is_symlink():raise ValueError('original_OSS_quota_directory_required')
        with checkpoint.lock(self.root):
            authorization();allowed,identity=policy()
            directory=self.root.lstat();history=self.root/'intents'
            if (directory.st_uid!=os.getuid() or stat.S_IMODE(directory.st_mode)!=0o700 or history.is_symlink()
                    or history.stat().st_uid!=os.getuid() or stat.S_IMODE(history.stat().st_mode)!=0o700):
                raise ValueError('private_original_OSS_quota_required')
            private(self.root/'usage.json',0o600);state=checkpoint.verified(self.root/'usage.json')
            if (set(state)!={'version','authorization_sha256','requests','reserved_bytes','tip'}
                    or state['version']!='g2c-beta-oss-usage.1' or state['authorization_sha256']!=identity
                    or type(state['tip']) is not str or re.fullmatch('[0-9a-f]{64}',state['tip']) is None
                    or any(type(state[name]) is not int or not 0<=state[name]<=limit for name,limit in (('requests',300),('reserved_bytes',2*GIB)))):
                raise ValueError('original_OSS_usage_required')
            expected={f'{i:06d}.json' for i in range(1,state['requests']+1)}
            if {p.name for p in history.iterdir()}!=expected:raise ValueError('HOLD_original_OSS_intents_differ')
            tip='0'*64;total=0
            for index in range(1,state['requests']+1):
                path=history/f'{index:06d}.json';private(path,0o400);intent=checkpoint.verified(path)
                if (set(intent)!={'version','authorization_sha256','sequence','previous','kind','object_sha256','bytes'}
                        or intent['version']!='g2c-beta-oss-intent.1' or intent['authorization_sha256']!=identity
                        or intent['sequence']!=index or intent['previous']!=tip or intent['kind'] not in ('head','acl','put','get')
                        or type(intent['object_sha256']) is not str or re.fullmatch('[0-9a-f]{64}',intent['object_sha256']) is None
                        or type(intent['bytes']) is not int or not 0<=intent['bytes']<=67108864):raise ValueError('HOLD_original_OSS_intent_invalid')
                total+=intent['bytes'];tip=hashlib.sha256(checkpoint.canonical(intent)).hexdigest()
            if total!=state['reserved_bytes'] or tip!=state['tip']:raise ValueError('HOLD_original_OSS_counter_regressed')
            count=state['requests']+1;size=total+byte_count
            hold=2*count+(size*200+GIB-1)//GIB if allowed['mode']=='paid_capped' else 0
            if count>300 or size>2*GIB or hold>allowed['hold_limit_fen']:raise ValueError('OSS_allowance_exhausted')
            intent=dict(version='g2c-beta-oss-intent.1',authorization_sha256=identity,sequence=count,previous=tip,kind=kind,
                object_sha256=hashlib.sha256(checkpoint.canonical(dict(bucket=request.bucket,key=request.key))).hexdigest(),bytes=byte_count)
            descriptor=os.open(history/f'{count:06d}.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
            with os.fdopen(descriptor,'w') as output:
                json.dump(checkpoint.envelope(intent),output);output.flush();os.fsync(output.fileno())
            checkpoint.local.sync_directory(history)
            state.update(requests=count,reserved_bytes=size,tip=hashlib.sha256(checkpoint.canonical(intent)).hexdigest())
            checkpoint.atomic(self.root/'usage.json',state)
            self.before_send(identity)
            return identity

    @staticmethod
    def before_send(identity):
        authorization();_,current=policy()
        if current!=identity:raise ValueError('OSS_authority_changed_hold_retained')

    def head_object(self,request):
        identity=self.reserve(request,'head');self.before_send(identity)
        return self.wrapped.head_object(request)

    def get_object_acl(self,request):
        identity=self.reserve(request,'acl');self.before_send(identity)
        return self.wrapped.get_object_acl(request)

    def put_object(self,request):
        identity=self.reserve(request,'put',byte_count=request.content_length);self.before_send(identity)
        return self.wrapped.put_object(request)

    def get_object(self,request):
        from .oss_backup import object_limit
        identity=self.reserve(request,'get',byte_count=object_limit(request.key));self.before_send(identity)
        return self.wrapped.get_object(request)
