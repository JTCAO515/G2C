"""One fixed-host secret set: private 0600 env files, never build arguments.

Existing or interrupted sets are inspection-only. No vendor key, login account,
provider request, database row, image or application service is created here.
"""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa,ed25519
from cj_api.supabase_test_database import decode_uri,decode_cleanup_uri
from cj_strict_json import reject_duplicates

ROOT=Path('/host')
DEADLINE=datetime(2026,11,30,16,tzinfo=timezone.utc)
ENV_FILES=('api.env','worker.env','operator.env','backup.env','rehearsal.env','common.env')


def encoded(value):return base64.b64encode(value).decode('ascii')
def sha(value):return hashlib.sha256(value).hexdigest()


def validate(value,*,now,nonce):
    names={'operator_uri','runtime_uri','cleanup_uri','model_key','amap_key','oss_id','oss_secret','trial_expiry','revision'}
    if type(value) is not dict or set(value)!=names:raise ValueError('fixed_deployment_secret_inputs_required')
    if any(type(item) is not str or not item or len(item)>8192 or any(c in item for c in ('\n','\r','\0')) for item in value.values()):raise ValueError('single_line_secret_values_required')
    decode_uri(value['operator_uri'],operator=True);decode_uri(value['runtime_uri']);decode_cleanup_uri(value['cleanup_uri'])
    if (re.fullmatch(r'[\x21-\x7e]{1,4096}',value['model_key']) is None
            or re.fullmatch(r'[A-Za-z0-9_-]{16,256}',value['amap_key']) is None
            or re.fullmatch(r'LTAI[A-Za-z0-9]{16,28}',value['oss_id']) is None
            or re.fullmatch(r'[A-Za-z0-9+/=_-]{24,128}',value['oss_secret']) is None
            or re.fullmatch(r'[0-9a-f]{40}',value['revision']) is None
            or re.fullmatch(r'[0-9a-f]{12}',nonce) is None):raise ValueError('explicit_authorized_secret_shapes_required')
    trial=datetime.fromisoformat(value['trial_expiry'])
    if trial.tzinfo is None or now.tzinfo is None or now>=min(trial,DEADLINE):raise ValueError('trial_or_test_authorization_expired')
    return trial


def plan(value,*,now,nonce):
    return render(value,now=now,nonce=nonce,trial=validate(value,now=now,nonce=nonce))


