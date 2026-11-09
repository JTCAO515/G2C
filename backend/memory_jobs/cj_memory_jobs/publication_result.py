"""Original publication receipts; stored data is historical, never a source grant."""
from hashlib import sha256

from cj_memory.domain import InvalidInput as MemoryInvalidInput,strict_object
from cj_message.travel import Selection
from cj_memory.typed import parse_stored
from .codec import Unavailable,InvalidInput,integer,pg_identity
from .extraction import decode_output,InvalidExtraction
from .publication import build_command
from .postgres import encode

VERSION='MEMORY-PUBLICATION-result@1'
VERSION_V2='MEMORY-PUBLICATION-result@2'
VERSION_DEMO='MEMORY-PUBLICATION-result@4'
FIELDS={'version','job_id','attempt_id','enqueue_input_sha256','prepared_input_sha256','model_output_sha256','receipts'}
RECEIPT_FIELDS={'operation_id','item_id','version','status','input_sha256'}


def _digest(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def is_demo_candidate(entry):
    return entry.extent=='long_term' and entry.kind in ('fact','preference')


def encode_result(status,prepared_input_sha256,model_output_sha256,receipts,*,version=VERSION):
    raw=encode(dict(version=version,job_id=status.job_id,attempt_id=status.attempt_id,
        enqueue_input_sha256=status.input_sha256,prepared_input_sha256=prepared_input_sha256,
        model_output_sha256=model_output_sha256,receipts=receipts))
    if len(raw)>16384:raise ValueError('original publication receipt exceeds candidate bound')
    return raw


def decode_result(raw,status,model_output,*,versions=(VERSION,VERSION_V2)):
    try:
        value=strict_object(raw)
        if (type(value) is not dict or set(value)!=FIELDS or value['version'] not in versions
                or value['job_id']!=status.job_id or value['attempt_id']!=status.attempt_id
                or value['enqueue_input_sha256']!=status.input_sha256
                or not _digest(value['prepared_input_sha256'])
                or not _digest(value['model_output_sha256'])
                or model_output is None or value['model_output_sha256']!=sha256(model_output).hexdigest()
                or type(value['receipts']) is not list or len(value['receipts'])>100):
            raise Unavailable('original publication receipt unavailable')
        seen=set()
        for receipt in value['receipts']:
            if type(receipt) is not dict or set(receipt)!=RECEIPT_FIELDS:
                raise Unavailable('original publication result unavailable')
            operation=pg_identity(receipt['operation_id'],4096)
            pg_identity(receipt['item_id'],4096);integer(receipt['version'],1)
            if (operation in seen or receipt['status'] not in ('active','candidate')
                    or not _digest(receipt['input_sha256'])):
                raise Unavailable('original publication result unavailable')
            seen.add(operation)
        return value
    except (MemoryInvalidInput,InvalidInput,RecursionError):
        raise Unavailable('original publication receipt unavailable') from None


def original_result(tx,job_id,attempt_id,*,expected_version=VERSION):
    row,output=tx.output(job_id,attempt_id)
    if row[0].state!='completed':return None
    demo=expected_version==VERSION_DEMO
    value=decode_result(row[6],row[0],output,versions=(VERSION_DEMO,) if demo else (VERSION,VERSION_V2))
    if value['version']!=expected_version:raise Unavailable('explicit original publication version required')
    messages=row[4]
    try:
        if expected_version in (VERSION_V2,VERSION_DEMO):
            from .model_v2 import decode_output as decode_v2
            entries=decode_v2(output,messages,tx.scope)
        else:entries=decode_output(output,messages)
    except InvalidExtraction:
        raise Unavailable('original model output unavailable') from None
    if demo:
        if len(messages)!=1 or any(receipt['status']!='candidate' for receipt in value['receipts']):
            raise Unavailable('original Demo candidate publication differs')
        entries=tuple(entry for entry in entries if is_demo_candidate(entry))
    if len(entries)!=len(value['receipts']):
        raise Unavailable('original publication entry count differs')
    for entry,receipt in zip(entries,value['receipts']):
        operation=tx.memory.operation(receipt['operation_id'])
        if operation is None:
            raise Unavailable('original canonical publication receipt unavailable')
        stored=operation[1]
        if entry.kind=='inference' and stored.status!='candidate':
            raise Unavailable('original inference publication is not a candidate')
        try:command=parse_stored(operation[0])
        except MemoryInvalidInput:
            raise Unavailable('original canonical command unavailable') from None
        if command.extent=='long_term':context=None
        elif command.context_kind=='travel':context=Selection(command.context_id,command.context_version)
        else:raise Unavailable('original canonical context unavailable')
        if build_command(tx.scope,entry,messages,context).raw!=operation[0]:
            raise Unavailable('original canonical command differs from model source')
        if receipt!=dict(operation_id=stored.operation_id,item_id=stored.item_id,version=stored.version,
                         status=stored.status,input_sha256=stored.input_sha256):
            raise Unavailable('original canonical publication result differs')
    return row[6]
