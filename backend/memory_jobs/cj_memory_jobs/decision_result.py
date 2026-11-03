"""Original Pub3 receipts, independent of current Trip/history admission."""
from cj_memory.domain import strict_object,InvalidInput as MemoryInvalid
from cj_memory.typed import parse_stored
from cj_message.travel import Selection
from .codec import Unavailable
from .postgres import encode
from .publication_result import decode_result,FIELDS,VERSION_V2
from .decision_batch import decoded
from .decision_input import source_digest
from .decision_output import _translated
from .extraction import _decode_value,InvalidExtraction
from .decision_publication import command_for
from .model_v2 import origin_reference

VERSION='MEMORY-PUBLICATION-result@3'


def encoded(status,prepared_sha,output_sha,receipts,digest):
    raw=encode(dict(version=VERSION,job_id=status.job_id,attempt_id=status.attempt_id,
        enqueue_input_sha256=status.input_sha256,prepared_input_sha256=prepared_sha,model_output_sha256=output_sha,
        receipts=receipts,decision_source_sha256=digest))
    if len(raw)>16384:raise ValueError('original decision receipt exceeds bound')
    return raw


def original_result(tx,jid,attempt):
    row,output=tx.output(jid,attempt)
    if row[0].state!='completed':return None
    try:
        value=strict_object(row[6])
        if type(value) is not dict or set(value)!=FIELDS|{'decision_source_sha256'} or value['version']!=VERSION:
            raise Unavailable('explicit original decision publication required')
        _,messages,_,decision=decoded(row[2]);digest=source_digest(tx.scope,decision)
        if value['decision_source_sha256']!=digest:raise Unavailable('original decision receipt source differs')
        base=dict(value);base.pop('decision_source_sha256');base['version']=VERSION_V2
        decode_result(encode(base),row[0],output)
        model,texts,trip_entries=_translated(output,messages,decision,tx.scope)
        entries=_decode_value(model,messages,quote_texts=texts)
    except (MemoryInvalid,InvalidExtraction,ValueError,TypeError,KeyError,RecursionError) as error:
        raise Unavailable('original decision publication unavailable') from error
    if len(entries)!=len(value['receipts']):raise Unavailable('original decision entry count differs')
    for entry,receipt in zip(entries,value['receipts']):
        operation=tx.memory.operation(receipt['operation_id'])
        if operation is None:raise Unavailable('original decision canonical operation unavailable')
        try:command=parse_stored(operation[0])
        except MemoryInvalid as error:raise Unavailable('original decision command unavailable') from error
        stored=operation[1]
        trip=encode([entry.subject,entry.slot,entry.extent]) in trip_entries
        if (trip or entry.kind=='inference') and stored.status!='candidate':
            raise Unavailable('original decision conclusion is not a candidate')
        if command.extent=='long_term':context=None
        elif command.context_kind=='travel':context=Selection(command.context_id,command.context_version)
        else:raise Unavailable('original decision context unsupported')
        if command_for(tx.scope,entry,messages,context,digest,trip).raw!=operation[0]:
            raise Unavailable('original decision command differs')
        if receipt!=dict(operation_id=stored.operation_id,item_id=stored.item_id,version=stored.version,
                status=stored.status,input_sha256=stored.input_sha256):raise Unavailable('original decision receipt differs')
        tx.cur.execute('SELECT decision_source_sha256,origin_refs FROM cj_memory_history_origin WHERE scope=%s AND source_id=%s',
                       (tx.scope,command.source_id))
        origin=tx.cur.fetchone()
        if origin is None or origin[0]!=digest or type(origin[1]) is not list:
            raise Unavailable('original decision association unavailable')
        by_id={m.receipt.message_id:m for m in messages}
        if any(origin_reference(by_id[e.message_id]) not in origin[1] for e in entry.evidence):
            raise Unavailable('original decision message association missing')
    return row[6]
