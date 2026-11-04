"""Fixed private Hong Kong bucket, one original PUT, HEAD reconciliation only."""
import json
import os
from pathlib import Path
import re

import alibabacloud_oss_v2 as oss

from .configuration import authorization
from deploy.recovery import checksum,sync_directory

BUCKET='g2c-beta-backup'


def client():
    authorization()
    from .oss_quota import Client,require_persistent_control
    require_persistent_control()
    return Client(oss.Client(oss.Config(region='cn-hongkong',endpoint='https://oss-cn-hongkong-internal.aliyuncs.com',
        signature_version='v4',credentials_provider=oss.credentials.EnvironmentVariableCredentialsProvider(),
        retry_max_attempts=1,connect_timeout=10,readwrite_timeout=30,enabled_redirect=False)))


def object_limit(key):
    if not re.fullmatch(r'backups/[0-9]{8}T[0-9]{6}Z-[0-9a-f]{64}/(database.dump|manifest.json)',key):
        raise ValueError('fixed_backup_prefix_and_file_required')
    return 67108864 if key.endswith('/database.dump') else 1048576


def save(path,value):
    temporary=path.with_suffix('.tmp')
    with temporary.open('x') as output:
        json.dump(value,output);output.flush()
        import os
        os.fsync(output.fileno())
    temporary.replace(path);sync_directory(path.parent)


def upload_file(client,path,key,journal):
    authorization();path=Path(path);journal=Path(journal)
    limit=object_limit(key)
    if path.stat().st_size>limit:raise ValueError('recoverable_backup_size_limit_required')
    expected=dict(bucket=BUCKET,key=key,size=path.stat().st_size,sha256=checksum(path))
    previous=json.loads(journal.read_bytes()) if journal.exists() else None
    if previous is not None and previous.get('object')!=expected:raise ValueError('original_upload_binding_changed')
    try:head=client.head_object(oss.HeadObjectRequest(bucket=BUCKET,key=key))
    except oss.exceptions.OperationError as error:
        detail=error.unwrap()
        if not isinstance(detail,oss.exceptions.ServiceError) or not (detail.code=='NoSuchKey' or detail.status_code==404 and detail.code=='BadErrorResponse'):raise
        head=None
    if head is not None:
        if previous is None:raise ValueError('unregistered_existing_backup_object_refused')
        if head.content_length!=expected['size'] or (head.metadata or {}).get('sha256')!=expected['sha256'] or head.server_side_encryption!='AES256':
            raise ValueError('original_backup_object_differs')
        authorization()
        if client.get_object_acl(oss.GetObjectAclRequest(bucket=BUCKET,key=key)).acl!='private':
            raise ValueError('original_backup_object_not_private')
        save(journal,dict(object=expected,state='RECEIVED'));return 'HEAD_CONFIRMED'
    if previous is not None:
        raise ValueError('original_upload_unknown_no_resend')
    save(journal,dict(object=expected,state='INTENT'))
    authorization()
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


def download_file(client,key,path,expected_sha256,*,limit):
    authorization();path=Path(path);journal=path.with_suffix(path.suffix+'.get.json')
    maximum=object_limit(key)
    if not re.fullmatch('[0-9a-f]{64}',expected_sha256) or type(limit) is not int or not 1<=limit<=maximum:
        raise ValueError('explicit_original_backup_object_required')
    original=dict(bucket=BUCKET,key=key,sha256=expected_sha256)
    if journal.exists() and json.loads(journal.read_bytes()).get('object')!=original:raise ValueError('original_download_binding_changed')
    if path.exists():
        if path.stat().st_size>limit or checksum(path)!=expected_sha256:raise ValueError('partial_original_download_unknown_no_resend')
        save(journal,dict(object=original,state='RECEIVED'));return 'READ_ONLY_ORIGINAL'
    if journal.exists():raise ValueError('original_download_unknown_no_resend')
    save(journal,dict(object=original,state='INTENT'))
    authorization()
    if client.get_object_acl(oss.GetObjectAclRequest(bucket=BUCKET,key=key)).acl!='private':
        raise ValueError('original_backup_object_not_private')
    authorization()
    result=client.get_object(oss.GetObjectRequest(bucket=BUCKET,key=key))
    size=0
    with result.body as body:
        if (type(result.content_length) is not int or not 0<=result.content_length<=limit
                or (result.metadata or {}).get('sha256')!=expected_sha256 or result.server_side_encryption!='AES256'):
            raise ValueError('original_download_headers_rejected')
        with path.open('xb') as output:
            os.chmod(path,0o600)
            for chunk in body.iter_bytes(block_size=65536):
                size+=len(chunk)
                if size>limit:raise ValueError('bounded_backup_download_required')
                output.write(chunk)
            output.flush();os.fsync(output.fileno())
    if size!=result.content_length or checksum(path)!=expected_sha256:raise ValueError('download_integrity_unknown')
    save(journal,dict(object=original,state='RECEIVED'));return 'GET_VERIFIED'


def download_package(original_package,destination):
    from datetime import datetime,timezone
    from .checkpoint import verified
    original_package=Path(original_package);destination=Path(destination);destination.mkdir(mode=0o700,parents=True,exist_ok=True)
    manifest=verified(original_package/'manifest.json')
    if manifest['version']!='g2c-beta-data-checkpoint.1':raise ValueError('application_checkpoint_required')
    prefix='backups/'+datetime.fromtimestamp(manifest['at'],timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+manifest['dump_sha256']
    service=client()
    return {name:download_file(service,prefix+'/'+name,destination/name,
        manifest['dump_sha256'] if name=='database.dump' else checksum(original_package/name),limit=67108864 if name=='database.dump' else 1048576)
        for name in ('database.dump','manifest.json')}
