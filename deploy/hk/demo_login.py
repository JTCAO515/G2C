"""Demo login with the existing worker-held signing key and a private Unix socket."""
from contextlib import contextmanager
from datetime import datetime,timezone
import base64
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
from socketserver import StreamRequestHandler,UnixStreamServer
import stat
import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse
import psycopg
from starlette.concurrency import run_in_threadpool

import dev_auth
from cj_api.local_app import ISSUER,scope_for
from cj_api.composition import CompositionUnavailable
from cj_api.local_worker_context import checker_for
from cj_api.message_routes import BodyError,_error,_stream_octets,_token
from cj_auth.interfaces import AdmissionStatus
from cj_strict_json import reject_duplicates

VERSION='DEMO-invite-session.1'
ROLLING_VERSION='DEMO-invite-session.2'
RENEW_VERSION='DEMO-session-renewal.1'
ROLLING_SECONDS=7*24*60*60
SOCKET=Path('/run/g2c-demo/login.sock')
CODE=re.compile(r'D1-([a-z0-9]{12})[.]([A-Za-z0-9_-]{22})')
SHORT_CODE=re.compile(r'(?:G2C|CJ_Tester)@[0-9]{3}')
MAX_REQUEST=512
MAX_RESPONSE=4096
MAX_SOCKET_REQUEST=8192

_QUALIFIED_INVITATION="""SELECT demo_invite_digest,
    floor(extract(epoch FROM demo_invite_expires_at))::bigint,demo_session_floor
    FROM public.cj_message_scope WHERE scope=%s AND demo_revoked_at IS NULL
    AND demo_invite_expires_at>clock_timestamp() AND public.cj_account_scope_current(scope)
    AND EXISTS (SELECT 1 FROM public.cj_message_context_profile p
        WHERE p.scope=cj_message_scope.scope AND p.version='message-travel.1') FOR SHARE"""


