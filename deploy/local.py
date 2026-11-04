"""Create a NEW synthetic-only local configuration. Never overwrite secrets."""
import argparse
import json
import os
from pathlib import Path
import secrets
import time
import re
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

import dev_auth


def prepare(root, port, project):
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700)
    config, control, heartbeat = root / 'config', root / 'control',root/'heartbeat'
    config.mkdir(mode=0o700)
    control.mkdir(mode=0o755);heartbeat.mkdir(mode=0o700)
    runtime,operator=config/'runtime',config/'operator'
    runtime.mkdir(mode=0o700);operator.mkdir(mode=0o700)
    dev_auth.init(runtime / 'auth', ['synthetic-alice', 'synthetic-bob'])
    for name, value in (('database-password', secrets.token_urlsafe(32).encode()), ('recovery.key', secrets.token_bytes(32))):
        path = operator / name
        path.write_bytes(value)
        path.chmod(0o600)
    public=Ed25519PrivateKey.from_private_bytes((operator/'recovery.key').read_bytes()).public_key().public_bytes(
        serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    (runtime/'recovery.pub').write_bytes(public)
    for name, user in (('migration', 'cj_deploy_admin'), ('runtime', 'cj_m1_runtime')):
        path = (operator if name=='migration' else runtime) / (name + '.json')
        path.write_text(json.dumps(dict(host='/var/run/postgresql', user=user, dbname='postgres',
                                       connect_timeout=3, options='-c statement_timeout=10000 -c lock_timeout=5000')))
        path.chmod(0o600)
    now = int(time.time())
    (runtime / 'run.json').write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2', history=[], current=dict(
        meter=dict(unit='provider_call', budget=20, period_start=now-60, period_end=now+86400,
                   max_steps=20, max_tools=10, max_output=10000, max_seconds=600),
        output_limits=dict(model=2000, tool=2000, memory=2000)))))
    (root / 'compose.env').write_text('\n'.join((
        'COMPOSE_PROJECT_NAME='+project,
        'CJ_DEPLOY_CONFIG=' + str(config.resolve()), 'CJ_DEPLOY_CONTROL_DIR=' + str(control.resolve()),
        'CJ_DEPLOY_HEARTBEAT_DIR='+str(heartbeat.resolve()),
        'CJ_DEPLOY_PORT=' + str(port), 'CJ_DEPLOY_UID=' + str(os.getuid()), 'CJ_DEPLOY_GID=' + str(os.getgid()))) + '\n')
    (root / 'compose.env').chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--project', required=True)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('unprivileged port required')
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{0,48}',args.project):parser.error('explicit local Compose project name required')
    prepare(args.root, args.port,args.project)
    print('PASS created new synthetic local configuration; no real provider enabled')


if __name__ == '__main__':
    main()
