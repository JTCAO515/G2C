"""Read the exact new outer wire beside its original canonical MESSAGE receipt.

This is source data, never a replacement for an active MESSAGE lease.
"""
from hashlib import sha256
import json

from .demo_dialogue import DialogueMessage, LIO_VERSION, LIO_VERSION_V3
from .domain import Unavailable


def original_protocol(cursor, binding, stored):
    row = cursor.execute(
        'SELECT demo_dialogue_protocol,demo_dialogue_input_sha256,lio_wire_protocol,lio_wire_input '
        'FROM cj_message_receipt WHERE scope=%s AND conversation_id=%s AND generation=%s '
        'AND message_id=%s AND run_id=%s AND sequence=%s AND input_sha256=%s AND raw_input=%s',
        (binding.scope, binding.conversation_id, binding.generation, binding.message_id,
         binding.run_id, binding.message_sequence, stored.receipt.input_sha256, stored.raw)).fetchone()
    if row is None or row[0] != LIO_VERSION:
        raise Unavailable('original Lio wire unavailable')
    if row[2:] == (None, None):
        return LIO_VERSION
    if row[2] != LIO_VERSION_V3 or row[3] is None:
        raise Unavailable('original Lio wire version differs')
    wire = bytes(row[3])
    outer = DialogueMessage.parse(wire, version=LIO_VERSION_V3)
    canonical = json.loads(stored.raw)
    receipt = stored.receipt
    if (sha256(wire).hexdigest() != row[1]
            or (outer.id, outer.text) != (receipt.message_id, canonical['text'])
            or outer.conversation_id is not None and outer.conversation_id != receipt.conversation_id):
        raise Unavailable('original Lio wire does not match canonical MESSAGE')
    return row[2]