def render(value,*,now,nonce,trial):
    def signing_pair():
        signing=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        return (signing.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()),
            signing.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    private,public=signing_pair();rehearsal_private,rehearsal_public=signing_pair()
    recovery=ed25519.Ed25519PrivateKey.generate()
    rprivate=recovery.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
    rpublic=recovery.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    confirmation,history,cleanup=(secrets.token_bytes(32) for _ in range(3))
    recovery_subjects=['m4-synthetic-recovery-'+nonce+'-'+suffix for suffix in ('a','b')]
    subjects=['m4-synthetic-beta-a','m4-synthetic-beta-b']
    context=dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=80,
        period_start=int(now.timestamp())-60,period_end=int(min(trial,DEADLINE).timestamp()),
        max_steps=24,max_tools=12,max_output=65536,max_seconds=600),output_limits=dict(model=12000,tool=48000,memory=1000)),history=[])
    files={
      'api.env':dict(CJ_SUPABASE_RUNTIME_URI=value['runtime_uri'],CJ_BETA_CONFIRMATION_B64=encoded(confirmation),CJ_BETA_HISTORY_B64=encoded(history)),
      'worker.env':dict(CJ_SUPABASE_RUNTIME_URI=value['runtime_uri'],CJ_BETA_SIGNING_PRIVATE_B64=encoded(private),CJ_MODEL_API_KEY=value['model_key'],CJ_AMAP_WEB_KEY=value['amap_key']),
      'operator.env':dict(CJ_SUPABASE_OPERATOR_URI=value['operator_uri'],CJ_BETA_RECOVERY_PRIVATE_B64=encoded(rprivate)),
      'backup.env':dict(CJ_BETA_BACKUP_ROOT='/backups',OSS_ACCESS_KEY_ID=value['oss_id'],OSS_ACCESS_KEY_SECRET=value['oss_secret']),
      'rehearsal.env':dict(CJ_SUPABASE_RUNTIME_URI=value['runtime_uri'],CJ_SUPABASE_CLEANUP_URI=value['cleanup_uri'],CJ_REHEARSAL_SUBJECTS_JSON=json.dumps(recovery_subjects,separators=(',',':')),CJ_REHEARSAL_SIGNING_PRIVATE_B64=encoded(rehearsal_private),CJ_REHEARSAL_SIGNING_PUBLIC_B64=encoded(rehearsal_public),CJ_BETA_CLEANUP_B64=encoded(cleanup)),
      'common.env':dict(CJ_ENV='local',CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_TRIAL_VALID_UNTIL=value['trial_expiry'],
        CJ_SUPABASE_CA_FILE='/run/config/supabase-ca.crt',CJ_DEPLOY_CONTROL='/control',CJ_DEPLOY_HEARTBEAT='/heartbeat',
        CJ_BETA_SUBJECTS_JSON=json.dumps(subjects,separators=(',',':')),CJ_BETA_SIGNING_PUBLIC_B64=encoded(public),CJ_BETA_RECOVERY_PUBLIC_B64=encoded(rpublic),
        CJ_BETA_RUN_CONTEXT_JSON=json.dumps(context,separators=(',',':'))),
    }
    rendered={name:(''.join(key+'='+item+'\n' for key,item in fields.items())).encode('utf8') for name,fields in files.items()}
    metadata=dict(version='g2c-beta-secret-set.1',revision=value['revision'],recovery_subjects=recovery_subjects,
        signing_public_sha256=sha(public),recovery_public_sha256=sha(rpublic),files={name:sha(body) for name,body in rendered.items()})
    return rendered,metadata


def sync(directory):
    descriptor=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def store_new(path,body,*,mode=0o600):
    descriptor=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
    with os.fdopen(descriptor,'wb') as output:output.write(body);output.flush();os.fsync(output.fileno())


def inspect(root):
    stage=root/'.secret-setup'
    if stage.is_symlink():raise ValueError('owned_original_setup_required')
    raw=(stage/'done.json').read_bytes()
    if len(raw)>8192:raise ValueError('bounded_original_setup_metadata_required')
    metadata=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate_setup_metadata'))
    if (metadata['version']!='g2c-beta-secret-set.1' or set(metadata['files'])!=set(ENV_FILES)
            or any(type(digest) is not str or re.fullmatch('[0-9a-f]{64}',digest) is None for digest in metadata['files'].values())):raise ValueError('original_secret_set_required')
    for name,digest in metadata['files'].items():
        path=root/name;info=path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=10001 or stat.S_IMODE(info.st_mode)!=0o600
                or sha(path.read_bytes())!=digest):raise ValueError('original_private_environment_differs')
    return dict(mode='READ_ONLY_ORIGINAL',**metadata)


