"""Explicit one-dispatch weather failure fixture; no vendor request or receipt.

The original weather registration validates parameters/identity first. Its
RegisteredExit owns Meter reserve/claim/settlement. This fixture never invokes
the vendor closure and never creates a financial attempt. A private artifact is
bound to the actual settled Meter receipt, not presented as Gaode evidence.
"""
from datetime import timedelta
from hashlib import sha256
import os
from pathlib import Path
import stat
import re

from cj_message.lio_context import original_for
from cj_usage.core import Receipt
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.registered_exit import InvocationInput,Registration
from runtime_adapter.contract import decode,encode,require,Unavailable

from .runtime_private import read_private

VERSION='G2C-runtime-weather-fault.1'
PREFIX='fixture-weather-not-sent:'
TASK='dev-tool-failure'


def artifact_name(scope,run_id,operation_key,attempt_id):
    return 'weather-fault-'+sha256(encode([scope,run_id,operation_key,attempt_id])).hexdigest()+'.json'


def _directory(path):
    descriptor=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    info=os.fstat(descriptor)
    if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        os.close(descriptor)
        raise Unavailable('WEATHER_FAULT_ARTIFACT_AUTHORITY')
    return descriptor


class NativeWeatherFault:
    def __init__(self,claims,routing,database,budget,directory,pins,token_supplier):
        self.claims,self.routing,self.database=claims,routing,database
        self.budget,self.directory,self.pins,self.token_supplier=budget,Path(directory),pins,token_supplier
        self.used=set()

    def _selected_request(self,request):
        if request is None or request['kind']!='message' or not request['prior_step_ids']:return False
        setup=decode(self.claims.read(request['prior_step_ids'][0],deadline=self.routing.clock()+30))
        return setup['kind']=='task_setup' and setup['payload']['task_id']==TASK

    def selected(self,binding):
        # The native source lease may already own MESSAGE locks here. Reuse
        # the worker's proved binding and current canonical/AUTH recheck;
        # never re-enter a MESSAGE transaction inside its registered call.
        if not self.routing.selects(binding):return False
        request=decode(self.claims.read(binding.message_id,deadline=self.routing.clock()+30))
        return self._selected_request(request)

    def wrap(self,registrations,binding,request):
        if not self._selected_request(request):return registrations
        original=registrations['tool.weather']
        def prepare(argument):
            native=original.prepare_input(argument)
            query=decode(native.original_bytes)['query']
            source=original_for(self.database,binding)
            if source is None or source.question_day is None:
                raise BudgetUnknown('original weather question day unavailable')
            day=(source.question_day+timedelta(days=1)).isoformat()
            if (query['fact_key']!='weather' or query['region'] not in ('beijing','110000','北京') or
                    query['dates']!={'start':day,'end':day} or
                    query['conditions'].get('calendar_timezone')!='Asia/Shanghai'):
                raise BudgetUnknown('weather fault requires the original Beijing next-day query')
            marker={}
            def bind(operation,guard):
                # Preserve the real registration's current scope/identity checks.
                # Obtaining its closure does not call or reserve the vendor.
                native.bind_operation(operation,guard)
                def invoke():
                    if guard() is not True or not self.selected(operation.binding):
                        raise BudgetUnknown('original weather fault authority unavailable')
                    key=(operation.binding.scope,operation.binding.message_id)
                    if key in self.used:raise BudgetUnknown('original weather fault already dispatched; query only')
                    self.used.add(key)
                    with self.budget.connect() as journal:
                        journal.execute('BEGIN');self.budget.require_producer(journal)
                        if journal.execute('SELECT 1 FROM attempt WHERE id=?',(operation.command.attempt_id,)).fetchone() is not None:
                            raise BudgetUnknown('weather fault must not replace a financial original')
                    result=encode(dict(source_url=None,status='error',reason='synthetic_definite_weather_failure',
                        fault_injected=True,vendor_sent=False,region_adcode='110000',calendar_timezone='Asia/Shanghai',
                        requested_date=day,request_day=source.question_day.isoformat(),query_day=day,
                        original_dispatches=1,vendor_sends=0,forecasts=[]))
                    record=dict(version=VERSION,source_commit=self.pins.value['code_sha'],
                        scope_sha256=sha256(operation.binding.scope.encode()).hexdigest(),
                        message_id=operation.binding.message_id,run_id=operation.binding.run_id,
                        operation_key=operation.operation_key,registration_id=operation.registration_id,
                        attempt_id=operation.command.attempt_id,operation_id=operation.command.operation_id,
                        input_sha256=operation.command.input_digest,request_day=source.question_day.isoformat(),
                        query_day=day,original_dispatches=1,vendor_sends=0,
                        result_utf8=result.decode(),output_sha256=sha256(result).hexdigest())
                    raw=encode(record);marker['receipt_id']=PREFIX+sha256(raw).hexdigest()
                    directory=_directory(self.directory)
                    try:
                        descriptor=os.open(artifact_name(operation.binding.scope,operation.binding.run_id,
                            operation.operation_key,operation.command.attempt_id),
                            os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
                        with os.fdopen(descriptor,'wb') as output:
                            output.write(raw);output.flush();os.fsync(output.fileno())
                        os.fsync(directory)
                    finally:os.close(directory)
                    if guard() is not True:raise BudgetUnknown('weather fault authority changed before result')
                    yield result.decode()
                return invoke
            def receipt(attempt,unit,output):
                return Receipt(attempt,marker['receipt_id'],unit,1,output)
            return InvocationInput(native.original_bytes,None,bind,receipt)
        return {**registrations,'tool.weather':Registration('tool',prepare)}


def read_artifact(originals,scope,stored,snapshot,row,usage):
    if usage.command.kind!='tool' or row[1]!='tool.weather':
        raise Unavailable('UNSENT_OUTPUT_IS_NOT_WEATHER_FIXTURE')
    directory=_directory(originals.directory)
    try:raw=read_private(artifact_name(scope,stored.receipt.run_id,row[0],usage.command.attempt_id),65536,directory_fd=directory)
    finally:os.close(directory)
    value=decode(raw)
    fields={'version','source_commit','scope_sha256','message_id','run_id','operation_key','registration_id',
        'attempt_id','operation_id','input_sha256','request_day','query_day','original_dispatches','vendor_sends',
        'result_utf8','output_sha256'}
    require(type(value) is dict and set(value)==fields and type(value['result_utf8']) is str and
        type(value['source_commit']) is str and re.fullmatch('[a-f0-9]{40}',value['source_commit']) is not None and
        type(value['original_dispatches']) is int and type(value['vendor_sends']) is int,'WEATHER_FAULT_ARTIFACT_FIELDS')
    expected=dict(version=VERSION,scope_sha256=sha256(scope.encode()).hexdigest(),
        message_id=stored.receipt.message_id,run_id=stored.receipt.run_id,operation_key=row[0],
        registration_id=row[1],attempt_id=row[3],operation_id=row[4],input_sha256=usage.command.input_digest,
        original_dispatches=1,vendor_sends=0)
    if any(value.get(key)!=item for key,item in expected.items()):
        raise Unavailable('WEATHER_FAULT_ORIGINAL_BINDING_CHANGED')
    from cj_run.core import Binding
    receipt=stored.receipt
    source=original_for(originals.database,Binding(scope,receipt.conversation_id,receipt.generation,
        receipt.message_id,receipt.run_id,receipt.sequence))
    logical=decode(usage.input_bytes)
    require(type(logical) is dict and logical.get('name')=='weather' and type(logical.get('query')) is dict,
        'WEATHER_FAULT_ORIGINAL_INPUT_FIELDS')
    query=logical['query']
    require(type(query.get('dates')) is dict and type(query.get('conditions')) is dict,'WEATHER_FAULT_ORIGINAL_QUERY_FIELDS')
    if source is None or source.question_day is None:raise Unavailable('WEATHER_FAULT_QUESTION_DAY_UNAVAILABLE')
    expected_day=(source.question_day+timedelta(days=1)).isoformat()
    if (value['request_day']!=source.question_day.isoformat() or value['query_day']!=expected_day or
            query['fact_key']!='weather' or query['region'] not in ('beijing','110000','北京') or
            query['dates']!={'start':expected_day,'end':expected_day} or
            query['conditions'].get('calendar_timezone')!='Asia/Shanghai'):
        raise Unavailable('WEATHER_FAULT_ORIGINAL_QUERY_CHANGED')
    result=value['result_utf8'].encode()
    if sha256(result).hexdigest()!=value['output_sha256']:
        raise Unavailable('WEATHER_FAULT_OUTPUT_HASH_CHANGED')
    meter=decode(originals._meter(scope,snapshot,row,usage))
    receipt=meter['receipt']
    if (meter['state']!='settled' or receipt is None or
            receipt['receipt_id']!=PREFIX+sha256(raw).hexdigest() or receipt['attempt_id']!=row[3] or
            receipt['actual']!=1 or receipt['output']!=len(value['result_utf8'])):
        raise Unavailable('WEATHER_FAULT_ORIGINAL_METER_RECEIPT_CHANGED')
    # The caller already proved this exact attempt has no financial row under
    # the original producer. Do not invent a vendor/fee receipt for the fixture.
    return raw
