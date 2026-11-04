"""Beta environment boundary. Persistent application secrets live only in 0600 env files."""
import base64
from dataclasses import dataclass
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from cj_api.aead_cursor import AeadCursorCodec
from cj_api.history_config import CursorPolicy,HistoryWireConfiguration
from cj_api.local_app import create_local_app
from cj_api.local_run_context import load_run_context
from cj_api.supabase_test_database import SupabaseTestDatabase
from cj_strict_json import reject_duplicates
from cj_trip.confirmation import ConfirmationSigner


def decoded(name,*,length=None):
    try:value=base64.b64decode(os.environ[name],validate=True)
    except (KeyError,ValueError):raise ValueError('missing_or_invalid_'+name) from None
    if length is not None and len(value)!=length:raise ValueError('invalid_length_'+name)
    return value


def authorization():
    if (os.environ.get('CJ_ENV')!='local' or os.environ.get('CJ_DEPLOY_TARGET')!='hk-beta'
            or os.environ.get('CJ_M4_SYNTHETIC_ONLY')!='1'):
        raise ValueError('explicit_hk_beta_synthetic_activation_required')
    try:end=datetime.fromisoformat(os.environ['CJ_TRIAL_VALID_UNTIL'])
    except (KeyError,ValueError):raise ValueError('verified_trial_expiry_required') from None
    if end.tzinfo is None or datetime.now(timezone.utc)>=min(end,datetime(2026,11,30,16,tzinfo=timezone.utc)):
        raise ValueError('trial_or_database_authorization_expired')


@dataclass(repr=False)
class Runtime:
    auth:Path
    context:object
    context_path:Path
    descriptors:list

    @classmethod
    def load(cls,root,*,worker=False):
        authorization();root=Path(root)
        root.mkdir(mode=0o700,parents=True,exist_ok=True)
        subjects=json.loads(os.environ['CJ_BETA_SUBJECTS_JSON'],object_pairs_hook=reject_duplicates(ValueError,'duplicate_beta_subject_field'))
        if (type(subjects) is not list or not subjects
                or any(type(s) is not str or re.fullmatch('m4-synthetic-[a-z0-9-]{1,80}',s) is None for s in subjects)
                or len(set(subjects))!=len(subjects)):
            raise ValueError('explicit_unique_beta_synthetic_subjects_required')
        auth=root/'auth';auth.mkdir(mode=0o700,exist_ok=True)
        public=decoded('CJ_BETA_SIGNING_PUBLIC_B64')
        parsed=serialization.load_pem_public_key(public)
        if not isinstance(parsed,rsa.RSAPublicKey) or parsed.key_size<2048:raise ValueError('beta_RSA_public_key_required')
        (auth/'public.pem').write_bytes(public)
        (auth/'invited.json').write_text(json.dumps(subjects))
        descriptors=[]
        if worker:
            private=decoded('CJ_BETA_SIGNING_PRIVATE_B64')
            key=serialization.load_pem_private_key(private,password=None)
            if not isinstance(key,rsa.RSAPrivateKey) or key.public_key().public_numbers()!=parsed.public_numbers():
                raise ValueError('matching_beta_signing_key_required')
            # Linux process memory, never a persisted PEM file. The established
            # token supplier consumes a path; /proc/self/fd reads this process's
            # own in-memory descriptor, with no secret bytes in the symlink.
            fd=os.memfd_create('g2c-beta-signing',0);os.fchmod(fd,0o600);os.write(fd,private);os.lseek(fd,0,0)
            target=auth/'private.pem'
            if target.is_symlink():target.unlink()
            if target.exists():raise ValueError('persisted_private_key_not_adopted')
            target.symlink_to('/proc/self/fd/'+str(fd));descriptors.append(fd)
        context_path=root/'run.json'
        raw=os.environ['CJ_BETA_RUN_CONTEXT_JSON']
        context_path.write_text(raw)
        context=load_run_context(context_path)
        if context.version!='CJ-LOCAL-RUN@2':raise ValueError('registered_beta_run_context_required')
        return cls(auth,context,context_path,descriptors)

    def database(self):
        authorization()
        return SupabaseTestDatabase(os.environ['CJ_SUPABASE_RUNTIME_URI'],os.environ['CJ_SUPABASE_CA_FILE'],run_context=self.context)

    def app(self):
        import time
        key=decoded('CJ_BETA_HISTORY_B64',length=32)
        codec=AeadCursorCodec(keys={'local-history-v1':key},active_key_id='local-history-v1',version='local-history-v1',
            clock=lambda:int(time.time()),max_ttl_seconds=300,max_token_bytes=2048,max_plaintext_bytes=512,max_binding_bytes=2048)
        history=HistoryWireConfiguration(20,16384,1_000_000,CursorPolicy(codec,300,2048))
        return create_local_app(conninfo_path=None,auth_dir=self.auth,database=self.database(),run_context=self.context,
            confirmation_signer=ConfirmationSigner(decoded('CJ_BETA_CONFIRMATION_B64',length=32)),history_configuration=history,
            account_admission=True)

    def close(self):
        for fd in self.descriptors:os.close(fd)
        self.descriptors.clear()
