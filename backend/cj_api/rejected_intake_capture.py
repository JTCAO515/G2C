"""Private rejected intake outputs: actual complete producer + definite Meter ACK.

No request/input copy, paid call, replay, public route or caller-selected path.
The consumer encloses stream+parse and rejects before leaving this lifetime.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime,timezone
from hashlib import sha256
import json,os,re,time,sys,stat,logging,secrets
from pathlib import Path

from cj_usage.authorization_budget import canonical
from cj_strict_json import reject_duplicates
from cj_usage.core import checked_clock_value
from cj_usage.metered_exit import BudgetUnknown
from .runtime_private import private_directory,read_private

TTL_SECONDS=7*86400
MAX_OUTPUT_BYTES=48000
MAX_ARTIFACT_BYTES=65536
REGISTRATION='model.lio_intake.9'
OPERATION_KEY='model.lio_intake.0'
_current=ContextVar('rejected_intake_current',default=None)
_sink=ContextVar('rejected_intake_sink',default=None)
_LIFETIME_FACTORY=object()


class CaptureUnavailable(BudgetUnknown,ValueError):
    """Configuration refuses startup; execution records original UNKNOWN."""
    pass


@dataclass(frozen=True)
class CaptureReceipt:
    status:str
    reference:str|None
    output_sha256:str
    output_bytes:int
    expires_at:str|None


class RejectedIntakeSink:
    def __init__(self,directory,*,clock=time.time):
        self.directory=Path(directory);self.clock=clock;self.next_prune=0
        with private_directory(self.directory,CaptureUnavailable('private rejection directory required')):pass

    def remove(self,reference):
        if re.fullmatch(r'[0-9a-f]{64}',reference)is None:raise CaptureUnavailable('private reference required')
        with private_directory(self.directory,CaptureUnavailable('private rejection directory required'))as fd:
            os.unlink(reference+'.json',dir_fd=fd)

    def _load(self,fd,name):
        try:
            data=json.loads(read_private(name,MAX_ARTIFACT_BYTES,directory_fd=fd),
                object_pairs_hook=reject_duplicates(CaptureUnavailable,'duplicate rejection field'))
            if data['version']!='G2C-rejected-intake.1'or data['reference']+'.json'!=name:
                raise CaptureUnavailable('original rejection artifact differs')
            raw=data['result_utf8'].encode('utf-8')
            if len(raw)!=data['output_bytes']or sha256(raw).hexdigest()!=data['output_sha256']:
                raise CaptureUnavailable('original rejection bytes differ')
            created=datetime.fromisoformat(data['captured_at']);end=datetime.fromisoformat(data['expires_at'])
            if created.tzinfo is None or end.tzinfo is None or(end-created).total_seconds()!=TTL_SECONDS:
                raise CaptureUnavailable('original bounded rejection retention required')
            return data,end.timestamp()
        except (KeyError,TypeError,ValueError,UnicodeError)as error:
            raise CaptureUnavailable('original rejection artifact invalid')from error

    def read(self,reference):
        """Internal storage bytes only; callers must retain original AUTH/source framing."""
        if re.fullmatch(r'[0-9a-f]{64}',reference)is None:raise CaptureUnavailable('private reference required')
        with private_directory(self.directory,CaptureUnavailable('private rejection directory required'))as fd:
            data,expires=self._load(fd,reference+'.json')
        if checked_clock_value(self.clock())>=expires:raise CaptureUnavailable('rejected output retention expired')
        return data

    def prune(self):
        now=checked_clock_value(self.clock())
        if now<self.next_prune:return
        next_prune=now+60
        with private_directory(self.directory,CaptureUnavailable('private rejection directory required'))as fd:
            for name in os.listdir(fd):
                try:info=os.stat(name,dir_fd=fd,follow_symlinks=False)
                except FileNotFoundError:continue
                owned=stat.S_ISREG(info.st_mode)and info.st_uid==os.getuid()
                partial=re.fullmatch(r'\.[0-9a-f]{64}\.[0-9a-f]{32}\.tmp',name)is not None
                final=re.fullmatch(r'[0-9a-f]{64}\.json',name)is not None
                if partial and owned:
                    expiry=info.st_mtime+60
                elif final and owned:
                    try:_,expiry=self._load(fd,name)
                    except (OSError,ValueError,CaptureUnavailable):
                        logging.getLogger('cj_usage.audit').warning('REJECTED_INTAKE_ARTIFACT_INVALID name_sha256=%s',sha256(name.encode()).hexdigest())
                        expiry=info.st_mtime+TTL_SECONDS
                else:
                    logging.getLogger('cj_usage.audit').warning('REJECTED_INTAKE_UNKNOWN_ENTRY name_sha256=%s',sha256(name.encode()).hexdigest())
                    continue
                if now>=expiry:
                    try:os.unlink(name,dir_fd=fd)
                    except FileNotFoundError:pass
                else:next_prune=min(next_prune,expiry)
        self.next_prune=next_prune

    def persist(self,operation,raw,metadata,memory,code,check):
        self.prune();now=checked_clock_value(self.clock());expires=datetime.fromtimestamp(now+TTL_SECONDS,timezone.utc).isoformat()
        ref=sha256(canonical([operation.binding.scope,operation.binding.run_id,
            operation.operation_key,operation.command.attempt_id])).hexdigest()
        value=dict(version='G2C-rejected-intake.1',reference=ref,registration_id=REGISTRATION,
            operation_key=OPERATION_KEY,scope_sha256=sha256(operation.binding.scope.encode()).hexdigest(),
            message_id=operation.binding.message_id,run_id=operation.binding.run_id,
            attempt_id=operation.command.attempt_id,operation_id=operation.command.operation_id,
            input_sha256=operation.command.input_digest,output_sha256=sha256(raw).hexdigest(),
            output_bytes=len(raw),result_utf8=raw.decode('utf-8'),receipt=dict(metadata),code=code,
            memory=memory,kernel_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            captured_at=datetime.fromtimestamp(now,timezone.utc).isoformat(),expires_at=expires)
        encoded=canonical(value)
        if len(encoded)>MAX_ARTIFACT_BYTES:raise CaptureUnavailable('rejection artifact bound exceeded')
        with private_directory(self.directory,CaptureUnavailable('private rejection directory required'))as fd:
            check()
            temporary='.'+ref+'.'+secrets.token_hex(16)+'.tmp'
            published=False
            out=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
            try:
                with os.fdopen(out,'wb')as target:
                    target.write(encoded);target.flush();os.fsync(target.fileno())
                    check()
                check()
                os.link(temporary,ref+'.json',src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
                published=True
                os.fsync(fd);check()
            except BaseException:
                if published:os.unlink(ref+'.json',dir_fd=fd)
                raise
            finally:
                try:os.unlink(temporary,dir_fd=fd)
                except FileNotFoundError:pass
        return CaptureReceipt('CAPTURED',ref,value['output_sha256'],len(raw),expires)


class OriginalIntakeReadLifetime:
    """Opaque original producer lifetime, never reconstructed from persisted refs."""
    def __init__(self,capture,*,_factory):
        if _factory is not _LIFETIME_FACTORY:raise CaptureUnavailable('actual producer lifetime required')
        self.capture=capture

    @contextmanager
    def hold(self,context,binding,operation_id,input_sha256,descriptor):
        capture=self.capture
        if not capture.active or capture.observed is None or capture.settled is None:
            raise CaptureUnavailable('original producer lifetime ended')
        operation,_,_,lifetime,original_descriptor=capture.observed
        if (context.scope!=binding.scope or operation.binding!=binding
                or operation.command.operation_id!=operation_id
                or operation.command.input_digest!=input_sha256 or original_descriptor!=descriptor):
            raise CaptureUnavailable('original producer association changed')
        context.principal
        capture.check_running()
        with lifetime()as check:
            check();yield check;check()


class IntakeCapture:
    def __init__(self,binding,check_running):
        self.binding,self.check_running=binding,check_running
        self.sink=_sink.get();self.active=True;self.observed=None;self.settled=None;self.result=None

    def observe(self,operation,raw,metadata,lifetime,memory=None):
        if not self.active:raise CaptureUnavailable('intake capture lifetime ended')
        if self.sink is None:return
        if (operation.binding!=self.binding or operation.registration_id!=REGISTRATION
                or operation.operation_key!=OPERATION_KEY or operation.command.kind!='model'):
            raise CaptureUnavailable('original intake binding changed')
        if self.observed is not None:raise CaptureUnavailable('original intake already observed')
        if len(raw)>MAX_OUTPUT_BYTES:raise CaptureUnavailable('rejected output bound exceeded')
        raw.decode('utf-8')
        receipt={key:metadata[key]for key in ('receipt_sha256','model_id','endpoint','region','usage','response_id')if key in metadata}
        self.observed=(operation,raw,receipt,lifetime,memory)

    def acknowledge(self,operation,attempt):
        if self.observed is None:return
        original,raw,metadata,_,_=self.observed
        if (operation!=original or attempt.command!=original.command or attempt.state!='settled'
                or attempt.cancelled or attempt.exceeded or attempt.receipt is None
                or attempt.receipt.receipt_id!='live:'+metadata['receipt_sha256']
                or attempt.receipt.actual!=1 or attempt.receipt.output!=len(raw.decode('utf-8'))):
            raise CaptureUnavailable('definite original intake settlement required')
        self.settled=attempt

    def reject(self,code,output_utf8):
        digest=sha256(output_utf8).hexdigest()
        if not self.active:raise CaptureUnavailable('intake capture lifetime ended')
        if re.fullmatch(r'[a-z][a-z0-9_.:-]{0,95}',code)is None:raise CaptureUnavailable('diagnostic code required')
        if self.observed is None or self.settled is None:
            return CaptureReceipt('NOT_CAPTURED',None,digest,len(output_utf8),None)
        operation,raw,metadata,lifetime,memory=self.observed
        if raw!=output_utf8:raise CaptureUnavailable('rejected bytes differ from actual producer')
        created=None
        try:
            with lifetime()as source_check:
                def check():
                    self.check_running();source_check()
                check()
                if self.result is not None:return self.result
                created=self.sink.persist(operation,raw,metadata,memory,code,check)
            self.result=created
            return self.result
        except BaseException:
            if created is not None:self.sink.remove(created.reference)
            raise

    def read_lifetime(self):
        if not self.active or self.observed is None or self.settled is None:
            raise CaptureUnavailable('actual complete producer lifetime required')
        return OriginalIntakeReadLifetime(self,_factory=_LIFETIME_FACTORY)

    def close(self):
        self.active=False;self.observed=None;self.settled=None


@contextmanager
def use_rejected_intake_sink(sink):
    token=_sink.set(sink)
    try:yield
    finally:_sink.reset(token)


@contextmanager
def capture_rejected_intake(binding,*,check_running):
    if _current.get()is not None:raise CaptureUnavailable('nested intake capture prohibited')
    capture=IntakeCapture(binding,check_running);token=_current.set(capture)
    try:yield capture
    finally:capture.close();_current.reset(token)


def observe_complete(operation,raw,metadata,lifetime):
    capture=_current.get()
    if capture is not None:capture.observe(operation,raw,metadata,lifetime)


def acknowledge_settlement(operation,attempt):
    capture=_current.get()
    if capture is not None:capture.acknowledge(operation,attempt)


def observe_stream(operation,stream,metadata,lifetime,memory=None):
    capture=_current.get()
    if capture is None or capture.sink is None:
        yield from stream
        return
    chunks=[]
    try:
        for part in stream:
            chunks.append(part)
            yield part
        with lifetime()as check:
            check();capture.observe(operation,''.join(chunks).encode('utf-8'),metadata,lifetime,memory);check()
    finally:
        primary=sys.exception()
        try:stream.close()
        except Exception:
            if primary is not None:primary.add_note('original intake stream cleanup failed')
            else:raise CaptureUnavailable('original intake stream cleanup unavailable')from None


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Prune only expired private rejected outputs; no provider/database access.')
    parser.add_argument('--prune',type=Path,required=True)
    args=parser.parse_args()
    RejectedIntakeSink(args.prune).prune()
    print('REJECTED_INTAKE_PRUNE_COMPLETE')


if __name__=='__main__':main()
