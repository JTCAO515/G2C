"""RUN-USAGE-OPERATIONS@1 storage, with no dispatch from original reads."""
from dataclasses import dataclass
import hashlib
import uuid
from cj_usage.core import Command, label, Blocked
from .core import Denied
from .step_usage import ledger_scope_for, OriginalStepOnly
from .usage_binding import UsageBinding

ABI = 'RUN-USAGE-OPERATIONS@1'


@dataclass(frozen=True, repr=False)
class RegisteredOperation:
    binding: object
    operation_key: str
    registration_id: str
    ledger_scope: str
    period: tuple[int, int]
    original: UsageBinding

    @property
    def command(self): return self.original.command


class OperationStore:
    def __init__(self, runs, config, *, new_id=lambda:uuid.uuid4().hex):
        self.runs,self.config,self.new_id=runs,config,new_id

    def bind_period_without_operation(self,binding):
        """Pin the zero-model RUN's original account; never creates an operation."""
        with self.runs.repository.transaction() as tx:
            state=tx.get(binding)
            if state.status!='queued' or self.runs.valid(binding) is not True:
                raise Denied('new original RUN required for zero-model clock')
            expected=(ledger_scope_for(binding.scope,self.config),'provider_call',self.config.period_start,self.config.period_end,ABI)
            tx.cur.execute('INSERT INTO cj_run_metered_binding VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(binding.scope,binding.run_id,*expected))
            tx.cur.execute('SELECT ledger_scope,unit,period_start,period_end,source_abi FROM cj_run_metered_binding WHERE scope=%s AND run_id=%s',(binding.scope,binding.run_id))
            if tx.cur.fetchone()!=expected:raise OriginalStepOnly('original zero-model period mismatch')

    def _read(self, tx, binding, key):
        tx.cur.execute('SELECT o.registration_id,o.kind,o.attempt_id,o.operation_id,o.ledger_scope,'
                       'b.unit,b.period_start,b.period_end,b.source_abi,o.command_bytes,o.input_bytes '
                       'FROM cj_run_metered_operation o JOIN cj_run_metered_binding b '
                       'ON (b.scope,b.run_id,b.ledger_scope)=(o.scope,o.run_id,o.ledger_scope) '
                       'WHERE o.scope=%s AND o.run_id=%s AND o.operation_key=%s',
                       (binding.scope,binding.run_id,key))
        row=tx.cur.fetchone()
        if row is None: return None
        try: label(row[0])
        except Blocked:
            raise OriginalStepOnly('original registration unavailable') from None
        original=UsageBinding(bytes(row[9]),bytes(row[10]));command=original.command
        if (row[8]!=ABI or row[5]!='provider_call' or (row[6],row[7])!=(self.config.period_start,self.config.period_end)
                or row[4]!=ledger_scope_for(binding.scope,self.config)
                or (row[1],row[2],row[3])!=(command.kind,command.attempt_id,command.operation_id)
                or command.run_id!=binding.run_id or command.reserve!=1):
            raise OriginalStepOnly('original registered operation unavailable')
        return RegisteredOperation(binding,key,row[0],row[4],(row[6],row[7]),original)

    def create(self, binding, key, registration_id, kind, input_bytes, output_limit):
        with self.runs.repository.transaction() as tx:
            state=tx.get(binding)
            if state.status!='running' or self.runs.valid(binding) is not True:
                raise Denied('original run cannot prepare registered operation')
            if self._read(tx,binding,key) is not None:
                raise OriginalStepOnly('original operation already exists')
            account=ledger_scope_for(binding.scope,self.config)
            tx.cur.execute('SELECT ledger_scope,unit,period_start,period_end,source_abi '
                           'FROM cj_run_metered_binding WHERE scope=%s AND run_id=%s',
                           (binding.scope,binding.run_id))
            old=tx.cur.fetchone()
            expected=(account,'provider_call',self.config.period_start,self.config.period_end,ABI)
            if old is None:
                # A hidden historical row conflicts on its original primary key.
                tx.cur.execute('INSERT INTO cj_run_metered_binding VALUES(%s,%s,%s,%s,%s,%s,%s)',
                               (binding.scope,binding.run_id,*expected))
            elif old!=expected:
                raise OriginalStepOnly('original run partition changed')
            command=Command(self.new_id(),self.new_id(),binding.run_id,kind,
                            hashlib.sha256(input_bytes).hexdigest(),1,output_limit)
            original=UsageBinding.from_command(command,input_bytes)
            tx.cur.execute('INSERT INTO cj_run_metered_operation VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                           (binding.scope,binding.run_id,key,account,registration_id,kind,command.attempt_id,
                            command.operation_id,original.command_bytes,input_bytes))
            if tx.get(binding)!=state or self.runs.valid(binding) is not True:
                raise Denied('original run changed during operation preparation')
            result=RegisteredOperation(binding,key,registration_id,account,
                                       (self.config.period_start,self.config.period_end),original)
        return result

    def read_original(self, binding, key):
        with self.runs.repository.transaction() as tx:
            tx.get(binding)
            if self.runs.valid(binding) is not True: raise Denied('original run unavailable')
            result=self._read(tx,binding,key)
            if result is None: raise OriginalStepOnly('original operation unavailable')
        return result
