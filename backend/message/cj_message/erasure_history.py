"""MESSAGE-history.5: retained human history, explicit erased source cache.

This read never reconstructs a source, dispatches a RUN or grants model use.
Old reference readers keep requiring their original complete source bytes.
"""
from hashlib import sha256
from dataclasses import dataclass
import json
from .domain import Command,Unavailable
from cj_run.payload_evidence import owner_digest,key_digest


@dataclass(frozen=True)
class HistoryMessage:
    stored:object
    reference:dict|None
    source_state:str


def read(service,message_id):
    with service.repository.transaction() as tx:
        tx.lock_scope()
        stored=tx.find(message_id)
        if stored is None:raise Unavailable('original history message unavailable')
        command=Command.parse_original(stored.raw);r=stored.receipt
        if (command.message_id,command.conversation_id)!=(r.message_id,r.conversation_id) or r.message_id!=message_id or sha256(stored.raw).hexdigest()!=r.input_sha256:
            raise Unavailable('original human history bytes differ')
        def result(reference,state):return HistoryMessage(stored,reference,state)
        version=json.loads(stored.raw)['version']
        if version not in ('MESSAGE-send.3','MESSAGE-send.4'):
            if version=='MESSAGE-send.2':
                from .travel_reference import read_reference
                return result(read_reference(tx,stored).public_value(),'retained')
            return result(None,'not_applicable')
        table='cj_message_trip_reference' if version=='MESSAGE-send.3' else 'cj_message_edit_reference'
        tx.cur.execute(f'SELECT run_id,conversation_id,generation,sequence,input_sha256,selection,selection_epoch,source_content,content_sha256 '
                       f'FROM {table} WHERE scope=%s AND message_id=%s',(tx.scope,message_id))
        row=tx.cur.fetchone()
        if (row is None or row[:5]!=(r.run_id,r.conversation_id,r.generation,r.sequence,r.input_sha256)
            or sha256(stored.raw).hexdigest()!=r.input_sha256 or type(row[6]) is not int or not 1<=row[6]<=r.sequence):
            raise Unavailable('original history reference differs')
        if row[7] is not None or command.trip_context is None:
            if version=='MESSAGE-send.3':
                from .trip_reference import read_reference
                return result(read_reference(tx,stored).public_value(),'retained')
            from .edit_reference import read
            return result(read(tx,stored).public_value(),'retained')
        raw=json.loads(stored.raw)
        keys=('travel_context','needs_reference','trip_context')
        if version=='MESSAGE-send.4':keys+=('modification_intent',)
        selection={key:raw[key] for key in keys}
        canonical=json.dumps(selection,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        if row[5]!=canonical or row[8] is not None:raise Unavailable('original erased reference differs')
        tx.cur.execute("SELECT payload_sha256 FROM cj_run_payload_erasure WHERE owner_digest=%s AND kind='reference' "
                       "AND object_digest=%s AND outcome='erased'",(owner_digest(tx.scope),
                       key_digest('reference',table,r.message_id,r.run_id,r.input_sha256)))
        proof=tx.cur.fetchone()
        if proof is None or proof[0] is None:raise Unavailable('original source erasure unproven')
        return result(None,'erased')
