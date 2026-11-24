"""Install one approved API credential from stdin under the HK deployment lock."""

import os
from pathlib import Path
import re
import stat
import sys
from tempfile import mkstemp


ROOT = Path('/srv/g2c-beta')
NAMES = {'CJ_QWEATHER_KEY', 'CJ_VARIFLIGHT_MCP_KEY'}
REQUIRED = {b'CJ_SUPABASE_RUNTIME_URI', b'CJ_BETA_CONFIRMATION_B64', b'CJ_BETA_HISTORY_B64'}
NAME = re.compile(rb'[A-Z][A-Z0-9_]*')
PRINTABLE = re.compile(rb'[!-~]{8,512}')


def read_env(path, owner):
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or (info.st_uid, info.st_gid) != owner or info.st_nlink != 1):
            raise ValueError('api_env_identity_mismatch')
        raw = stream.read(65537)
    if len(raw) > 65536 or not raw.endswith(b'\n') or b'\r' in raw:
        raise ValueError('api_env_format_mismatch')
    if len(raw.decode('utf-8').splitlines()) != raw.count(b'\n'):
        raise ValueError('api_env_format_mismatch')
    names = set()
    for line in raw[:-1].split(b'\n'):
        name, sep, value = line.partition(b'=')
        if not sep or not NAME.fullmatch(name) or not value or b'\0' in value or name in names:
            raise ValueError('api_env_format_mismatch')
        names.add(name)
    if not REQUIRED <= names:
        raise ValueError('api_env_required_fields_missing')
    return info, raw


def write_file(directory, tag, raw, owner):
    fd, name = mkstemp(prefix=tag, dir=str(directory))
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchown(stream.fileno(), *owner)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        os.unlink(name)
        raise
    return name


def identity(info):
    return info.st_dev, info.st_ino, info.st_mtime_ns


def install(path, name, value, owner):
    if name not in NAMES:
        raise ValueError('unapproved_travel_variable')
    value = value[:-1] if value.endswith(b'\n') else value
    if not PRINTABLE.fullmatch(value):
        raise ValueError('invalid_credential_stdin')
    info, old = read_env(path, owner)
    prefix = name.encode() + b'='
    replacement = prefix + value
    lines = old[:-1].split(b'\n')
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            break
    else:
        lines.append(replacement)
    new = b'\n'.join(lines) + b'\n'
    if len(new) > 65536:
        raise ValueError('api_env_size_mismatch')
    write_file(path.parent, 'api.env.before-travel-', old, owner)
    staged = write_file(path.parent, 'api.env.travel-staged-', new, owner)
    try:
        actual, current = read_env(path, owner)
        if identity(actual) != identity(info) or current != old:
            raise ValueError('api_env_changed_under_lock')
        os.replace(staged, str(path))
        staged = None
        directory = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if staged is not None:
            os.unlink(staged)
    _, observed = read_env(path, owner)
    if observed != new or not any(line.startswith(prefix) and len(line) > len(prefix)
                                  for line in observed.split(b'\n')):
        raise ValueError('api_env_readback_mismatch')


if __name__ == '__main__':
    try:
        name, = sys.argv[1:]
        install(ROOT / 'api.env', name, sys.stdin.buffer.read(514), (10001, 10001))
        print(name, 'present_nonempty')
    except (OSError, UnicodeError, ValueError):
        print('TRAVEL_CREDENTIAL_INSTALL_STOP', file=sys.stderr)
        raise SystemExit(2) from None