def _grant(runtime,subject,row,version,*,parent_expires_at=None):
    now=int(time.time())
    if version==VERSION:
        minutes=min(120,(row[1]-now-1)//60)
        if minutes<=0:return None
        token=dev_auth.token(runtime.auth,subject,minutes)
    else:
        expiry=min(now+ROLLING_SECONDS,row[1])
        if expiry<=now:return None
        token=dev_auth.token(runtime.auth,subject,ROLLING_SECONDS//60,expires_at=expiry)
    middle=token.split('.')[1]
    claims=json.loads(base64.urlsafe_b64decode(middle+'='*(-len(middle)%4)))
    if (claims['exp']>row[1] or claims['iat']<row[2] or time.time()>=claims['exp']
            or parent_expires_at is not None and time.time()>=parent_expires_at):
        return None
    return dict(version=version,access_token=token,subject=subject,
        expires_at=datetime.fromtimestamp(claims['exp'],timezone.utc).isoformat().replace('+00:00','Z'))


def invitation_subject(code):
    match=CODE.fullmatch(code)
    if match is not None:
        suffix=match[1]
    elif SHORT_CODE.fullmatch(code) is not None:
        suffix=hashlib.sha256(code.encode('ascii')).hexdigest()[:12]
    else:
        return None
    return 'm4-synthetic-demo-'+suffix


def exchange(runtime,code,*,version=VERSION):
    subject=invitation_subject(code)
    if subject is None:return None
    if subject not in runtime.demo_subjects:return None
    scope=scope_for(ISSUER,subject)
    digest=hashlib.sha256(code.encode('ascii')).hexdigest()
    with runtime.database().connect(scope) as connection:
        row=connection.execute(_QUALIFIED_INVITATION,(scope,)).fetchone()
        if row is None or row[0] is None or not hmac.compare_digest(digest,row[0]):
            return None
        return _grant(runtime,subject,row,version)


def renew(runtime,token):
    decision=checker_for(runtime.auth).check(token)
    if decision.status is AdmissionStatus.UNKNOWN:
        raise ValueError('original session identity unavailable')
    if decision.status is not AdmissionStatus.ALLOWED:
        return None
    principal=decision.principal
    if principal.subject not in runtime.demo_subjects:
        return None
    scope=scope_for(ISSUER,principal.subject)
    with runtime.database().connect(scope) as connection:
        row=connection.execute(_QUALIFIED_INVITATION,(scope,)).fetchone()
        if row is None or row[0] is None or principal.issued_at<row[2]:
            return None
        return _grant(runtime,principal.subject,row,ROLLING_VERSION,parent_expires_at=principal.expires_at)


def _sign_request(runtime,raw):
    if not raw.startswith('{'):
        return exchange(runtime,raw)
    value=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate signer request field'))
    if (type(value) is dict and value.keys()=={'version','invite_code'}
            and value['version']==ROLLING_VERSION and type(value['invite_code']) is str):
        return exchange(runtime,value['invite_code'],version=ROLLING_VERSION)
    if (type(value) is dict and value.keys()=={'version','access_token'}
            and value['version']==RENEW_VERSION and _valid_token(value['access_token'])):
        return renew(runtime,value['access_token'])
    raise ValueError('explicit signer operation required')


def _valid_token(token):
    return type(token) is str and 0<len(token)<=4096 and all(0x21<=ord(char)<=0x7e for char in token)


@contextmanager
def signing_socket(runtime):
    if not runtime.demo_subjects:
        yield
        return
    root=SOCKET.parent
    info=root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError('owned private demo signer socket directory required')

    class Handler(StreamRequestHandler):
        def handle(self):
            self.request.settimeout(4)
            try:
                raw=self.rfile.readline(MAX_SOCKET_REQUEST+1)
                result=(_sign_request(runtime,raw[:-1].decode('ascii'))
                        if raw.endswith(b'\n') and len(raw)<=MAX_SOCKET_REQUEST else None)
                answer=dict(result=result)
            except (OSError,ValueError,CompositionUnavailable,psycopg.Error):
                answer=dict(unavailable=True)
            try:self.wfile.write(json.dumps(answer,separators=(',',':')).encode('ascii')+b'\n')
            except OSError:pass

    lock=os.open(root/'signer.lock',os.O_CREAT|os.O_NOFOLLOW|os.O_RDWR,0o600)
    with os.fdopen(lock,'rb') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if SOCKET.exists() or SOCKET.is_symlink():
            meta=SOCKET.lstat()
            if not stat.S_ISSOCK(meta.st_mode) or meta.st_uid!=os.getuid():
                raise ValueError('original demo socket required')
            SOCKET.unlink()
        with UnixStreamServer(str(SOCKET),Handler) as server:
            SOCKET.chmod(0o600)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:yield
            finally:
                server.shutdown()
                thread.join()
                SOCKET.unlink()


def _socket_request(command,version):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as channel:
        channel.settimeout(5)
        channel.connect(str(SOCKET))
        channel.sendall(command.encode('ascii')+b'\n')
        with channel.makefile('rb') as response:
            raw=response.readline(MAX_RESPONSE+1)
        if len(raw)>MAX_RESPONSE or not raw.endswith(b'\n'):
            raise ValueError('bounded demo signer response required')
        value=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate demo signer field'))
        if type(value) is not dict or set(value)!={'result'}:
            raise ValueError('demo signer unavailable')
        result=value['result']
        if result is not None and (type(result) is not dict or set(result)!={'version','access_token','subject','expires_at'}
                or result['version']!=version or any(type(field) is not str for field in result.values())):
            raise ValueError('explicit demo session required')
        return result


def socket_exchange(code,*,version=VERSION):
    command=(code if version==VERSION else
             json.dumps(dict(version=ROLLING_VERSION,invite_code=code),separators=(',',':')))
    return _socket_request(command,version)


def socket_renew(token):
    command=json.dumps(dict(version=RENEW_VERSION,access_token=token),separators=(',',':'))
    return _socket_request(command,ROLLING_VERSION)


def register_demo_login(app):
    def failure(request,status,code,en,zh):
        category='input' if status==400 else 'access' if status==401 else 'dependency'
        outcome='unknown' if status==503 else 'failed'
        response=_error(request,status,code,category,outcome,'do_not_retry',message_en=en,message_zh=zh)
        response.headers['Cache-Control']='no-store'
        return response

    async def command(request,version,fields):
        media=request.headers.getlist('content-type')
        if (len(media)!=1 or media[0].split(';',1)[0].strip().lower()!='application/json'
                or request.headers.get('content-encoding','identity').lower()!='identity'
                or request.scope['query_string']):
            raise ValueError('explicit demo request required')
        raw=await _stream_octets(request,MAX_REQUEST)
        value=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate demo field'))
        if type(value) is not dict or value.keys()!=fields or value['version']!=version:
            raise ValueError('explicit demo request required')
        return value

    async def invite(request,version):
        try:
            value=await command(request,version,{'version','invite_code','consent'})
            if value['consent'] is not True or type(value['invite_code']) is not str:
                raise ValueError('explicit demo request required')
        except (BodyError,ValueError,UnicodeError):
            return failure(request,400,'INVALID_INPUT','Invalid request or demo rules not accepted','请求无效或未确认演示规则')
        code=value['invite_code']
        if invitation_subject(code) is None:
            return failure(request,401,'DEMO_INVITE_DENIED','Invite code unavailable','邀请码不可用')
        try:
            result=await run_in_threadpool(socket_exchange,code,version=version)
        except (OSError,ValueError):
            return failure(request,503,'DEMO_LOGIN_UNAVAILABLE','Sign-in is temporarily unavailable','登录服务暂不可用')
        if result is None:
            return failure(request,401,'DEMO_INVITE_DENIED','Invite code unavailable','邀请码不可用')
        return JSONResponse(result,headers={'Cache-Control':'no-store'})

    @app.post('/v1/demo-invite-sessions')
    async def login(request:Request):
        return await invite(request,VERSION)

    @app.post('/v2/demo-invite-sessions')
    async def login_v2(request:Request):
        return await invite(request,ROLLING_VERSION)

    @app.post('/v2/demo-session-renewals')
    async def renewal(request:Request):
        try:
            await command(request,RENEW_VERSION,{'version'})
        except (BodyError,ValueError,UnicodeError):
            return failure(request,400,'INVALID_INPUT','Invalid renewal request','续期请求无效')
        token=_token(request)
        if not _valid_token(token):
            return failure(request,401,'DEMO_SESSION_DENIED','Session unavailable','会话已失效，请重新登录')
        try:result=await run_in_threadpool(socket_renew,token)
        except (OSError,ValueError):
            return failure(request,503,'DEMO_SESSION_UNAVAILABLE','Sign-in is temporarily unavailable','登录服务暂不可用')
        if result is None:
            return failure(request,401,'DEMO_SESSION_DENIED','Session unavailable','会话已失效，请重新登录')
        return JSONResponse(result,headers={'Cache-Control':'no-store'})
