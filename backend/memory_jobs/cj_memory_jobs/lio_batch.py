"""Single-message Lio batch; old history batches keep their own stream."""
from dataclasses import asdict
from hashlib import sha256
import json

from cj_strict_json import reject_duplicates
from .codec import InvalidInput, decode_v2, encode_v2


VERSION = 'CJ020-lio.1'


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')


def encode_batch(source, rows, mode):
    if mode != 'incremental' or len(rows) != 1:
        raise InvalidInput('one committed Lio message required')
    value = json.loads(encode_v2(source, rows, mode))
    value['version'] = VERSION
    return _canonical(value)


def decode_batch(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 262144:
        raise InvalidInput('bounded Lio batch required')
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates(InvalidInput, 'duplicate field'))
        if value['version'] != VERSION:
            raise InvalidInput('explicit Lio batch required')
        value['version'] = 'CJ020-internal.2'
        source, rows, mode = decode_v2(_canonical(value))
        if encode_batch(source, rows, mode) != raw:
            raise InvalidInput('canonical Lio batch required')
        return source, rows, mode
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        raise InvalidInput('invalid Lio batch') from error


def stream_key(source):
    return sha256(_canonical(dict(version=VERSION, source=asdict(source)))).hexdigest()


def job_ids(source, message):
    receipt = message.receipt
    # Versions and timeouts never mint a replacement of the same original.
    identity = sha256(_canonical([source.cursor.scope, receipt.conversation_id, receipt.generation,
                                   receipt.message_id, receipt.run_id])).hexdigest()
    return 'lio-message-v1:' + identity, 'lio-message-attempt-v1:' + identity


def original_input(source, message):
    job_id, attempt_id = job_ids(source, message)
    cursor = source.cursor
    # The original enqueue proof keeps the existing cleanup reader's grammar.
    # Lio isolation lives in the batch version, stream, and original job IDs.
    query = dict(conversation_id=cursor.conversation_id, generation=cursor.generation,
                 epoch=cursor.epoch, after=cursor.after, through=cursor.through,
                 source_version=source.source_version, withdrawal_epoch=source.withdrawal_epoch,
                 mode='incremental')
    return _canonical(dict(version='MEMORY-JOBS@1', job_id=job_id, attempt_id=attempt_id, source=query))
