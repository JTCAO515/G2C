"""Immutable original bytes; validate raw input once, trust the internal value."""
from dataclasses import dataclass, asdict
import hashlib
import json
from cj_usage.core import Command, Blocked

FIELDS = frozenset({'attempt_id', 'operation_id', 'run_id', 'kind', 'input_digest', 'reserve', 'output_limit'})


def _decode_command(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate command field')
            result[key] = value
        return result
    try:
        values = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
    except (UnicodeError, ValueError) as exc:
        raise ValueError('invalid command encoding') from exc
    if type(values) is not dict or set(values) != FIELDS:
        raise ValueError('unsupported command fields')
    try:
        return Command(**values)
    except Blocked as exc:
        raise ValueError('invalid command fields') from exc


@dataclass(frozen=True)
class UsageBinding:
    command_bytes: bytes
    input_bytes: bytes

    def __post_init__(self):
        # Raw persisted/caller bytes are the boundary; consumers do not decode again.
        if type(self.command_bytes) is not bytes or type(self.input_bytes) is not bytes:
            raise ValueError('original immutable bytes required')
        command = _decode_command(self.command_bytes)
        if command.input_digest != hashlib.sha256(self.input_bytes).hexdigest():
            raise ValueError('input bytes do not match original digest')
        object.__setattr__(self, '_command', command)

    @classmethod
    def from_command(cls, command: Command, input_bytes: bytes):
        """Internal factory: command was just constructed from these input bytes.

        Keep the two public dataclass fields/byte equality unchanged. This avoids
        serializing and re-validating our own already validated Command.
        """
        value = object.__new__(cls)
        object.__setattr__(value, 'command_bytes', json.dumps(asdict(command), sort_keys=True, separators=(',', ':')).encode('utf-8'))
        object.__setattr__(value, 'input_bytes', input_bytes)
        object.__setattr__(value, '_command', command)
        return value

    @property
    def command(self):
        return self._command

    def values(self):
        return asdict(self._command)

    def check_run(self, run_id):
        if self._command.run_id != run_id:
            raise ValueError('command run differs from original run')
