"""RUN-PAYLOAD-ERASURE@1 original hashed proof; no dispatch or fee mutation."""
from hashlib import sha256
from .core import Denied
from .usage_binding import ErasedUsageBinding,_decode_command


def owner_digest(scope):return sha256(scope.encode('utf-8')).hexdigest()


def key_digest(kind,*parts):
    raw=b'CJ-PAYLOAD-ERASURE@1\0'+kind.encode('utf-8')
    for part in parts:raw+=b'\0'+part.encode('utf-8')
    return sha256(raw).hexdigest()


def erased_original(cursor,scope,table,run_id,operation_key,command_bytes):
    command=_decode_command(command_bytes)
    if command.run_id!=run_id:raise Denied('erased original command run differs')
    key=key_digest('input',table,run_id,operation_key)
    cursor.execute("SELECT payload_sha256 FROM cj_run_payload_erasure WHERE owner_digest=%s AND kind='input' AND object_digest=%s AND outcome='erased'",
                   (owner_digest(scope),key))
    if cursor.fetchone()!=(command.input_digest,):raise Denied('original payload erasure proof unavailable')
    return ErasedUsageBinding(command_bytes,command)
