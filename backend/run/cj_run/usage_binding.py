"""Immutable RUN-owned association, not a quota ledger or public authority.

The internal byte codec stores the seven canonical CJ008 Command fields. Original
outbound input bytes are private; no normalization, reconstruction or logging.
"""
from dataclasses import dataclass
import hashlib
import json


FIELDS = frozenset({'attempt_id', 'operation_id', 'run_id', 'kind', 'input_digest', 'reserve', 'output_limit'})


@dataclass(frozen=True)
class UsageBinding:
    command_bytes: bytes
    input_bytes: bytes

    def __post_init__(self):
        if type(self.command_bytes) is not bytes or type(self.input_bytes) is not bytes:
            raise ValueError('original immutable bytes required')
        values = self.values()
        if values['input_digest'] != hashlib.sha256(self.input_bytes).hexdigest():
            raise ValueError('input bytes do not match original digest')

    def values(self):
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError('duplicate command field')
                result[key] = value
            return result
        try:
            values = json.loads(self.command_bytes.decode('utf-8'), object_pairs_hook=pairs)
        except (UnicodeError, ValueError) as exc:
            raise ValueError('invalid command encoding') from exc
        if type(values) is not dict or set(values) != FIELDS:
            raise ValueError('unsupported command fields')
        for key in ('attempt_id', 'operation_id', 'run_id'):
            if type(values[key]) is not str or not values[key] or len(values[key]) > 200:
                raise ValueError('invalid command identity')
        if values['kind'] not in ('model', 'tool', 'memory'):
            raise ValueError('unsupported command kind')
        digest = values['input_digest']
        if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('invalid input digest')
        for key in ('reserve', 'output_limit'):
            if type(values[key]) is not int or values[key] < 1:
                raise ValueError('invalid command limit')
        return values

    def check_run(self, run_id):
        if self.values()['run_id'] != run_id:
            raise ValueError('command run differs from original run')