def prepare(value,root=ROOT,*,resume_rejected_validation=False):
    if os.getuid()!=0:raise ValueError('explicit_host_operator_required')
    info=root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o700:raise ValueError('owned_private_host_mount_required')
    stage=root/'.secret-setup'
    if stage.is_symlink():raise ValueError('original_setup_directory_required')
    if stage.exists() and (stage/'done.json').exists():return inspect(root)
    expected=ENV_FILES
    if any((root/name).exists() or (root/name).is_symlink() for name in expected):raise ValueError('existing_configuration_not_overwritten')
    now=datetime.now(timezone.utc);nonce=secrets.token_hex(6)
    # Credential validation has no dispatch or key generation side effects.
    trial=validate(value,now=now,nonce=nonce)
    intent=dict(version='g2c-beta-secret-setup-intent.1',input_sha256=sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode()),
        nonce=nonce,at=now.isoformat(),source_revision=value['revision'])
    if stage.exists():
        if not resume_rejected_validation:raise ValueError('HOLD_original_secret_setup_requires_inspection')
        metadata=stage.lstat()
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid!=0 or stat.S_IMODE(metadata.st_mode)!=0o700
                or set(path.name for path in stage.iterdir())!={'intent.json'}
                or re.fullmatch(r'[A-Za-z0-9_-]{16,256}',value['model_key']) is not None):
            raise ValueError('HOLD_exact_unpublished_validation_rejection_required')
        descriptor=os.open(stage/'intent.json',os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(descriptor,'rb') as source:
            original=os.fstat(source.fileno());body=source.read(64)
        if (not stat.S_ISREG(original.st_mode) or original.st_uid!=0 or stat.S_IMODE(original.st_mode)!=0o600
                or body!=b'{"state":"INTENT"}\n'):
            raise ValueError('HOLD_exact_legacy_intent_required')
        # One O_EXCL claimant, before generating any key. The original 19-byte
        # record is preserved. This new hash binds current reconciliation input;
        # it is not falsely attributed to the old unbound intent.
        intent.update(state='RECONCILING_UNPUBLISHED_VALIDATION_REJECTION',legacy_intent_sha256=sha(body),
            legacy_source_revision='0801e0e791c791c56cb5109b7f968574aff9a563')
        store_new(stage/'reconciliation.json',json.dumps(intent,sort_keys=True).encode());sync(stage)
    else:
        if resume_rejected_validation:raise ValueError('original_validation_rejection_required')
        stage.mkdir(mode=0o700)
        store_new(stage/'intent.json',json.dumps(dict(intent,state='VALIDATED_INTENT'),sort_keys=True).encode());sync(stage);sync(root)
    rendered,metadata=render(value,now=now,nonce=nonce,trial=trial)
    for name,body in rendered.items():store_new(stage/name,body)
    sync(stage)
    for name in expected:
        os.link(stage/name,root/name);os.chown(root/name,10001,10001)
    sync(root);sync(stage)
    store_new(stage/'done.json',json.dumps(metadata,sort_keys=True).encode());sync(stage)
    return dict(mode='CREATED',**metadata)


def require_host():
    if os.getuid()!=0:raise ValueError('specified_trial_host_required')
    mounted=hostname=False
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields,_,filesystem=line.partition(' - ');parts=fields.split();kind=filesystem.split()[0]
        if (parts[4]=='/host' and parts[3]=='/srv/g2c-beta' and 'rw' in parts[5].split(',')
                and kind in ('ext4','xfs','btrfs')):mounted=True
        if (parts[4]=='/run/config/host-name' and parts[3]=='/etc/hostname' and 'ro' in parts[5].split(',')
                and kind in ('ext4','xfs','btrfs')):hostname=True
    if not mounted or not hostname:raise ValueError('specified_persistent_host_bind_required')
    if Path('/run/config/host-name').read_text().strip()!='iZj6c3ldt64bg18flzpr7hZ':
        raise ValueError('specified_trial_host_required')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-rejected-validation',action='store_true')
    args=parser.parse_args()
    try:
        # Check before even reading credential stdin. prepare/plan are also used
        # separately by the network-free synthetic filesystem test seam.
        require_host()
        raw=sys.stdin.buffer.read(65537)
        if len(raw)>65536:raise ValueError('bounded_secret_inputs_required')
        result=prepare(json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate_secret_input')),resume_rejected_validation=args.resume_rejected_validation)
        public={name:item for name,item in result.items() if name!='files'}
        public.update(file_count=len(result['files']),permissions='0600',owner_uid=10001)
        print(json.dumps(public,sort_keys=True))
    except Exception as error:
        print(json.dumps(dict(state='UNAVAILABLE_OR_HOLD',error_type=type(error).__name__)),file=sys.stderr)
        raise SystemExit(1) from None


if __name__=='__main__':main()
