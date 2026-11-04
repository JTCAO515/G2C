"""Fixed private Hong Kong bucket, one original PUT, HEAD reconciliation only."""
import json
from pathlib import Path
import re

import alibabacloud_oss_v2 as oss

from .configuration import authorization
from deploy.recovery import checksum,sync_directory

BUCKET='g2c-beta-backup'


def client():
    authorization()
    return oss.Client(oss.Config(region='cn-hongkong',endpoint='https://oss-cn-hongkong-internal.aliyuncs.com',
        signature_version='v4',credentials_provider=oss.credentials.EnvironmentVariableCredentialsProvider(),
        retry_max_attempts=1,connect_timeout=10,readwrite_timeout=30,enabled_redirect=False))


def save(path,value):
    temporary=path.with_suffix('.tmp')
    with temporary.open('x') as output:
        json.dump(value,output);output.flush()
        import os
        os.fsync(output.fileno())
    temporary.replace(path);sync_directory(path.parent)


def upload_file(client,path,key,journal):
    authorization();path=Path(path);journal=Path(journal)
    if not re.fullmatch(r'backups/[0-9]{8}T[0-9]{6}Z-[0-9a-f]{64}/(database.dump|manifest.json)',key):
        raise ValueError('fixed_backup_prefix_and_file_required')
    expected=dict(bucket=BUCKET,key=key,size=path.stat().st_size,sha256=checksum(path))
    previous=json.loads(journal.read_bytes()) if journal.exists() else None
    if previous is not None and previous.get('object')!=expected:raise ValueError('original_upload_binding_changed')
    try:head=client.head_object(oss.HeadObjectRequest(bucket=BUCKET,key=key))
    except oss.exceptions.ServiceError as error:
        if error.code!='NoSuchKey':raise
        head=None
    if head is not None:
        if head.content_length!=expected['size'] or (head.metadata or {}).get('sha256')!=expected['sha256'] or head.server_side_encryption!='AES256':
            raise ValueError('original_backup_object_differs')
        save(journal,dict(object=expected,state='RECEIVED'));return 'HEAD_CONFIRMED'
    if previous is not None:
        raise ValueError('original_upload_unknown_no_resend')
    save(journal,dict(object=expected,state='INTENT'))
    with path.open('rb') as body:
        client.put_object(oss.PutObjectRequest(bucket=BUCKET,key=key,body=body,content_length=expected['size'],
            metadata={'sha256':expected['sha256']},server_side_encryption='AES256',acl='private',forbid_overwrite=True))
    # Verify actual object metadata after the original write; no automatic PUT retry.
    return upload_file(client,path,key,journal)


def upload_package(package,journal_root):
    from datetime import datetime,timezone
    from .checkpoint import verified
    package=Path(package);root=Path(journal_root);root.mkdir(mode=0o700,parents=True,exist_ok=True)
    manifest=verified(package/'manifest.json')
    if manifest['version']!='g2c-beta-data-checkpoint.1' or manifest['dump_sha256']!=checksum(package/'database.dump'):
        raise ValueError('verified_application_checkpoint_required')
    prefix='backups/'+datetime.fromtimestamp(manifest['at'],timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+manifest['dump_sha256']
    service=client()
    return {name:upload_file(service,package/name,prefix+'/'+name,root/(manifest['dump_sha256']+'-'+name+'.json'))
        for name in ('database.dump','manifest.json')}
