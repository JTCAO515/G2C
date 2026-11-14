"""Read the exact new outer wire beside its original canonical MESSAGE receipt.

This is source data, never a replacement for an active MESSAGE lease.
"""
from hashlib import sha256
from dataclasses import dataclass
import json

from .demo_dialogue import DialogueMessage, LIO_VERSION, LIO_VERSION_V3, LIO_VERSION_V4
from .domain import Unavailable


def original_protocol(cursor, binding, stored):
    return _original_protocol(cursor,binding,stored,LIO_VERSION_V3)


def exploration_original_protocol(cursor,binding,stored):
    return _original_protocol(cursor,binding,stored,LIO_VERSION_V4)


@dataclass(frozen=True)
class ExplorationOrigin:
    """Actual immutable origin witness, not AUTH, a client flag or a write grant."""
    database:object
    binding:object
    stored:object

    def check(self,binding):
        if binding!=self.binding:
            raise Unavailable('exploration input belongs to a different original RUN')
        with self.database.connect(binding.scope) as connection:
            exploration_original_protocol(connection.cursor(),binding,self.stored)

    def descriptor(self):
        receipt=self.stored.receipt
        return dict(protocol=LIO_VERSION_V4,message_id=receipt.message_id,run_id=receipt.run_id,
                    conversation_id=receipt.conversation_id,generation=receipt.generation,
                    sequence=receipt.sequence,input_sha256=receipt.input_sha256)


def _original_protocol(cursor,binding,stored,selected):
    row = cursor.execute(
        'SELECT demo_dialogue_protocol,demo_dialogue_input_sha256,lio_wire_protocol,lio_wire_input '
        'FROM cj_message_receipt WHERE scope=%s AND conversation_id=%s AND generation=%s '
        'AND message_id=%s AND run_id=%s AND sequence=%s AND input_sha256=%s AND raw_input=%s',
        (binding.scope, binding.conversation_id, binding.generation, binding.message_id,
         binding.run_id, binding.message_sequence, stored.receipt.input_sha256, stored.raw)).fetchone()
    if row is None or row[0] != LIO_VERSION:
        raise Unavailable('original Lio wire unavailable')
    if row[2:] == (None, None) and selected==LIO_VERSION_V3:
        return LIO_VERSION
    if row[2] != selected or row[3] is None:
        raise Unavailable('original Lio wire version differs')
    wire = bytes(row[3])
    outer = DialogueMessage.parse(wire, version=selected)
    canonical = json.loads(stored.raw)
    receipt = stored.receipt
    if (sha256(wire).hexdigest() != row[1]
            or (outer.id, outer.text) != (receipt.message_id, canonical['text'])
            or outer.conversation_id is not None and outer.conversation_id != receipt.conversation_id):
        raise Unavailable('original Lio wire does not match canonical MESSAGE')
    return row[2]
