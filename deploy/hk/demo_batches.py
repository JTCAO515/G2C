"""Long invite-code batches per channel, and channel attribution (#1749).

    python -B -m deploy.hk.demo_batches generate --channel internal-test --count 5 \
        --expires-at 2026-12-31T23:00:00+08:00 --out <private directory>
    python -B -m deploy.hk.demo_batches attribute --manifests <directory> <subject>
    python -B -m deploy.hk.demo_batches subjects --manifests <directory>

``generate`` writes two files into ``--out`` (an existing 0700 directory):

- ``codes-<batch>.txt`` (0600): one long code per line, for the operator to hand out.
  Codes are never stored anywhere else.
- ``batch-<batch>.json`` (0600): the manifest — batch id, channel, category, expiry and,
  per member, the subject and the SHA-256 digest. Each member is then bootstrapped with
  ``deploy.hk.demo_accounts bootstrap <subject> --digest <digest> --expires-at <expiry>``
  and revoked one by one with ``demo_accounts revoke <subject>``.

Only long ``D1-`` codes are issued (short codes are public, #1718), only for a channel
whose ``issuing`` is true in ``demo_channels.json``, and never more than 50 per batch.
Attribution maps subject → batch → channel from the manifests; no database change.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import string

from cj_strict_json import reject_duplicates
from cj_usage.authorization_deadlines import deadline

from .demo_login import CODE,SHORT_CODE_SUBJECTS,invitation_subject

CHANNELS_PATH=Path(__file__).with_name('demo_channels.json')
VERSION='g2c-demo-batch.1'
MAX_BATCH=50
_ID=re.compile(r'[a-z][a-z0-9-]{2,31}')
_BATCH=re.compile(r'[a-z][a-z0-9-]{2,31}-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}')
_SUFFIX=string.ascii_lowercase+string.digits
_SECRET=string.ascii_letters+string.digits+'-_'


def load_channels(path=CHANNELS_PATH):
    data=json.loads(path.read_bytes(),object_pairs_hook=reject_duplicates(ValueError,'duplicate_demo_channel_key'))
    if (type(data) is not dict or set(data)!={'version','decision','channels'} or data['version']!='g2c-demo-channels.1'
            or type(data['channels']) is not list or not data['channels']):
        raise ValueError('demo_channels_invalid')
    channels={}
    for item in data['channels']:
        if (type(item) is not dict or set(item)!={'id','category','issuing','label'} or type(item['id']) is not str
                or _ID.fullmatch(item['id']) is None or item['id'] in channels or item['category'] not in ('internal','external')
                or type(item['issuing']) is not bool or type(item['label']) is not str or not item['label']):
            raise ValueError('demo_channels_invalid')
        channels[item['id']]=dict(item)
    return channels


def new_code():
    """A long D1 code whose subject can never be one of the public short-code subjects."""
    while True:
        code='D1-'+''.join(secrets.choice(_SUFFIX) for _ in range(12))+'.'+''.join(secrets.choice(_SECRET) for _ in range(22))
        if CODE.fullmatch(code) and invitation_subject(code) not in SHORT_CODE_SUBJECTS:
            return code


def _private_directory(path):
    info=Path(path).lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError('private_batch_directory_required')


def _write_private(path,text):
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8') as output:
        output.write(text);output.flush();os.fsync(output.fileno())


def generate(channel,count,expires_at,out,*,now=None,channels=None,code=new_code):
    channels=load_channels() if channels is None else channels
    now=now or datetime.now(timezone.utc)
    if channel not in channels:raise ValueError('registered_channel_required')
    if not channels[channel]['issuing']:raise ValueError('channel_not_issuing_codes')
    if type(count) is not int or not 1<=count<=MAX_BATCH:raise ValueError('bounded_batch_size_required')
    expiry=datetime.fromisoformat(expires_at)
    if expiry.tzinfo is None or not now<expiry<=deadline('hk_demo'):raise ValueError('bounded_invitation_expiry_required')
    _private_directory(out)
    batch=channel+'-'+now.strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(3)
    codes=[]
    while len(codes)<count:
        value=code()
        if CODE.fullmatch(value) is None or invitation_subject(value) in SHORT_CODE_SUBJECTS:
            raise ValueError('long_invite_code_required')
        if invitation_subject(value) not in {invitation_subject(c) for c in codes}:codes.append(value)
    members=[dict(subject=invitation_subject(c),digest=hashlib.sha256(c.encode('ascii')).hexdigest()) for c in codes]
    manifest=dict(version=VERSION,batch=batch,channel=channel,category=channels[channel]['category'],
                  created_at=now.isoformat(),expires_at=expiry.isoformat(),members=members)
    _write_private(Path(out)/('codes-'+batch+'.txt'),''.join(c+'\n' for c in codes))
    _write_private(Path(out)/('batch-'+batch+'.json'),json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    return manifest


def manifests(directory,*,channels=None):
    channels=load_channels() if channels is None else channels
    seen={}
    for path in sorted(Path(directory).glob('batch-*.json')):
        data=json.loads(path.read_bytes(),object_pairs_hook=reject_duplicates(ValueError,'duplicate_batch_key'))
        if (type(data) is not dict or data.get('version')!=VERSION or _BATCH.fullmatch(str(data.get('batch')))is None
                or path.name!='batch-'+data['batch']+'.json' or data.get('channel') not in channels
                or data.get('category')!=channels[data['channel']]['category'] or type(data.get('members')) is not list):
            raise ValueError('demo_batch_manifest_invalid')
        for member in data['members']:
            subject=member.get('subject') if type(member) is dict else None
            if (type(subject) is not str or re.fullmatch(r'm4-synthetic-demo-[a-z0-9]{12}',subject) is None
                    or subject in SHORT_CODE_SUBJECTS or subject in seen
                    or re.fullmatch('[0-9a-f]{64}',str(member.get('digest'))) is None):
                raise ValueError('demo_batch_manifest_invalid')
            seen[subject]=(data['batch'],data['channel'],data['category'])
    return seen


def attribute(directory,subject,*,channels=None):
    """(batch, channel, category) for a batch member; internal short-code subjects are 'internal-short-code'."""
    found=manifests(directory,channels=channels).get(subject)
    if found is not None:return found
    if subject in SHORT_CODE_SUBJECTS:return (None,'internal-short-code','internal')
    return None


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    commands=parser.add_subparsers(dest='command',required=True)
    make=commands.add_parser('generate')
    make.add_argument('--channel',required=True);make.add_argument('--count',type=int,required=True)
    make.add_argument('--expires-at',required=True);make.add_argument('--out',required=True)
    find=commands.add_parser('attribute');find.add_argument('--manifests',required=True);find.add_argument('subject')
    listing=commands.add_parser('subjects');listing.add_argument('--manifests',required=True)
    args=parser.parse_args(argv)
    if args.command=='generate':
        manifest=generate(args.channel,args.count,args.expires_at,args.out)
        print(json.dumps(dict(batch=manifest['batch'],channel=manifest['channel'],members=len(manifest['members']))))
    elif args.command=='attribute':
        found=attribute(args.manifests,args.subject)
        print(json.dumps(None if found is None else dict(batch=found[0],channel=found[1],category=found[2])))
    else:
        print(json.dumps(sorted(manifests(args.manifests))))


if __name__=='__main__':main()
