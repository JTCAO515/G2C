"""Private worker RPC for G's call/propose/query, not a public application API.

An original bearer selects its existing line; callers cannot supply a model,
ledger, configuration, account, filesystem path or per-step capability.
"""
import base64
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
from socketserver import StreamRequestHandler,ThreadingUnixStreamServer
import stat
import threading
from time import monotonic

from cj_auth.interfaces import AdmissionStatus
from runtime_adapter.contract import decode,encode,error_code,Invalid,require,Unavailable


VERSION='G2C-runtime-host.1'
MAX_REQUEST=131072
MAX_RESPONSE=16*1024*1024


class RuntimeRPC:
    def __init__(self,bindings):self.bindings=bindings

    def _session(self,token):
        require(type(token) is str and 0<len(token)<=4096 and all(0x21<=ord(c)<=0x7e for c in token),
            'RUNTIME_ORIGINAL_AUTH_TOKEN')
        for session in self.bindings.by_scope.values():
            authority=session['authority']
            decision=authority.checker.check(token)
            if decision.status is not AdmissionStatus.ALLOWED:continue
            from .local_app import scope_for
            from hashlib import sha256
            if (scope_for(decision.principal.issuer,decision.principal.subject)==session['binding'].scope and
                    sha256(token.encode()).hexdigest()==session['binding'].auth_session_id):
                return session
        raise Unavailable('ORIGINAL_AUTH_NOT_BOUND_TO_RUNTIME')

    def handle(self,raw):
        require(type(raw) is bytes and len(raw)<=MAX_REQUEST,'RUNTIME_RPC_REQUEST_BOUND')
        request=decode(raw)
        require(type(request) is dict and set(request)=={'version','token','method','params'} and
            request['version']==VERSION and type(request['params']) is dict,'RUNTIME_RPC_FIELDS')
        require(type(request['token']) is str and request['token'] not in encode(request['params']).decode(),
            'RUNTIME_CREDENTIAL_IN_DATA')
        session=self._session(request['token']);adapter=session['adapter'];backend=session['backend']
        method=request['method'];params=request['params']
        fields={'c0':set(),'query':{'attempt_id'},'original':{'reference'},
            'call':{'task','candidate','attempt_id','timeout'},
            'propose':{'candidate','feedback','components','attempt_id','timeout'}}
        require(type(method) is str and method in fields and set(params)==fields[method],'RUNTIME_RPC_METHOD')
        if method in ('call','propose') and session['line']=='F':
            # This fixed G cases/score release is E's dialogue evaluation, not
            # F's separately admitted teacher corpus or first-phase write grant.
            result=dict(version=VERSION,status='UNRUN',attempt_id=params['attempt_id'],
                reason='F_TEACHER_SOURCE_ADAPTER_NOT_CONNECTED',quality_status='UNKNOWN')
        elif method in ('call','propose') and session['line']=='E' and set(adapter.tasks)!=set(session['dialogue'].supported_tasks):
            # Existing funding is not a substitute for complete legal setup.
            # Incomplete E/F hosts stop before G writes an intent or pays setup.
            result=dict(version=VERSION,status='UNRUN',attempt_id=params['attempt_id'],
                reason='ALL_TASK_LEGAL_SETUPS_NOT_CONNECTED',quality_status='UNKNOWN')
        elif method=='call':result=adapter.call(**params)
        elif method=='propose':result=adapter.propose(**params)
        elif method=='query':result=adapter.query(**params)
        elif method=='original':
            original=backend.original(params['reference'],deadline=monotonic()+30)
            result=dict(version=VERSION,encoding='base64',original=base64.b64encode(original).decode('ascii'))
        else:result=dict(version=VERSION,pins=self.bindings.pins.value,c0=self.bindings.pins.c0(),
            legal_setups=sorted(session['dialogue'].supported_tasks),training_status='UNRUN')
        # A source callback or long model operation may revoke the caller while
        # reading. Do not return earlier private results under a fresh identity.
        session['authority'].require(binding=session['binding'],pins_sha256=self.bindings.pins.key,
            purpose='query',deadline=monotonic()+30,read_only=True)
        self._session(request['token'])
        body=encode(result)
        if len(body)>MAX_RESPONSE:raise Unavailable('RUNTIME_RPC_RESPONSE_BOUND')
        return body


@contextmanager
def runtime_socket(bindings,path):
    path=Path(path);root=path.parent;info=root.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,
        'RUNTIME_PRIVATE_SOCKET_DIRECTORY')
    rpc=RuntimeRPC(bindings)
    class Handler(StreamRequestHandler):
        def handle(self):
            self.request.settimeout(5)
            try:
                raw=self.rfile.readline(MAX_REQUEST+2)
                if not raw.endswith(b'\n') or len(raw)>MAX_REQUEST+1:raise Invalid('RUNTIME_RPC_REQUEST_BOUND')
                answer=rpc.handle(raw[:-1])
            except (Invalid,Unavailable,OSError,TimeoutError) as error:
                answer=encode(dict(version=VERSION,status='UNKNOWN',reason=error_code(error),quality_status='UNKNOWN'))
            # A lost socket ACK never retries an operation or invents another
            # client ID; the caller must query its persisted logical attempt.
            try:self.wfile.write(answer+b'\n')
            except OSError:pass
    lock=os.open(root/'runtime.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(lock,'rb') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if path.exists() or path.is_symlink():
            metadata=path.lstat()
            require(stat.S_ISSOCK(metadata.st_mode) and metadata.st_uid==os.getuid(),'RUNTIME_ORIGINAL_SOCKET')
            path.unlink()
        with ThreadingUnixStreamServer(str(path),Handler) as server:
            path.chmod(0o600)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:yield
            finally:
                server.shutdown();thread.join();path.unlink()
