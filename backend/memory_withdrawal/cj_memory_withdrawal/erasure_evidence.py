"""Freeze original enqueue/source comparison, never infer a B envelope hash."""
from hashlib import sha256
import json

from cj_cleanup.core import Denied
from cj_memory.domain import strict_object,Unavailable,unique_fields
from cj_memory_jobs.postgres import encode
from cj_memory_jobs.codec import encode_v2
from cj_memory_jobs.publication_store import PublicationTransaction
from cj_memory_jobs.publication_result import decode_result,VERSION_V2
from cj_memory_jobs.model_v2 import origin_reference,reference as message_reference
from cj_memory_jobs import decision_input
from cj_message.domain import Command
from cj_message.source import EndQuery,end_id
from .association_codec import _identity,_digest

VERSION='MEMORY-ERASURE-EVIDENCE@1'
MAX_BYTES=8_000_000


def _object(raw,limit):
    if type(raw) is not bytes or not 0<len(raw)<=limit:raise Denied('bounded original proof JSON required')
    return json.loads(raw.decode('utf-8'),object_pairs_hook=unique_fields)


def freeze_jobs(memory,association):
    tx=PublicationTransaction(memory);result=[]
    for ref in association['job_refs']:
        value=dict(ref,original_utf8=None,source_comparison=None,publication_utf8=None,publication_sha256=None,
                   model_output_sha256=None)
        if ref['state']=='erased':result.append(value);continue
        row,output=tx.output(ref['job_id'],ref['attempt_id'])
        if row[0].input_sha256!=ref['original_input_sha256']:raise Unavailable('original proof job changed')
        source,messages,mode=row[3],row[4],row[5]
        command=json.loads(row[1]);original_end=command.get('end')
        if mode=='conversation_end':
            query=EndQuery(**original_end) if original_end is not None else EndQuery(
                source.cursor.conversation_id,source.cursor.generation,source.cursor.epoch,source.cursor.through)
            ending=end_id(memory.scope,query)
        else:ending=None
        comparison=dict(version='MEMORY-SOURCE-COMPARISON@1',purpose=mode,end_ref=ending,
            source_fingerprint=sha256(encode_v2(source,messages,mode)).hexdigest(),
            messages=[dict(ref=message_reference(memory.scope,m),text_sha256=sha256(m.text.encode()).hexdigest(),
                           original=origin_reference(m)) for m in messages],decision=None)
        if command['version']=='MEMORY-DECISION-JOBS@1':
            from cj_memory_jobs.decision_batch import decoded
            _,_,_,decision=decoded(row[2]);refs=[]
            for message in messages:
                if Command.parse_original(message.original_utf8).trip_context is not None:
                    refs.append(dict(ref=decision_input.reference(memory.scope,message,decision),
                                     anchor_ref=message_reference(memory.scope,message)))
            comparison['decision']=dict(source_sha256=decision_input.source_digest(memory.scope,decision),
                document_sha256=decision.content_sha256,refs=refs)
        if row[6] is not None:
            publication=strict_object(row[6]);base=dict(publication)
            if publication.get('version')=='MEMORY-EXTRACT@1' and row[6]==output:
                pass  # Explicit legacy CollectionService completion, no Pub receipt.
            else:
                if publication['version']=='MEMORY-PUBLICATION-result@3':
                    if comparison['decision'] is None or base.pop('decision_source_sha256')!=comparison['decision']['source_sha256']:
                        raise Unavailable('original decision publication proof differs')
                    base['version']=VERSION_V2
                decode_result(encode(base),row[0],output)
                value.update(publication_utf8=row[6].decode(),publication_sha256=sha256(row[6]).hexdigest())
        value.update(original_utf8=row[1].decode(),source_comparison=comparison,
                     model_output_sha256=None if output is None else sha256(output).hexdigest())
        result.append(value)
    return result


