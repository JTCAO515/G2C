"""Complete B-owned comparison inventory under the held physical barrier."""
from dataclasses import dataclass
from contextlib import closing
import json
from .core import Denied,digest
from .memory_inputs import consumes_sources
from cj_message.domain import Command
from cj_run.usage_binding import UsageBinding
from cj_run.payload_evidence import erased_original
from cj_run.background_store import _load as load_background

MAX_ROWS=20000
MAX_PAYLOAD=8_388_608


@dataclass(frozen=True)
class Message:
    message_id:str
    conversation_id:str
    generation:str
    sequence:int
    run_id:str
    input_sha256:str
    raw:bytes
    command:Command
    document:dict

    @property
    def trip_derived(self):return self.command.trip_context is not None or self.document['creation_intent']=='consider_trip'


@dataclass(frozen=True)
class Input:
    table:str
    run_id:str
    key:str
    command_bytes:bytes
    input_sha256:str
    erased:bool


@dataclass(frozen=True)
class Reference:
    table:str
    message:Message
    payload:bytes|None
    payload_sha256:str|None


@dataclass(frozen=True)
class Plan:
    messages:dict
    related:frozenset
    inputs:tuple
    references:tuple
    background:dict


def _rows(cursor,sql,scope):
    count=0
    with closing(cursor.stream(sql,(scope,))) as rows:
        for row in rows:
            count+=1
            if count>MAX_ROWS:raise Denied('complete payload inventory exceeds supported bound')
            yield row


def read_plan(cursor,scope,association):
    messages={};by_run={};related=set()
    sql='SELECT message_id,conversation_id,generation,sequence,run_id,input_sha256,raw_input FROM cj_message_receipt WHERE scope=%s'
    for mid,cid,generation,sequence,run_id,input_sha,raw in _rows(cursor,sql,scope):
        raw=bytes(raw)
        if digest(raw)!=input_sha:raise Denied('original MESSAGE bytes differ')
        command=Command.parse_original(raw)
        if (command.message_id,command.conversation_id)!=(mid,cid):raise Denied('original MESSAGE coordinates differ')
        message=Message(mid,cid,generation,sequence,run_id,input_sha,raw,command,json.loads(raw))
        messages[mid]=message;by_run[run_id]=message
        if message.trip_derived:related.add(run_id)
    for ref in association['message_refs']:
        message=messages.get(ref['message_id'])
        if (message is None or (message.conversation_id,message.generation,message.sequence,message.input_sha256)!=
           (ref['conversation_id'],ref['generation'],ref['sequence'],ref['input_sha256'])):
            raise Denied('approved original MESSAGE hash/coordinates unavailable')
        related.add(message.run_id)
    # A RUN may exist before its first metered operation. Validate all its
    # original MESSAGE associations; no orphan/alternate principal is inferred.
    for rid,mid,cid,generation,sequence in _rows(cursor,
        'SELECT run_id,message_id,conversation_id,generation,message_sequence FROM cj_run_record WHERE scope=%s',scope):
        message=by_run.get(rid)
        if message is None or (message.message_id,message.conversation_id,message.generation,message.sequence)!=(mid,cid,generation,sequence):
            raise Denied('original RUN/MESSAGE association unavailable')
    inputs=[];erased=[]
    for table,key_col,command_col,payload_col in (
        ('cj_run_record',"'original'",'usage_command_bytes','usage_input_bytes'),
        ('cj_run_step_usage','step_key','command_bytes','input_bytes'),
        ('cj_run_metered_operation','operation_key','command_bytes','input_bytes')):
        sql=f'SELECT run_id,{key_col},{command_col},CASE WHEN octet_length({payload_col})<={MAX_PAYLOAD} THEN {payload_col} END,octet_length({payload_col}) FROM {table} WHERE scope=%s AND {command_col} IS NOT NULL'
        for rid,key,command_raw,payload,size in _rows(cursor,sql,scope):
            if size is not None and size>MAX_PAYLOAD:raise Denied('original payload exceeds supported bound')
            message=by_run.get(rid)
            if message is None:raise Denied('original payload MESSAGE unavailable')
            command_raw=bytes(command_raw)
            if payload is None:
                erased.append((table,rid,key,command_raw));continue
            payload=bytes(payload);original=UsageBinding(command_raw,payload);original.check_run(rid)
            if rid not in related and original.command.kind=='model' and payload!=message.raw:
                if consumes_sources(payload,message.document['text'],association['source_refs']):related.add(rid)
            inputs.append(Input(table,rid,key,command_raw,original.command.input_digest,False))
    for table,rid,key,raw in erased:
        original=erased_original(cursor,scope,table,rid,key,raw)
        inputs.append(Input(table,rid,key,raw,original.command.input_digest,True))
    references=[]
    for table,version in (('cj_message_trip_reference','MESSAGE-send.3'),('cj_message_edit_reference','MESSAGE-send.4')):
        sql=f'SELECT message_id,run_id,input_sha256,CASE WHEN octet_length(source_content)<={MAX_PAYLOAD} THEN source_content END,content_sha256,octet_length(source_content) FROM {table} WHERE scope=%s'
        for mid,rid,input_sha,payload,payload_sha,size in _rows(cursor,sql,scope):
            message=messages.get(mid)
            if message is None or (message.run_id,message.input_sha256)!=(rid,input_sha) or message.document.get('version')!=version:
                raise Denied('original copied source association differs')
            if rid not in related:continue
            if size is not None and size>MAX_PAYLOAD:raise Denied('copied source exceeds supported bound')
            raw=None if payload is None else bytes(payload)
            if raw is not None and digest(raw)!=payload_sha:raise Denied('copied source bytes differ')
            references.append(Reference(table,message,raw,payload_sha))
    background={}
    wanted={(ref['job_id'],ref['attempt_id']) for ref in association['job_refs']}
    for jid,attempt in sorted(wanted):
        cursor.execute('SELECT job_id,attempt_id,run_id,ledger_scope,prepared_input_sha256,config_bytes,command_bytes,'
            f'CASE WHEN octet_length(input_bytes)<={MAX_PAYLOAD} THEN input_bytes END,'
            'state,output_sha256,receipt_sha256,protocol,decision_source_sha256,octet_length(input_bytes) '
            'FROM cj_run_background_job WHERE scope=%s AND job_id=%s AND attempt_id=%s',(scope,jid,attempt))
        row=cursor.fetchone()
        if row is not None:
            if row[-1] is not None and row[-1]>MAX_PAYLOAD:raise Denied('original background payload exceeds supported bound')
            background[(jid,attempt)]=load_background(row[:-1],scope)
    return Plan(messages,frozenset(related),tuple(i for i in inputs if i.run_id in related),tuple(references),background)
