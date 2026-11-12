"""Private durable operation mapping, not an accounting/authorization ledger."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat

from .contract import Invalid, decode, encode, raw_digest, require


class IntentStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and
                stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_INTENT_DIRECTORY')

    @contextmanager
    def locked(self):
        descriptor = os.open(self.directory / 'writer.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            raise Invalid('ADAPTER_BUSY') from None
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def path(self, attempt_id):
        return self.directory / (raw_digest(attempt_id.encode('utf-8')) + '.json')

    def read(self, attempt_id):
        path = self.path(attempt_id)
        return self._read(path, expected_attempt=attempt_id)

    def _read(self, path, *, expected_attempt=None):
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        with os.fdopen(descriptor, 'rb') as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                    stat.S_IMODE(info.st_mode) == 0o600, 'PRIVATE_INTENT_FILE')
            raw = source.read(2_097_153)
        require(len(raw) <= 2_097_152, 'INTENT_BOUND')
        value = decode(raw)
        require(type(value) is dict and set(value) == {'payload', 'sha256'} and
                type(value['payload']) is dict and
                value['sha256'] == raw_digest(encode(value['payload'])), 'DAMAGED_INTENT')
        p = value['payload']
        require(set(p) == {'attempt_id', 'purpose', 'request', 'request_sha256', 'plan', 'steps',
                'binding_sha256', 'pins_sha256'} and type(p['attempt_id']) is str and
                self.path(p['attempt_id']) == path and
                (expected_attempt is None or p['attempt_id'] == expected_attempt) and
                p['purpose'] in ('call', 'propose') and type(p['request']) is dict and
                p['request_sha256'] == raw_digest(encode(p['request'])) and
                type(p['plan']) is list and type(p['steps']) is list and
                0 <= len(p['steps']) <= len(p['plan']) <= 128, 'DAMAGED_INTENT')
        return p

    def all(self):
        # Only adapter-owned mappings; no model/provider/fee ledger is read here.
        for path in sorted(self.directory.glob('*.json')):
            yield self._read(path)

    def write(self, payload):
        raw = encode(dict(payload=payload, sha256=raw_digest(encode(payload))))
        require(len(raw) <= 2_097_152, 'INTENT_BOUND')
        path = self.path(payload['attempt_id'])
        temporary = path.with_suffix('.next')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
