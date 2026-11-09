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


def token(directory, subject, minutes, *, jti=None):
    if os.environ.get('CJ_ENV') != 'local':
        raise SystemExit('CJ_ENV=local is required')
    key = serialization.load_pem_private_key((directory / 'private.pem').read_bytes(), password=None)
    now = int(time.time())
    claims = dict(iss=ISSUER, aud=AUDIENCE, sub=subject, iat=now, nbf=now, exp=now + 60 * minutes)
    if jti is not None:
        claims['jti'] = jti
    return jwt.encode(claims, key, algorithm='RS256', headers={'kid': KEY_ID})


def activate_travel(conninfo_path,subject,run_context,consumer_abi,*,typed_memory_configuration=None,auth_dir=None):
    """Local metadata operator only; creates no key, account or budget.

    Stop old workers before invoking. The DB activation trigger serializes all
    unacknowledged work and old readers remain blocked by the restrictive gate.
    """
    import psycopg
    from cj_api.local_app import LocalDatabase,local_conninfo,scope_for
    from cj_message.travel import ABI,PROFILE
    if consumer_abi!=ABI or run_context.version!='CJ-LOCAL-RUN@2':
        raise ValueError('explicit compatible registered consumer required')
    scope=scope_for(ISSUER,subject)
    database=LocalDatabase(conninfo_path,run_context=run_context,travel_context=True)
    database.require_budget_account(scope)
    validate=None
    if typed_memory_configuration is not None:
        from cj_memory.typed_runtime import TypedRuntimeConfiguration
        from cj_memory.runtime import RuntimeDenied,RuntimeUnknown
        from cj_api.local_account_admission_v2 import account_checker_for
        from cj_auth.interfaces import AdmissionStatus
        from cj_message.travel_reference import MessageContextAuthority
        if type(typed_memory_configuration) is not TypedRuntimeConfiguration or auth_dir is None:
            raise ValueError('canonical typed Memory configuration and original AUTH required')
        credential=token(Path(auth_dir),subject,5)
        checker=account_checker_for(Path(auth_dir),database)
        first=checker.check(credential)
        if first.status is AdmissionStatus.UNKNOWN:raise RuntimeUnknown('typed activation admission uncertain')
        if first.status is not AdmissionStatus.ALLOWED:raise RuntimeDenied('typed activation owner unavailable')
        def admit():
            current=checker.check(credential)
            if current.status is AdmissionStatus.UNKNOWN:raise RuntimeUnknown('typed activation admission uncertain')
            if (current.status is not AdmissionStatus.ALLOWED or current.principal!=first.principal
                    or scope_for(current.principal.issuer,current.principal.subject)!=scope):
                raise RuntimeDenied('typed activation owner unavailable')
            return current.principal
        memory=typed_memory_configuration.bind_readonly(database,scope,subject,admit,
            message_context=MessageContextAuthority(database.message_repository(scope),admit))
        validate=memory.guard
    with psycopg.connect(**local_conninfo(conninfo_path)) as conn:
        if conn.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(scope,)).fetchone() is None:
            raise ValueError('existing owned namespace required')
        if validate is not None:validate('typed_travel_activation')
        if conn.execute('SELECT 1 FROM cj_memory_scope WHERE scope=%s',(scope,)).fetchone() and validate is None:
            raise ValueError('typed memory consumer is not installed')
        old=conn.execute('SELECT version FROM cj_message_context_profile WHERE scope=%s',(scope,)).fetchone()
        if old is not None:
            if old!=(PROFILE,):raise ValueError('unknown travel profile')
            return 'existing'
        conn.execute('INSERT INTO cj_message_context_profile(scope,version) VALUES(%s,%s)',(scope,PROFILE))
    if validate is not None:validate('typed_travel_activation')
    return 'activated'


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init'); p.add_argument('dir', type=Path); p.add_argument('--invite', action='append', default=[])
    p = sub.add_parser('confirmation-key'); p.add_argument('dir', type=Path)
    p = sub.add_parser('history-key'); p.add_argument('dir', type=Path)
    p = sub.add_parser('token'); p.add_argument('dir', type=Path); p.add_argument('--subject', required=True)
    p.add_argument('--minutes', type=int, default=30, choices=range(1, 121), metavar='1-120')
    p = sub.add_parser('activate-travel')
    p.add_argument('--conninfo-json',type=Path,required=True)
    p.add_argument('--subject',required=True)
    p.add_argument('--run-context',type=Path,required=True)
    p.add_argument('--consumer-abi',choices=['MESSAGE-TRAVEL-CONSUMER@1'],required=True)
    p.add_argument('--typed-memory-run-policy',type=Path)
    p.add_argument('--auth-dir',type=Path)
    args = parser.parse_args()
    if args.command == 'init':
        init(args.dir, args.invite)
    elif args.command == 'confirmation-key':
        confirmation_key(args.dir)
    elif args.command == 'history-key':
        history_key(args.dir)
    elif args.command=='activate-travel':
        from cj_api.local_run_context import load_run_context
        config=None
        if args.typed_memory_run_policy is not None:
            from cj_memory.typed_runtime import load_typed_runtime_configuration
            config=load_typed_runtime_configuration(args.typed_memory_run_policy)
        print(json.dumps({'status':activate_travel(args.conninfo_json,args.subject,
            load_run_context(args.run_context),args.consumer_abi,typed_memory_configuration=config,auth_dir=args.auth_dir)}))
    else:
        print(token(args.dir, args.subject, args.minutes))


if __name__ == '__main__':
    main()
