"""Run the locked SDK's serializer, OperationError, body and CRC over fake HTTP."""
import hashlib
import io
from types import SimpleNamespace
from urllib.parse import urlsplit,parse_qs

import pytest
import requests
import alibabacloud_oss_v2 as oss
from alibabacloud_oss_v2.crc import Crc64
from alibabacloud_oss_v2.transport.requests_client import RequestsHttpClient

from deploy.hk import oss_backup
from test_hk_boundaries import activate


class Session:
    def __init__(self):self.objects={};self.calls=[];self.acl='private'
    def request(self,method,url,*,headers,data,**kwargs):
        assert urlsplit(url).hostname=='g2c-beta-backup.oss-unit.invalid'
        self.calls.append(method);key=urlsplit(url).path
        status=200;body=b'';response_headers={'x-oss-request-id':'synthetic-sdk','Date':'Wed, 04 Nov 2026 12:00:00 GMT','Last-Modified':'Wed, 04 Nov 2026 12:00:00 GMT'}
        if method=='HEAD':
            if key not in self.objects:status=404
            else:
                payload,metadata=self.objects[key]
                response_headers.update({'Content-Length':str(len(payload)),'x-oss-meta-sha256':metadata,'x-oss-server-side-encryption':'AES256'})
        elif method=='PUT':
            assert headers['x-oss-object-acl']=='private' and headers['x-oss-forbid-overwrite']=='true'
            assert headers['x-oss-server-side-encryption']=='AES256'
            payload=b''.join(data);self.objects[key]=(payload,headers['x-oss-meta-sha256'])
            crc=Crc64(0);crc.update(payload);response_headers['x-oss-hash-crc64ecma']=str(crc.sum64())
        elif method=='GET' and 'acl' in parse_qs(urlsplit(url).query,keep_blank_values=True):
            body=('<AccessControlPolicy><AccessControlList><Grant>'+self.acl+'</Grant></AccessControlList></AccessControlPolicy>').encode()
        elif method=='GET':
            payload,metadata=self.objects[key];body=payload
            response_headers.update({'Content-Length':str(len(payload)),'x-oss-meta-sha256':metadata,'x-oss-server-side-encryption':'AES256'})
            crc=Crc64(0);crc.update(payload);response_headers['x-oss-hash-crc64ecma']=str(crc.sum64())
        else:raise AssertionError('unexpected synthetic method')
        response=requests.Response();response.status_code=status;response.reason='OK' if status==200 else 'Not Found'
        response.headers.update(response_headers);response._content=body;response._content_consumed=True;response.raw=io.BytesIO(body)
        return response


def service(session):
    return oss.Client(oss.Config(region='cn-hongkong',endpoint='https://oss-unit.invalid',retry_max_attempts=1,
        credentials_provider=oss.credentials.AnonymousCredentialsProvider(),http_client=RequestsHttpClient(session=session)))


def test_actual_sdk_empty_head_404_put_and_streamed_get(tmp_path,monkeypatch):
    activate(monkeypatch);session=Session();client=service(session)
    source=tmp_path/'database.dump';source.write_bytes(b'synthetic canonical checkpoint')
    sha=hashlib.sha256(source.read_bytes()).hexdigest();key='backups/20261104T000000Z-'+sha+'/database.dump'
    assert oss_backup.upload_file(client,source,key,tmp_path/'put.json')=='HEAD_CONFIRMED'
    assert session.calls.count('PUT')==1
    target=tmp_path/'downloaded.dump'
    assert oss_backup.download_file(client,key,target,sha,limit=1024)=='GET_VERIFIED'
    assert target.read_bytes()==source.read_bytes()
    assert oss_backup.download_file(client,key,target,sha,limit=1024)=='READ_ONLY_ORIGINAL'
    assert session.calls.count('PUT')==1


def test_actual_sdk_existing_public_or_unregistered_object_is_rejected(tmp_path,monkeypatch):
    activate(monkeypatch);session=Session();client=service(session);source=tmp_path/'database.dump';source.write_bytes(b'synthetic')
    sha=hashlib.sha256(source.read_bytes()).hexdigest();key='backups/20261104T000000Z-'+sha+'/database.dump';journal=tmp_path/'put.json'
    session.objects['/'+key]=(source.read_bytes(),sha)
    with pytest.raises(ValueError,match='unregistered'):oss_backup.upload_file(client,source,key,journal)
    assert session.calls.count('PUT')==0
    session.objects.clear();oss_backup.upload_file(client,source,key,journal)
    session.acl='public-read'
    with pytest.raises(ValueError,match='not_private'):oss_backup.upload_file(client,source,key,journal)
    with pytest.raises(ValueError,match='not_private'):oss_backup.download_file(client,key,tmp_path/'out.dump',sha,limit=1024)
    assert session.calls.count('PUT')==1
