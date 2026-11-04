"""Network-free Linux image check of the env → memfd signing-key handoff."""
import base64
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import dev_auth
from cj_api.local_app import ISSUER,AUDIENCE
from . import configuration


class Clock(datetime):
    @classmethod
    def now(cls,tz=None):return datetime(2026,11,4,tzinfo=timezone.utc)


def main():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    private=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    now=int(time.time())
    context=dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(meter=dict(unit='provider_call',budget=20,
        period_start=now-60,period_end=now+3600,max_steps=8,max_tools=1,max_output=5000,max_seconds=120),output_limits=dict(model=2000,tool=2000,memory=2000)))
    values=dict(CJ_ENV='local',CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_TRIAL_VALID_UNTIL='2026-11-30T16:00:00+00:00',
        CJ_BETA_SUBJECTS_JSON='["m4-synthetic-linux-check"]',CJ_BETA_RUN_CONTEXT_JSON=json.dumps(context),
        CJ_BETA_SIGNING_PRIVATE_B64=base64.b64encode(private).decode(),CJ_BETA_SIGNING_PUBLIC_B64=base64.b64encode(public).decode())
    with patch.dict(os.environ,values),patch.object(configuration,'datetime',Clock),tempfile.TemporaryDirectory(prefix='g2c-beta-memory-') as directory:
        runtime=configuration.Runtime.load(directory,worker=True)
        try:
            path=runtime.auth/'private.pem'
            assert path.is_symlink() and str(path.readlink()).startswith('/proc/self/fd/') and path.read_bytes()==private
            token=dev_auth.token(runtime.auth,'m4-synthetic-linux-check',60)
            assert jwt.decode(token,public,algorithms=['RS256'],issuer=ISSUER,audience=AUDIENCE)['sub']=='m4-synthetic-linux-check'
            assert not any(p.is_file() and not p.is_symlink() and p.read_bytes()==private for p in Path(directory).rglob('*'))
        finally:runtime.close()
        try:path.read_bytes()
        except OSError:pass
        else:raise AssertionError('private signing bytes persisted after descriptor close')
    print('PASS Linux env-only private key → memfd → original signed token; no persisted PEM, no network/keychain/real-provider calls')


if __name__=='__main__':main()
