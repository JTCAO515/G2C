"""Capture actual ordinary-Home HTTP bytes for a bounded synthetic smoke.

This is a response-transparent observer, not a sender, credential issuer or
replacement for legacy stored wire. Only frozen C inputs enter a bounded queue;
one thread waits for the genuine worker claim/return and uses native history
AUTH before publishing. No worker model/Memory artifact directory is mounted.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from queue import Queue, Empty, Full
import re
import threading
import time
from uuid import uuid4
from urllib.parse import parse_qsl

from starlette.requests import Request

from cj_auth.interfaces import AdmissionStatus
from cj_message.demo_dialogue import DialogueMessage
from cj_message.domain import InvalidInput
from cj_run.core import Binding
from cj_strict_json import reject_duplicates
from cj_usage.authorization_budget import canonical
from cj_usage.metered_exit import BudgetUnknown
from cj_api.local_app import ISSUER, scope_for
from cj_api.message_routes import _token
from cj_api.runtime_originals import RuntimeOriginals
from cj_api.runtime_private import read_private, private_directory
from runtime_adapter.contract import Unavailable


VERSION='G2C-App-smoke-outer-window.1'
OUTER='G2C-App-smoke-outer.1'
ROUTES={'/v1/lio/messages':'LIO-message.1','/v2/lio/messages':'LIO-message.2'}
MAX_BODY=16384
READ_ROUTES=frozenset(('/v1/lio/timeline','/v2/lio/timeline','/v2/lio/messages'))
HTTP_LOG_LIMIT=16*1024*1024
MAX_READ_ARTIFACTS=64


def decoded(raw):
    return json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate smoke outer field'))


def publish_marker(directory,name,value,*,keep_existing=False):
    """Publish a complete one-shot receipt; readers never see partial JSON."""
    temporary='.'+uuid4().hex+'.pending'
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
    try:
        with os.fdopen(fd,'wb')as output:
            output.write(canonical(value));output.flush();os.fsync(output.fileno())
        try:os.link(temporary,name,src_dir_fd=directory,dst_dir_fd=directory,follow_symlinks=False)
        except FileExistsError:
            prior=decoded(read_private(name,16384,directory_fd=directory))
            if not keep_existing and prior!=value:
                raise Unavailable('APP_SMOKE_ORIGINAL_RECEIPT_CHANGED')
        os.fsync(directory)
    finally:os.unlink(temporary,dir_fd=directory)


@dataclass(frozen=True)
class Received:
    token:str=field(repr=False)
    scope:str
    raw:bytes=field(repr=False)
    route:str
    message_id:str
    input_sha256:str
    deadline:float


@dataclass(frozen=True)
class ReceivedRead:
    token:str=field(repr=False)
    scope:str
    route:str
    selector:dict
    response:bytes=field(repr=False)
    status:int
    deadline:float
    exchange_id:str


class OuterControls:
    """Read the worker's typed control metadata; never claim a new slot here."""
    def __init__(self,path,subjects,*,clock=time.time):
        self.path=Path(path);self.raw=read_private(path,16384);self.window=decoded(self.raw);self.clock=clock
        w=self.window
        if (type(w)is not dict or set(w)!={'version','policy_path','policy_sha256','directory','directory_device','directory_inode'}
                or w['version']!=VERSION or type(w['policy_sha256'])is not str
                or re.fullmatch('[0-9a-f]{64}',w['policy_sha256'])is None
                or any(type(w[k])is not str or not Path(w[k]).is_absolute()for k in ('policy_path','directory'))
                or any(type(w[k])is not int or w[k]<0 for k in ('directory_device','directory_inode'))):
            raise ValueError('qualified owned outer capture window required')
        self.policy_raw=read_private(w['policy_path'],65536)
        if sha256(self.policy_raw).hexdigest()!=w['policy_sha256']:
            raise ValueError('qualified App smoke policy digest changed')
        self.policy=p=decoded(self.policy_raw)
        needed={'version','source_commit','starts_at','ends_at','slots','directory','directory_device','directory_inode'}
        if (type(p)is not dict or not needed<=p.keys()or p['version']!='G2C-App-smoke-capture.1'
                or type(p['source_commit'])is not str or re.fullmatch('[0-9a-f]{40}',p['source_commit'])is None
                or any(type(p[k])is not str for k in ('starts_at','ends_at','directory'))
                or not Path(p['directory']).is_absolute()
                or any(type(p[k])is not int or p[k]<0 for k in ('directory_device','directory_inode'))
                or type(p['slots'])is not list or not 8<=len(p['slots'])<=12):
            raise ValueError('bounded original App smoke policy required')
        seen=set()
        for slot in p['slots']:
            fields={'slot_id','subject','locale','protocol','text_sha256'}
            if(type(slot)is not dict or not fields<=slot.keys()or type(slot['subject'])is not str
                    or slot['subject']not in subjects or type(slot['slot_id'])is not str or slot['slot_id']in seen
                    or slot['locale']not in ('zh','en')or slot['protocol']not in ROUTES.values()
                    or type(slot['text_sha256'])is not str or re.fullmatch('[0-9a-f]{64}',slot['text_sha256'])is None):
                raise ValueError('frozen existing App smoke inputs required')
            seen.add(slot['slot_id'])
        self.subjects=frozenset(x['subject']for x in p['slots'])
        if len(self.subjects)!=2 or not self.subjects<=frozenset(subjects):
            raise ValueError('two existing synthetic owners required')
        self.scopes=frozenset(scope_for(ISSUER,s)for s in self.subjects)
        self.ends=datetime.fromisoformat(p['ends_at']).timestamp()
        self.guard()

    def guard(self):
        if read_private(self.path,16384)!=self.raw or read_private(self.window['policy_path'],65536)!=self.policy_raw:
            raise Unavailable('APP_SMOKE_OUTER_AUTHORITY_CHANGED')
        start=datetime.fromisoformat(self.policy['starts_at'])
        end=datetime.fromisoformat(self.policy['ends_at'])
        if start.tzinfo is None or end.tzinfo is None or not 0<(end-start).total_seconds()<=5400 or not start.timestamp()<=self.clock()<end.timestamp():
            raise Unavailable('APP_SMOKE_OUTER_WINDOW_INACTIVE')
        with self.directory():pass

    def directory(self):
        from contextlib import contextmanager
        @contextmanager
        def opened():
            with private_directory(self.window['directory'],Unavailable('APP_SMOKE_OUTER_DIRECTORY_AUTHORITY'))as fd:
                info=os.fstat(fd)
                if(info.st_dev,info.st_ino)!=(self.window['directory_device'],self.window['directory_inode']):
                    raise Unavailable('APP_SMOKE_OUTER_DIRECTORY_REPLACED')
                yield fd
        return opened()

    def permits(self,scope,command):
        digest=sha256(command.text.encode()).hexdigest()
        return any(scope_for(ISSUER,x['subject'])==scope and
            (x['text_sha256'],x['locale'],x['protocol'])==(digest,command.locale,command.protocol)
            for x in self.policy['slots'])

    def claim(self,scope,mid):
        self.guard();p=self.policy
        with private_directory(p['directory'],Unavailable('APP_SMOKE_CLAIM_DIRECTORY_AUTHORITY'))as directory:
            info=os.fstat(directory)
            if(info.st_dev,info.st_ino)!=(p['directory_device'],p['directory_inode']):
                raise Unavailable('APP_SMOKE_CLAIM_DIRECTORY_REPLACED')
            value=decoded(read_private('claims.json',65536,directory_fd=directory))
        if (value.get('version')!='G2C-App-smoke-claims.1' or value.get('policy_sha256')!=self.window['policy_sha256']
                or value.get('state')not in ('ACTIVE','STOP_NEW')or type(value.get('claims'))is not list
                or len(value['claims'])>len(p['slots'])):
            raise Unavailable('APP_SMOKE_ORIGINAL_CLAIMS_UNAVAILABLE')
        matches=[x for x in value['claims']if x['binding']['scope']==scope and x['binding']['message_id']==mid]
        if not matches:return None
        if len(matches)!=1:raise Unavailable('APP_SMOKE_ORIGINAL_CLAIM_AMBIGUOUS')
        claim=matches[0];Binding(**claim['binding'])
        if any(type(claim.get(k))is not str or re.fullmatch('[0-9a-f]{64}',claim[k])is None
               for k in ('input_sha256','canonical_sha256')):
            raise Unavailable('APP_SMOKE_ORIGINAL_DIGEST_UNAVAILABLE')
        if not any(x['slot_id']==claim['slot_id']and scope_for(ISSUER,x['subject'])==scope for x in p['slots']):
            raise Unavailable('APP_SMOKE_ORIGINAL_CLAIM_OUTSIDE_PLAN')
        witness=claim.get('producer_return')
        if witness is not None and(type(witness)is not dict or
                witness.get('version')!='G2C-App-smoke-producer-return.1'or
                witness.get('producer')!='hk.entrypoint.run_worker.run_once.returned'or
                witness.get('source_commit')!=p['source_commit']or witness.get('acknowledged')is not True or
                witness.get('status')not in ('completed','unknown','failed','context_invalid','cancelled')or
                type(witness.get('event_sequence'))is not int or witness['event_sequence']<1 or
                witness.get('cost_coverage')!='NOT_ASSERTED'):
            raise Unavailable('APP_SMOKE_ORIGINAL_PRODUCER_RETURN_UNAVAILABLE')
        return claim

    def read_anchor(self,scope,route,selector,*,require_return=True):
        self.guard();p=self.policy
        with private_directory(p['directory'],Unavailable('APP_SMOKE_CLAIM_DIRECTORY_AUTHORITY'))as directory:
            info=os.fstat(directory)
            if(info.st_dev,info.st_ino)!=(p['directory_device'],p['directory_inode']):
                raise Unavailable('APP_SMOKE_CLAIM_DIRECTORY_REPLACED')
            value=decoded(read_private('claims.json',65536,directory_fd=directory))
        if value.get('policy_sha256')!=self.window['policy_sha256']:raise Unavailable('APP_SMOKE_READ_CLAIM_CHANGED')
        rows=[x for x in value['claims']if x['binding']['scope']==scope
              and (not require_return or x.get('producer_return')is not None)]
        if route=='/v2/lio/messages':
            rows=[x for x in rows if x['binding']['message_id']==selector['message_id']and x['input_sha256']==selector['input_sha256']]
        else:
            from cj_message.demo_dialogue import lio_conversation
            cid=selector.get('conversation_id',lio_conversation(scope))
            rows=[x for x in rows if x['binding']['conversation_id']==cid]
        if not rows:return None
        return max(rows,key=lambda x:x['binding']['message_sequence'])


