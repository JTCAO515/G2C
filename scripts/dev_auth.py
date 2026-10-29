"""Local development identity for CJ_ENV=local only (P2a). Not a real login.

  dev_auth.py init  DIR [--invite SUBJECT ...]   create RSA keys, invite list, Trip confirmation and history cursor keys
  dev_auth.py confirmation-key DIR               add the Trip confirmation key to an existing DIR
  dev_auth.py history-key DIR                    add the history cursor key to an existing DIR
  dev_auth.py token DIR --subject SUBJECT [--minutes N]   print a short-lived local token

The private key stays in DIR (mode 0600, git-ignored under .local/). Tokens are only
accepted by backend/cj_api/local_app.py, whose issuer is https://local.g2c.invalid.
"""
import argparse
import json
import os
from pathlib import Path
import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from cj_api.local_app import AUDIENCE, ISSUER, KEY_ID


def init(directory, invited):
    if os.environ.get('CJ_ENV') != 'local':
        raise SystemExit('CJ_ENV=local is required')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    private = directory / 'private.pem'
    if private.exists():
        raise SystemExit(f'{private} exists; refusing to overwrite')
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private.touch(mode=0o600)
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    (directory / 'public.pem').write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    (directory / 'invited.json').write_text(json.dumps(sorted(set(invited))) + '\n')
    confirmation_key(directory)
    history_key(directory)
    print(f'initialized {directory} (invited: {", ".join(sorted(set(invited))) or "none"})')


def confirmation_key(directory):
    """Dedicated local Trip confirmation signing key (32 random bytes, 0600); never overwritten."""
    path = directory / 'trip-confirmation.key'
    if path.exists():
        raise SystemExit(f'{path} exists; refusing to overwrite')
    path.touch(mode=0o600)
    path.write_bytes(os.urandom(32))
    print(f'created {path}')


def history_key(directory):
    """Create a dedicated local history key exclusively; preserve any existing entry."""
    if os.environ.get('CJ_ENV') != 'local':
        raise SystemExit('CJ_ENV=local is required')
    path = directory / 'history-cursor.key'
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit(f'{path} exists; refusing to overwrite') from None
    with os.fdopen(fd, 'wb') as destination:
        os.fchmod(destination.fileno(), 0o600)
        destination.write(os.urandom(32))
    print(f'created {path}')


def token(directory, subject, minutes):
    if os.environ.get('CJ_ENV') != 'local':
        raise SystemExit('CJ_ENV=local is required')
    key = serialization.load_pem_private_key((directory / 'private.pem').read_bytes(), password=None)
    now = int(time.time())
    claims = dict(iss=ISSUER, aud=AUDIENCE, sub=subject, iat=now, nbf=now, exp=now + 60 * minutes)
    return jwt.encode(claims, key, algorithm='RS256', headers={'kid': KEY_ID})


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init'); p.add_argument('dir', type=Path); p.add_argument('--invite', action='append', default=[])
    p = sub.add_parser('confirmation-key'); p.add_argument('dir', type=Path)
    p = sub.add_parser('history-key'); p.add_argument('dir', type=Path)
    p = sub.add_parser('token'); p.add_argument('dir', type=Path); p.add_argument('--subject', required=True)
    p.add_argument('--minutes', type=int, default=30, choices=range(1, 121), metavar='1-120')
    args = parser.parse_args()
    if args.command == 'init':
        init(args.dir, args.invite)
    elif args.command == 'confirmation-key':
        confirmation_key(args.dir)
    elif args.command == 'history-key':
        history_key(args.dir)
    else:
        print(token(args.dir, args.subject, args.minutes))


if __name__ == '__main__':
    main()