def _parse_original(raw,association,association_sha256):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_BYTES:raise Denied('bounded original erasure evidence required')
    try:value=_object(raw,MAX_BYTES)
    except (ValueError,RecursionError) as error:raise Denied('invalid original erasure evidence') from error
    fields={'version','operation_id','subject_digest','memory_scope_digest','selection','association_sha256','jobs'}
    if (type(value) is not dict or set(value)!=fields or value['version']!=VERSION
            or value['association_sha256']!=association_sha256
            or any(value[k]!=association[k] for k in ('operation_id','subject_digest','memory_scope_digest','selection'))
            or type(value['jobs']) is not list or len(value['jobs'])!=len(association['job_refs'])):
        raise Denied('original erasure evidence binding differs')
    fields={'job_id','attempt_id','original_input_sha256','state','original_utf8','source_comparison',
            'publication_utf8','publication_sha256','model_output_sha256'}
    for job,original in zip(value['jobs'],association['job_refs']):
        if type(job) is not dict or set(job)!=fields or any(job[k]!=v for k,v in original.items()):
            raise Denied('original erasure job proof differs')
        if job['state']=='erased':
            if any(job[k] is not None for k in fields-set(original)):raise Denied('erased payload cannot be reconstructed')
            continue
        raw_input=job['original_utf8']
        if type(raw_input) is not str or not 0<len(raw_input.encode())<=32768 or sha256(raw_input.encode()).hexdigest()!=job['original_input_sha256']:
            raise Denied('original enqueue proof differs')
        command=strict_object(raw_input.encode())
        if (command.get('job_id'),command.get('attempt_id'))!=(job['job_id'],job['attempt_id']):raise Denied('original enqueue identity differs')
        comparison=job['source_comparison']
        if (type(comparison) is not dict or set(comparison)!={'version','purpose','end_ref','source_fingerprint','messages','decision'}
                or comparison['version']!='MEMORY-SOURCE-COMPARISON@1' or comparison['purpose'] not in ('incremental','conversation_end')
                or type(comparison['messages']) is not list or len(comparison['messages'])>100):
            raise Denied('original source comparison unavailable')
        _digest(comparison['source_fingerprint'])
        if comparison['purpose']=='incremental':
            if comparison['end_ref'] is not None:raise Denied('unexpected original end')
        else:_digest(comparison['end_ref'])
        seen=set()
        for message in comparison['messages']:
            if type(message) is not dict or set(message)!={'ref','text_sha256','original'}:raise Denied('invalid source message proof')
            _identity(message['ref']);_digest(message['text_sha256'])
            if message['ref'] in seen:raise Denied('duplicate source message proof')
            seen.add(message['ref'])
            # Reuse the same public reference boundary as Association@1.
            from .association_codec import _rows
            _rows([message['original']],('conversation_id','generation','sequence','message_id','input_sha256'),
                  ('conversation_id','generation','message_id'),('input_sha256',),('sequence',))
        decision=comparison['decision']
        if decision is not None:
            if type(decision) is not dict or set(decision)!={'source_sha256','document_sha256','refs'}:raise Denied('invalid accepted source proof')
            _digest(decision['source_sha256']);_digest(decision['document_sha256'])
            if type(decision['refs']) is not list or len(decision['refs'])>100:raise Denied('accepted source reference bound')
            for ref in decision['refs']:
                if type(ref) is not dict or set(ref)!={'ref','anchor_ref'} or ref['anchor_ref'] not in seen:raise Denied('accepted anchor differs')
                _identity(ref['ref'])
        publication=job['publication_utf8']
        if publication is None:
            if job['publication_sha256'] is not None:raise Denied('publication proof missing')
        elif (type(publication) is not str or not 0<len(publication.encode())<=16384
                or sha256(publication.encode()).hexdigest()!=job['publication_sha256']):raise Denied('publication proof digest differs')
        if job['model_output_sha256'] is not None:_digest(job['model_output_sha256'])
    return value


def parse_original(raw,association,association_sha256):
    try:return _parse_original(raw,association,association_sha256)
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError) as error:
        raise Denied('original erasure evidence unavailable') from error


def compare_prepared(job,raw):
    """Return computed B prepared SHA after exact frozen source comparison.

    Not an attestation that C ever stored that prepared SHA. B must validate
    its own original envelope/IDs/query/bytes before using this comparison.
    """
    if job['state']=='erased':raise Denied('no original payload proof; require prior B redaction evidence')
    if type(raw) is not bytes or not 0<len(raw)<=1_000_000:raise Denied('bounded original prepared input required')
    try:
        envelope=_object(raw,1_000_000)
        if (set(envelope)!={'system','messages'} or type(envelope['system']) is not str
                or type(envelope['messages']) is not list or len(envelope['messages'])!=1
                or set(envelope['messages'][0])!={'role','content'} or envelope['messages'][0]['role']!='user'):
            raise Denied('original prepared input envelope differs')
        data=_object(envelope['messages'][0]['content'].encode(),1_000_000)
        source=job['source_comparison'];decision=source['decision']
        fields={'version','purpose','subjects','slots','max_entries','max_text_bytes','source_fingerprint','end_ref','omitted_count','messages'}
        if decision is not None:fields|={'trip_decisions','decision_source_sha256'}
        if (set(data)!=fields or data['version']!=('MEMORY-EXTRACT-DATA@3' if decision is not None else 'MEMORY-EXTRACT-DATA@2')
                or data['purpose']!=source['purpose'] or data['end_ref']!=source['end_ref'] or type(data['messages']) is not list):
            raise Denied('original prepared source format differs')
        wanted={m['ref']:m for m in source['messages']};order=[]
        for message in data['messages']:
            if (type(message) is not dict or set(message)!={'ref','text'} or message['ref'] not in wanted
                    or type(message['text']) is not str or sha256(message['text'].encode()).hexdigest()!=wanted[message['ref']]['text_sha256']):
                raise Denied('original prepared message differs')
            order.append(next(i for i,m in enumerate(source['messages']) if m['ref']==message['ref']))
        if order!=sorted(set(order)) or type(data['omitted_count']) is not int or data['omitted_count']!=len(wanted)-len(order):
            raise Denied('original prepared message subset differs')
        fingerprint=source['source_fingerprint']
        if decision is not None:
            refs=data['trip_decisions'];expected=[r for r in decision['refs'] if r['anchor_ref'] in {m['ref'] for m in data['messages']}]
            if type(refs) is not list or len(refs)!=len(expected) or not refs or data['decision_source_sha256']!=decision['source_sha256']:
                raise Denied('original accepted source subset differs')
            for ref,original in zip(refs,expected):
                if (type(ref) is not dict or set(ref)!={'ref','anchor_ref','document'}
                        or any(ref[k]!=v for k,v in original.items()) or type(ref['document']) is not str
                        or sha256(ref['document'].encode()).hexdigest()!=decision['document_sha256']):
                    raise Denied('original accepted document differs')
            fingerprint=sha256(encode([fingerprint,[r['ref'] for r in refs]])).hexdigest()
        if data['source_fingerprint']!=fingerprint:raise Denied('original prepared source fingerprint differs')
        return sha256(raw).hexdigest()
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError) as error:
        raise Denied('original prepared source unavailable') from error