class OuterCapture:
    def __init__(self,controls,fast_checker,originals,*,clock=time.time):
        self.controls,self.checker,self.originals,self.clock=controls,fast_checker,originals,clock
        self.queue=Queue(maxsize=12);self.read_queue=Queue(maxsize=12);self.stop=threading.Event()
        self.http_lock=threading.Lock()
        self.thread=threading.Thread(target=self._loop,name='app-smoke-outer',daemon=True);self.thread.start()

    def eligible(self,token):
        decision=self.checker.check(token)
        return (decision.status is AdmissionStatus.ALLOWED and decision.principal.subject in self.controls.subjects)

    def _http(self,value):
        try:return self._write_http(value)
        except (OSError,ValueError,Unavailable):
            # Keep a one-way gap marker; later successful observations cannot
            # turn a lost part of this window into complete HTTP coverage.
            self.mark_lost()
            raise

    def mark_lost(self):
        with self.controls.directory()as directory:
            publish_marker(directory,'http-coverage-lost.json',dict(version='G2C-App-smoke-HTTP-gap.1',
                policy_sha256=self.controls.window['policy_sha256']))

    def _write_http(self,value):
        controls=self.controls
        with self.http_lock,controls.directory()as directory:
            fd=os.open('http-attempts.jsonl',os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=directory)
            try:
                info=os.fstat(fd)
                import stat
                if(not stat.S_ISREG(info.st_mode)or info.st_uid!=os.getuid()or info.st_mode&0o777!=0o600
                        or info.st_nlink!=1 or info.st_size>HTTP_LOG_LIMIT):
                    raise Unavailable('APP_SMOKE_HTTP_LOG_UNQUALIFIED')
                line=canonical(value)+b'\n'
                if info.st_size+len(line)>HTTP_LOG_LIMIT or os.write(fd,line)!=len(line):
                    raise Unavailable('APP_SMOKE_HTTP_LOG_COVERAGE_LOST')
                os.fsync(fd)
            finally:os.close(fd)

    def begin(self,token,route,*,method='POST'):
        self.controls.guard();decision=self.checker.check(token)
        if decision.status is not AdmissionStatus.ALLOWED or decision.principal.subject not in self.controls.subjects:return None
        scope=scope_for(decision.principal.issuer,decision.principal.subject);exchange=str(uuid4())
        self._http(dict(version='G2C-App-smoke-HTTP.1',phase='started',exchange_id=exchange,
            policy_sha256=self.controls.window['policy_sha256'],scope_sha256=sha256(scope.encode()).hexdigest(),
            ts=datetime.fromtimestamp(self.clock(),timezone.utc).isoformat(),method=method,route=route))
        return scope,exchange

    def finish(self,identity,route,raw,*,status,request_id):
        scope,exchange=identity
        mid=None
        if raw is not None:
            try:
                command=DialogueMessage.parse(raw,version=ROUTES[route])
                if re.fullmatch('[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}',command.id):mid=command.id
            except InvalidInput:pass
        self._http(dict(version='G2C-App-smoke-HTTP.1',phase='finished',exchange_id=exchange,
            policy_sha256=self.controls.window['policy_sha256'],scope_sha256=sha256(scope.encode()).hexdigest(),
            ts=datetime.fromtimestamp(self.clock(),timezone.utc).isoformat(),method='POST',route=route,
            status=status,request_id=request_id,message_id=mid,
            body_fully_observed=raw is not None,input_sha256=None if raw is None else sha256(raw).hexdigest()))

    def submit(self,token,route,raw):
        self.controls.guard()
        command=DialogueMessage.parse(raw,version=ROUTES[route])
        if re.fullmatch('[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}',command.id)is None:return
        decision=self.checker.check(token)
        if decision.status is not AdmissionStatus.ALLOWED:return
        scope=scope_for(decision.principal.issuer,decision.principal.subject)
        if scope not in self.controls.scopes or not self.controls.permits(scope,command):return
        item=Received(token,scope,raw,route,command.id,sha256(raw).hexdigest(),min(self.controls.ends,self.clock()+90))
        self.queue.put_nowait(item)

    def submit_read(self,token,route,query,response,status,*,identity):
        self.controls.guard();decision=self.checker.check(token)
        if decision.status is not AdmissionStatus.ALLOWED or decision.principal.subject not in self.controls.subjects:return
        scope=scope_for(decision.principal.issuer,decision.principal.subject)
        if identity is None or identity[0]!=scope:raise Unavailable('APP_SMOKE_GET_EXCHANGE_REQUIRED')
        exchange=identity[1]
        try:selector=self._read_selector(route,query)
        except (ValueError,UnicodeError):selector=None
        self._http(dict(version='G2C-App-smoke-HTTP.1',phase='finished',exchange_id=exchange,
            policy_sha256=self.controls.window['policy_sha256'],scope_sha256=sha256(scope.encode()).hexdigest(),
            ts=datetime.fromtimestamp(self.clock(),timezone.utc).isoformat(),method='GET',route=route,
            selector=selector,status=status,body_fully_observed=response is not None,
            response_sha256=None if response is None else sha256(response).hexdigest()))
        if selector is None or status!=200 or response is None or len(response)>262144:
            self._read_outcome(scope,exchange,'UNKNOWN');return
        # A pending poll is not a future completed-read witness. Do not wait
        # ninety seconds at the head of the queue for an absent/old anchor.
        claim=self.controls.read_anchor(scope,route,selector,require_return=False)
        if claim is None:
            self._read_outcome(scope,exchange,'NOT_READY');return
        if claim.get('producer_return')is None:
            payload=decoded(response)
            # A completed HTTP snapshot may precede the worker-return witness
            # by a few instructions. Retain those actual bytes immediately;
            # ordinary in-progress polling is still not queued for ninety s.
            terminal=(route in('/v1/lio/timeline','/v2/lio/timeline')and
                any(row.get('message_id')==claim['binding']['message_id']and row.get('status')in('completed','failed')
                    for row in payload.get('messages',[])))
            if not terminal:
                self._read_outcome(scope,exchange,'NOT_READY');return
        try:self.read_queue.put_nowait(ReceivedRead(token,scope,route,selector,response,status,
            min(self.controls.ends,self.clock()+90),exchange))
        except Full:
            self._read_outcome(scope,exchange,'UNKNOWN');raise

    @staticmethod
    def _read_selector(route,query):
        if len(query)>2048:raise ValueError('bounded actual GET selector required')
        pairs=parse_qsl(query.decode('ascii'),keep_blank_values=True,strict_parsing=True)
        selector=dict(pairs)
        if len(selector)!=len(pairs):raise ValueError('duplicate App read selector')
        if route=='/v2/lio/messages':
            if set(selector)!={'message_id','input_sha256'}or re.fullmatch('[0-9a-f]{64}',selector['input_sha256'])is None:
                raise ValueError('exact original lookup required')
        elif route=='/v2/lio/timeline':
            if set(selector)!={'conversation_id'}or re.fullmatch('lio-dialogue-[0-9a-f]{32}',selector['conversation_id'])is None:
                raise ValueError('exact scoped timeline required')
        elif selector:raise ValueError('default timeline has no selector')
        return selector

    def _read_outcome(self,scope,exchange,status):
        self._http(dict(version='G2C-App-smoke-HTTP.1',phase='capture_result',exchange_id=exchange,
            policy_sha256=self.controls.window['policy_sha256'],scope_sha256=sha256(scope.encode()).hexdigest(),
            ts=datetime.fromtimestamp(self.clock(),timezone.utc).isoformat(),method='GET',capture_status=status))

    def _try_post(self,item):
        try:
            if self.stop.is_set()or self.clock()>=item.deadline:
                raise Unavailable('APP_SMOKE_OUTER_PRODUCER_NOT_OBSERVED')
            claim=self.controls.claim(item.scope,item.message_id)
            if claim is None or claim.get('producer_return')is None:return False
            self.publish(item,claim);return True
        except (OSError,ValueError,KeyError,Unavailable,BudgetUnknown):
            from .access_log import alert
            alert('app_smoke_outer_capture_unavailable')
            try:self._receipt(item,'UNKNOWN')
            except (OSError,ValueError,Unavailable):alert('app_smoke_outer_receipt_unavailable')
            return True

    def _read_once(self,item):
        try:
            if self.clock()>=item.deadline:raise Unavailable('APP_SMOKE_READ_CAPTURE_DEADLINE')
            claim=self.controls.read_anchor(item.scope,item.route,item.selector,require_return=False)
            if claim is None:raise Unavailable('APP_SMOKE_READ_ANCHOR_NOT_CLOSED')
            self.publish_read(item,claim)
            self._read_outcome(item.scope,item.exchange_id,'CAPTURED')
        except (OSError,ValueError,KeyError,Unavailable,BudgetUnknown):
            from .access_log import alert
            alert('app_smoke_read_capture_unavailable')
            try:self._read_outcome(item.scope,item.exchange_id,'UNKNOWN')
            except (OSError,ValueError,Unavailable):alert('app_smoke_read_receipt_unavailable')

    def _loop(self):
        # Checking a pending POST must not hold up any actual HTTP read for
        # its producer's potentially ninety-second wait. One native Runtime
        # still performs every protected publication serially.
        pending=None
        try:
            while not self.stop.is_set():
                if pending is None:
                    try:pending=self.queue.get_nowait()
                    except Empty:pass
                if pending is not None and self._try_post(pending):
                    self.queue.task_done();pending=None
                try:item=self.read_queue.get(timeout=.05)
                except Empty:continue
                try:self._read_once(item)
                finally:self.read_queue.task_done()
        finally:
            if pending is not None:
                self._try_post(pending)
                self.queue.task_done()

    def publish(self,item,claim):
        controls=self.controls
        def project(scope,original,source):
            r=original.receipt
            binding=Binding(scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
            from dataclasses import asdict
            if (scope!=item.scope or asdict(binding)!=claim['binding']or
                    sha256(original.raw).hexdigest()!=claim['canonical_sha256']or
                    r.input_sha256!=claim['canonical_sha256']or claim['input_sha256']!=item.input_sha256):
                raise Unavailable('APP_SMOKE_OUTER_NATIVE_BINDING_CHANGED')
            if source[0][0]!=claim['producer_return']['status']or source[0][1]!=binding.run_id:
                raise Unavailable('APP_SMOKE_OUTER_PRODUCER_STATE_CHANGED')
            controls.guard()
            if self.stop.is_set():raise Unavailable('APP_SMOKE_OUTER_OBSERVER_CLOSED')
            value=dict(version=OUTER,source_commit=controls.policy['source_commit'],
                policy_sha256=controls.window['policy_sha256'],slot_id=claim['slot_id'],
                binding=claim['binding'],input_sha256=item.input_sha256,canonical_sha256=claim['canonical_sha256'],
                method='POST',route=item.route,protocol=ROUTES[item.route],outer_utf8=item.raw.decode('utf-8'),
                observed_at=datetime.fromtimestamp(self.clock(),timezone.utc).isoformat())
            name=sha256(canonical([scope,item.message_id,item.input_sha256])).hexdigest()+'.json'
            stored=value
            with controls.directory()as directory:
                try:fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
                except FileExistsError:
                    prior=decoded(read_private(name,65536,directory_fd=directory))
                    if any(prior.get(k)!=v for k,v in value.items()if k!='observed_at'):
                        raise Unavailable('APP_SMOKE_OUTER_ORIGINAL_CHANGED')
                    stored=prior
                else:
                    with os.fdopen(fd,'wb')as output:
                        output.write(canonical(value));output.flush();os.fsync(output.fileno())
                    os.fsync(directory)
            return canonical(dict(file=name,sha256=sha256(canonical(stored)).hexdigest()))
        # The native reader owns the actual history AUTH/MESSAGE lifetime and
        # repeats its source checks. This reads no saved Memory or model raw.
        result=self.originals._read(item.token,item.message_id,project)
        controls.guard()
        self._receipt(item,'CAPTURED',decoded(result))
        return result

    def _receipt(self,item,status,descriptor=None):
        controls=self.controls
        name=sha256(canonical([item.scope,item.message_id,item.input_sha256])).hexdigest()
        receipt=dict(version='G2C-App-smoke-outer-receipt.1',status=status,
            source_commit=controls.policy['source_commit'],policy_sha256=controls.window['policy_sha256'],
            file=name+'.json',sha256=None if descriptor is None else descriptor['sha256'])
        with controls.directory()as directory:
            path=name+'.receipt.json'
            publish_marker(directory,path,receipt,keep_existing=status!='CAPTURED')

    def close(self):
        self.stop.set();self.thread.join(timeout=1)

    def publish_read(self,item,claim):
        controls=self.controls
        def project(scope,original,source):
            r=original.receipt
            from dataclasses import asdict
            b=Binding(scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
            if(scope!=item.scope or asdict(b)!=claim['binding']or sha256(original.raw).hexdigest()!=claim['canonical_sha256']):
                raise Unavailable('APP_SMOKE_HTTP_READ_OWNER_CHANGED')
            if claim.get('producer_return')is None and source[0][0]not in('completed','failed','cancelled','context_invalid','unknown'):
                raise Unavailable('APP_SMOKE_HTTP_READ_NOT_TERMINAL')
            payload=decoded(item.response)
            if item.route in('/v1/lio/timeline','/v2/lio/timeline')and payload.get('conversation_id')!=b.conversation_id:
                raise Unavailable('APP_SMOKE_HTTP_READ_CONVERSATION_CHANGED')
            controls.guard()
            value=dict(version='G2C-App-smoke-read.1',source_commit=controls.policy['source_commit'],
                policy_sha256=controls.window['policy_sha256'],scope_sha256=sha256(scope.encode()).hexdigest(),
                binding=claim['binding'],method='GET',route=item.route,selector=item.selector,status=item.status,
                exchange_id=item.exchange_id,
                response_utf8=item.response.decode('utf-8'),response_sha256=sha256(item.response).hexdigest(),
                observed_at=datetime.fromtimestamp(self.clock(),timezone.utc).isoformat())
            identity=sha256(canonical(value)).hexdigest()+'.read.json'
            with controls.directory()as directory:
                if sum(name.endswith('.read.json')for name in os.listdir(directory))>=MAX_READ_ARTIFACTS:
                    raise Unavailable('APP_SMOKE_READ_ARTIFACT_BOUND_REACHED')
                try:fd=os.open(identity,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
                except FileExistsError:
                    if read_private(identity,600000,directory_fd=directory)!=canonical(value):
                        raise Unavailable('APP_SMOKE_HTTP_READ_BYTES_CHANGED')
                else:
                    with os.fdopen(fd,'wb')as output:
                        output.write(canonical(value));output.flush();os.fsync(output.fileno())
                    os.fsync(directory)
            return canonical(dict(file=identity,sha256=sha256(canonical(value)).hexdigest()))
        result=self.originals._read(item.token,claim['binding']['message_id'],project)
        controls.guard();descriptor=decoded(result)
        marker=dict(version='G2C-App-smoke-read-receipt.1',status='CAPTURED',
            source_commit=controls.policy['source_commit'],policy_sha256=controls.window['policy_sha256'],**descriptor)
        with controls.directory()as directory:
            name=descriptor['file']+'.receipt'
            publish_marker(directory,name,marker)
        return result


class OuterMiddleware:
    def __init__(self,app,observer):self.app,self.observer=app,observer

    def capture_failure(self,code):
        from .access_log import alert
        alert(code)
        try:self.observer.mark_lost()
        except (OSError,ValueError,Unavailable,BudgetUnknown):alert('app_smoke_http_gap_marker_unavailable')

    async def __call__(self,scope,receive,send):
        if scope['type']=='http'and scope.get('method')=='GET'and scope.get('path')in READ_ROUTES:
            token=_token(Request(scope))
            if token is None or not self.observer.eligible(token):return await self.app(scope,receive,send)
            try:identity=self.observer.begin(token,scope['path'],method='GET')
            except (OSError,ValueError,Unavailable):
                identity=None;self.capture_failure('app_smoke_http_coverage_unavailable')
            response=bytearray();status=None;complete=False
            async def record(message):
                nonlocal response,status,complete
                if message['type']=='http.response.start':status=message['status']
                if message['type']=='http.response.body'and response is not None:
                    chunk=message.get('body',b'')
                    if len(response)+len(chunk)>262144:response=None
                    else:response.extend(chunk)
                await send(message)
                if message['type']=='http.response.body'and not message.get('more_body',False):complete=True
            try:await self.app(scope,receive,record)
            finally:
                raw=bytes(response)if response is not None and complete else None
                try:self.observer.submit_read(token,scope['path'],scope.get('query_string',b''),raw,status,identity=identity)
                except (OSError,ValueError,Unavailable,Full):
                    self.capture_failure('app_smoke_read_capture_unavailable')
            return
        if scope['type']!='http'or scope.get('method')!='POST'or scope.get('path')not in ROUTES:
            return await self.app(scope,receive,send)
        token=_token(Request(scope))
        if token is None or not self.observer.eligible(token):return await self.app(scope,receive,send)
        try:identity=self.observer.begin(token,scope['path'])
        except (OSError,ValueError,Unavailable):
            self.capture_failure('app_smoke_http_coverage_unavailable');identity=None
        body=bytearray();done=False
        status=request_id=None
        async def tap():
            nonlocal body,done
            message=await receive()
            if message['type']=='http.request':
                chunk=message.get('body',b'')
                if body is not None:
                    if len(body)+len(chunk)>MAX_BODY:body=None
                    else:body.extend(chunk)
                done=not message.get('more_body',False)
            return message
        async def observe(message):
            nonlocal status,request_id
            if message['type']=='http.response.start':
                status=message['status']
                for key,value in message.get('headers',()):
                    if key.lower()==b'x-request-id':
                        text=value.decode('ascii','replace')
                        if re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',text):request_id=text
            await send(message)
        try:await self.app(scope,tap,observe)
        finally:
            raw=bytes(body)if done and body is not None else None
            if identity is not None:
                try:self.observer.finish(identity,scope['path'],raw,status=status,request_id=request_id)
                except (OSError,ValueError,Unavailable):
                    self.capture_failure('app_smoke_http_coverage_unavailable')
            if done and body is not None:
                try:self.observer.submit(token,scope['path'],bytes(body))
                except (OSError,ValueError,InvalidInput,Unavailable,Full):
                    self.capture_failure('app_smoke_outer_enqueue_unavailable')


def create_capture(runtime,database,path):
    """API role uses only its existing public AUTH and scoped native reader."""
    from cj_api.local_account_admission_v2 import account_checker_for,retired_in_transaction
    from cj_api.local_worker_context import checker_for,checker_factory_for
    from cj_message.auth_boundary import Boundary
    controls=OuterControls(path,runtime.demo_subjects)
    subjects=controls.subjects
    checker=account_checker_for(runtime.auth,database,selected_subjects=subjects)
    builder=checker_factory_for(runtime.auth,selected_subjects=subjects)
    def in_transaction(tx,scope):return builder(retired_in_transaction(tx.cur,scope))
    boundary=Boundary(checker,lambda p:database.message_repository(scope_for(p.issuer,p.subject)),
        lambda:str(uuid4()),checker_in_transaction=in_transaction)
    originals=RuntimeOriginals(boundary,database,None,controls.window['directory'],
        query_original=lambda context,mid:context.query_lio_message(mid))
    return OuterCapture(controls,checker_for(runtime.auth,selected_subjects=subjects),originals)
