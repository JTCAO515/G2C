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
from cj_api.message_routes import BodyError,_error,_stream_octets
from cj_strict_json import reject_duplicates

VERSION='DEMO-invite-session.1'
SOCKET=Path('/run/g2c-demo/login.sock')
CODE=re.compile(r'D1-([a-z0-9]{12})[.]([A-Za-z0-9_-]{22})')
MAX_REQUEST=512
MAX_RESPONSE=4096


def exchange(runtime,code):
    match=CODE.fullmatch(code)
    if match is None:return None
    subject='m4-synthetic-demo-'+match[1]
    if subject not in runtime.demo_subjects:return None
    scope=scope_for(ISSUER,subject)
    digest=hashlib.sha256(code.encode('ascii')).hexdigest()
    with runtime.database().connect(scope) as connection:
        row=connection.execute("""SELECT demo_invite_digest,floor(extract(epoch FROM demo_invite_expires_at))::bigint,demo_session_floor
            FROM public.cj_message_scope WHERE scope=%s AND demo_revoked_at IS NULL
            AND demo_invite_expires_at>clock_timestamp()
            AND EXISTS (SELECT 1 FROM public.cj_message_context_profile p
                WHERE p.scope=cj_message_scope.scope AND p.version='message-travel.1') FOR SHARE""",(scope,)).fetchone()
        if row is None or row[0] is None or not hmac.compare_digest(digest,row[0]):
            return None
        minutes=min(120,(row[1]-int(time.time())-1)//60)
        if minutes<=0:return None
        token=dev_auth.token(runtime.auth,subject,minutes)
        middle=token.split('.')[1]
        claims=json.loads(base64.urlsafe_b64decode(middle+'='*(-len(middle)%4)))
        if claims['exp']>row[1] or claims['iat']<row[2]:return None
        return dict(version=VERSION,access_token=token,subject=subject,
            expires_at=datetime.fromtimestamp(claims['exp'],timezone.utc).isoformat().replace('+00:00','Z'))


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
                raw=self.rfile.readline(MAX_REQUEST+1)
                result=exchange(runtime,raw[:-1].decode('ascii')) if raw.endswith(b'\n') and len(raw)<=MAX_REQUEST else None
                answer=dict(result=result)
            except (OSError,ValueError,psycopg.Error):
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


def socket_exchange(code):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as channel:
        channel.settimeout(5)
        channel.connect(str(SOCKET))
        channel.sendall(code.encode('ascii')+b'\n')
        with channel.makefile('rb') as response:
            raw=response.readline(MAX_RESPONSE+1)
        if len(raw)>MAX_RESPONSE or not raw.endswith(b'\n'):
            raise ValueError('bounded demo signer response required')
        value=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate demo signer field'))
        if type(value) is not dict or set(value)!={'result'}:
            raise ValueError('demo signer unavailable')
        result=value['result']
        if result is not None and (type(result) is not dict or set(result)!={'version','access_token','subject','expires_at'}
                or result['version']!=VERSION or any(type(field) is not str for field in result.values())):
            raise ValueError('explicit demo session required')
        return result


def register_demo_login(app):
    def failure(request,status,code,en,zh):
        category='input' if status==400 else 'access' if status==401 else 'dependency'
        outcome='unknown' if status==503 else 'failed'
        response=_error(request,status,code,category,outcome,'do_not_retry',message_en=en,message_zh=zh)
        response.headers['Cache-Control']='no-store'
        return response

    @app.post('/v1/demo-invite-sessions')
    async def login(request:Request):
        try:
            media=request.headers.getlist('content-type')
            if (len(media)!=1 or media[0].split(';',1)[0].strip().lower()!='application/json'
                    or request.headers.get('content-encoding','identity').lower()!='identity'
                    or request.scope['query_string']):
                raise ValueError('explicit demo request required')
            raw=await _stream_octets(request,MAX_REQUEST)
            command=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate demo field'))
            if (type(command) is not dict or set(command)!={'version','invite_code','consent'}
                    or command['version']!=VERSION or command['consent'] is not True
                    or type(command['invite_code']) is not str):
                raise ValueError('explicit demo request required')
        except (BodyError,ValueError,UnicodeError):
            return failure(request,400,'INVALID_INPUT','Invalid request or demo rules not accepted','请求无效或未确认演示规则')
        code=command['invite_code']
        if CODE.fullmatch(code) is None:
            return failure(request,401,'DEMO_INVITE_DENIED','Invite code unavailable','邀请码不可用')
        try:result=await run_in_threadpool(socket_exchange,code)
        except (OSError,ValueError):
            return failure(request,503,'DEMO_LOGIN_UNAVAILABLE','Sign-in is temporarily unavailable','登录服务暂不可用')
        if result is None:
            return failure(request,401,'DEMO_INVITE_DENIED','Invite code unavailable','邀请码不可用')
        return JSONResponse(result,headers={'Cache-Control':'no-store'})
