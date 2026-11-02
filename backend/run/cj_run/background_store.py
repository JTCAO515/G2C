"""RUN-BACKGROUND@1 original job records; no MESSAGE receipt or RUN reuse."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict,dataclass
import base64,hashlib,json,uuid
from cj_message.source import SourceQuery
from cj_message.travel import Selection
from cj_usage.core import Command,Config
from cj_strict_json import reject_duplicates
from .core import Conflict,Denied
from .step_usage import ledger_scope_for
from .usage_binding import UsageBinding,_decode_command

ABI='RUN-BACKGROUND@1'
REGISTRATION='memory.history-extract.1'
LEASE_NAMESPACE='background-job@1'
TABLE='cj_run_background_job'
STATES=('queued','running','publishing','completed','budget_exhausted','cancelled','unknown')


def pack(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def sha(raw):return hashlib.sha256(raw).hexdigest()


def _identity(value):
    if type(value) is not str or not value.strip() or len(value)>256 or '\0' in value:
        raise ValueError('original job identity required')
    if len(value.encode('utf-8'))>1024:raise ValueError('job identity byte bound')


@dataclass(frozen=True,repr=False)
class JobRequest:
    job_id:str
    attempt_id:str
    query:SourceQuery
    travel:Selection|None
    prepared_input:bytes

    def __post_init__(self):
        _identity(self.job_id);_identity(self.attempt_id)
        for raw,limit in ((self.prepared_input,1048576),):
            if type(raw) is not bytes or not 0<len(raw)<=limit:raise ValueError('bounded original job bytes required')
            raw.decode('utf-8')

    @property
    def prepared_sha256(self):return sha(self.prepared_input)

    def envelope(self,scope,run_id):
        return pack(dict(version=ABI,registration_id=REGISTRATION,run_id=run_id,scope_digest=sha(scope.encode()),
            job_id=self.job_id,attempt_id=self.attempt_id,source=asdict(self.query),
            travel=None if self.travel is None else asdict(self.travel),
            prepared_input_base64=base64.b64encode(self.prepared_input).decode('ascii')))


@dataclass(frozen=True)
class JobBinding:
    scope:str
    run_id:str

    @property
    def chat(self):
        # Physical lease namespace only. Never a MESSAGE conversation/generation.
        return self.scope,LEASE_NAMESPACE,self.run_id


@dataclass(frozen=True,repr=False)
class JobRecord:
    binding:JobBinding
    job_id:str
    attempt_id:str
    ledger_scope:str
    prepared_input_sha256:str
    config:Config
    command:Command
    command_bytes:bytes
    input_bytes:bytes|None
    request:JobRequest|None
    state:str
    output_sha256:str|None
    receipt_sha256:str|None

    def summary(self):
        return dict(version=ABI,job_id=self.job_id,attempt_id=self.attempt_id,run_id=self.binding.run_id,state=self.state,
            registration_id=REGISTRATION,meter_attempt_id=self.command.attempt_id,meter_operation_id=self.command.operation_id,
            prepared_input_sha256=self.prepared_input_sha256,
            operation_input_sha256=self.command.input_digest,output_sha256=self.output_sha256,receipt_sha256=self.receipt_sha256,
            input_state='erased' if self.request is None else 'retained',recovery='reconcile_original')


def _load(row,scope):
    jid,attempt,run_id,ledger,prepared_sha,config_raw,command_raw,input_raw,state,output,receipt=row
    _identity(jid);_identity(attempt)
    config=Config(**json.loads(bytes(config_raw)))
    command_raw=bytes(command_raw);input_raw=None if input_raw is None else bytes(input_raw)
    command=_decode_command(command_raw) if input_raw is None else UsageBinding(command_raw,input_raw).command
    if (command.run_id!=run_id or command.kind!='memory' or command.reserve!=1 or config.unit!='provider_call'
            or ledger!=ledger_scope_for(scope,config) or state not in STATES or command.output_limit>config.max_output):
        raise Denied('original background operation unavailable')
    request=None
    if input_raw is not None:
        value=json.loads(input_raw.decode('utf-8'),object_pairs_hook=reject_duplicates(ValueError,'duplicate job input'))
        if (set(value)!={'version','registration_id','run_id','scope_digest','job_id','attempt_id','source','travel','prepared_input_base64'}
                or (value['version'],value['registration_id'],value['run_id'],value['scope_digest'],value['job_id'],value['attempt_id'])
                !=(ABI,REGISTRATION,run_id,sha(scope.encode()),jid,attempt)):
            raise Denied('original job input unavailable')
        travel=None if value['travel'] is None else Selection(**value['travel'])
        request=JobRequest(jid,attempt,SourceQuery(**value['source']),travel,
            base64.b64decode(value['prepared_input_base64'],validate=True))
        if prepared_sha!=request.prepared_sha256:raise Denied('original prepared data digest unavailable')
    for value in (prepared_sha,output,receipt):
        if value is not None and (type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value)):
            raise Denied('original publication digest unavailable')
    if state=='completed' and (output is None or receipt is None):raise Denied('actual publication receipt unavailable')
    return JobRecord(JobBinding(scope,run_id),jid,attempt,ledger,prepared_sha,config,command,command_raw,input_raw,request,state,output,receipt)


class JobStore:
    def __init__(self,repository):
        self.repository=repository
        self.scope=repository.scope
        self._active=ContextVar('background_job_row',default=None)

    def _read(self,tx,jid,attempt,*,lock=False):
        tx.cur.execute('SELECT epoch,active FROM cj_run_scope WHERE scope=%s',(self.scope,))
        if tx.cur.fetchone()!=(tx.epoch,True):raise Denied('original job scope changed')
        tx.cur.execute('SELECT job_id,attempt_id,run_id,ledger_scope,prepared_input_sha256,config_bytes,command_bytes,input_bytes,state,output_sha256,receipt_sha256 '
            'FROM cj_run_background_job WHERE scope=%s AND job_id=%s AND attempt_id=%s'+(' FOR UPDATE' if lock else ''),(self.scope,jid,attempt))
        row=tx.cur.fetchone()
        return None if row is None else _load(row,self.scope)

    def read(self,jid,attempt):
        _identity(jid);_identity(attempt)
        active=self._active.get()
        if active is not None:return self._read(active,jid,attempt)
        with self.repository.job_transaction(require_clean_close=True) as tx:return self._read(tx,jid,attempt)

    def pending(self):
        with self.repository.job_transaction(require_clean_close=True) as tx:
            tx.cur.execute("SELECT job_id,attempt_id FROM cj_run_background_job WHERE scope=%s AND state='queued' AND input_bytes IS NOT NULL ORDER BY run_id",(self.scope,))
            return tuple(tx.cur.fetchall())

    def prepare(self,request,config,output_limit):
        run_id=uuid.uuid4().hex;raw=request.envelope(self.scope,run_id)
        command=Command(uuid.uuid4().hex,uuid.uuid4().hex,run_id,'memory',sha(raw),1,output_limit)
        binding=UsageBinding.from_command(command,raw)
        with self.repository.job_transaction() as tx:
            tx.cur.execute("INSERT INTO cj_run_background_job(scope,job_id,attempt_id,run_id,ledger_scope,prepared_input_sha256,config_bytes,command_bytes,input_bytes) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(scope,job_id,attempt_id) DO NOTHING",
                (self.scope,request.job_id,request.attempt_id,run_id,ledger_scope_for(self.scope,config),request.prepared_sha256,pack(asdict(config)),binding.command_bytes,raw))
            result=self._read(tx,request.job_id,request.attempt_id,lock=True)
            if result is None:raise Denied('original job unavailable')
            self.require_original(result,request,config,output_limit)
        return result

    def require_original(self,record,request,config,limit):
        if record.request is None:raise Denied('original job payload erased')
        if record.request!=request or record.config!=config or record.command.output_limit!=limit:
            raise Conflict('original background job bytes/configuration required')

    @contextmanager
    def hold(self,record):
        with self.repository.job_transaction() as tx:
            current=self._read(tx,record.job_id,record.attempt_id,lock=True)
            if current is None or current.binding!=record.binding:raise Denied('original job unavailable')
            token=self._active.set(tx)
            try:yield tx,current
            finally:self._active.reset(token)

    def transition(self,record,previous,state,*,output=None,receipt=None):
        with self.hold(record) as (tx,current):
            if current.state not in previous:raise Conflict('original job stage changed')
            self.write_state(tx,current,state,output=output,receipt=receipt)
        result=self.read(record.job_id,record.attempt_id)
        if result is None:raise Denied('original job unavailable')
        return result

    def write_state(self,tx,record,state,*,output=None,receipt=None):
        if ((output is not None and record.output_sha256 is not None and output!=record.output_sha256)
                or (receipt is not None and record.receipt_sha256 is not None and receipt!=record.receipt_sha256)):
            raise Conflict('original job result digest changed')
        tx.cur.execute('UPDATE cj_run_background_job SET state=%s,output_sha256=COALESCE(output_sha256,%s),receipt_sha256=COALESCE(receipt_sha256,%s) '
            'WHERE scope=%s AND run_id=%s',(state,output,receipt,self.scope,record.binding.run_id))
        if tx.cur.rowcount!=1:raise Denied('original job stage unavailable')
