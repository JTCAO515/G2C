"""RUN-owned immutable local step association. No provider dispatch authority."""
from dataclasses import dataclass
import hashlib
import json
import uuid
from cj_usage.core import Command, Config
from .core import Denied
from .usage_binding import UsageBinding


class OriginalStepOnly(Exception):
    """An original exists or cannot be established; query it, never replace it."""


def ledger_scope_for(message_scope, config):
    raw=json.dumps([message_scope,config.unit,config.period_start,config.period_end],
                   ensure_ascii=False,separators=(',',':')).encode('utf-8')
    return 'u'+hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, repr=False)
class Step:
    binding: object
    step_key: str
    ledger_scope: str
    period: tuple[int, int]
    original: UsageBinding

    @property
    def command(self):
        return self.original.command


class StepStore:
    def __init__(self, runs, config: Config, *, new_id=lambda:uuid.uuid4().hex):
        if config.unit != 'provider_call':
            raise ValueError('explicit local provider_call profile required')
        self.runs,self.config,self.new_id=runs,config,new_id

    def _read(self, tx, binding, step_key):
        tx.cur.execute('SELECT attempt_id,ledger_scope,unit,period_start,period_end,command_bytes,input_bytes '
                       'FROM cj_run_step_usage WHERE scope=%s AND run_id=%s AND step_key=%s',
                       (binding.scope,binding.run_id,step_key))
        row=tx.cur.fetchone()
        if row is None: return None
        original=UsageBinding(bytes(row[5]),bytes(row[6]))
        original.check_run(binding.run_id)
        if (original.command.attempt_id != row[0] or original.command.kind != 'model'
                or original.command.reserve != 1 or row[2] != 'provider_call'
                or (row[3],row[4]) != (self.config.period_start,self.config.period_end)
                or row[1] != ledger_scope_for(binding.scope,self.config)):
            raise OriginalStepOnly('original step integrity or period unavailable')
        return Step(binding,step_key,row[1],(row[3],row[4]),original)

    def create(self, binding, step_key, input_bytes, output_limit):
        """Stage A: only a positively acknowledged NEW association may continue.

        Caller is the newly started worker under its original worker lease. Existing
        running work is recovered as UNKNOWN before this method is reached. A failed
        commit/close never returns Step; reconstruction has read_original only.
        """
        if step_key not in ('answer','draft') or type(input_bytes) is not bytes:
            raise ValueError('fixed local step and original bytes required')
        result=None
        with self.runs.repository.transaction() as tx:
            state=tx.get(binding)
            if state.status != 'running' or self.runs.valid(binding) is not True:
                raise Denied('original run cannot prepare step')
            if self._read(tx,binding,step_key) is not None:
                raise OriginalStepOnly('original step already exists')
            command=Command(self.new_id(),self.new_id(),binding.run_id,'model',
                            hashlib.sha256(input_bytes).hexdigest(),1,output_limit)
            original=UsageBinding.from_command(command,input_bytes)
            encoded=original.command_bytes
            account=ledger_scope_for(binding.scope,self.config)
            tx.cur.execute('INSERT INTO cj_run_step_usage '
                '(scope,run_id,step_key,attempt_id,ledger_scope,unit,period_start,period_end,command_bytes,input_bytes) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (binding.scope,binding.run_id,step_key,command.attempt_id,account,self.config.unit,
                 self.config.period_start,self.config.period_end,encoded,input_bytes))
            if tx.get(binding)!=state or self.runs.valid(binding) is not True:
                raise Denied('original run changed during preparation')
            result=Step(binding,step_key,account,(self.config.period_start,self.config.period_end),original)
        return result

    def read_original(self, binding, step_key):
        """Read only within an explicitly retained original period configuration.

        Missing historical config/RLS visibility is unavailable, not a new step.
        This return value alone never grants reserve, claim or execution.
        """
        with self.runs.repository.transaction() as tx:
            tx.get(binding)
            if self.runs.valid(binding) is not True: raise Denied('original run unavailable')
            result=self._read(tx,binding,step_key)
            if result is None: raise OriginalStepOnly('original step unavailable')
        return result
