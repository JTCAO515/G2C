"""Beta environment boundary. Persistent application secrets live only in 0600 env files."""
import base64
from dataclasses import dataclass
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import stat

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from cj_api.aead_cursor import AeadCursorCodec
from cj_api.history_config import CursorPolicy,HistoryWireConfiguration
from cj_api.local_app import create_local_app,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.supabase_test_database import SupabaseTestDatabase
from cj_strict_json import reject_duplicates
from cj_trip.confirmation import ConfirmationSigner


SECRET_FILES={
    'api':{'api':{'CJ_SUPABASE_RUNTIME_URI','CJ_BETA_CONFIRMATION_B64','CJ_BETA_HISTORY_B64'}},
    'worker':{'worker':{'CJ_SUPABASE_RUNTIME_URI','CJ_BETA_SIGNING_PRIVATE_B64','CJ_MODEL_API_KEY','CJ_AMAP_WEB_KEY'}},
    'migrate':{'operator':{'CJ_SUPABASE_OPERATOR_URI','CJ_BETA_RECOVERY_PRIVATE_B64'}},
    'recovery':{'operator':{'CJ_SUPABASE_OPERATOR_URI','CJ_BETA_RECOVERY_PRIVATE_B64'}},
    'rehearsal':{'operator':{'CJ_SUPABASE_OPERATOR_URI','CJ_BETA_RECOVERY_PRIVATE_B64'},
                 'rehearsal':{'CJ_SUPABASE_RUNTIME_URI','CJ_SUPABASE_CLEANUP_URI','CJ_REHEARSAL_SUBJECTS_JSON','CJ_REHEARSAL_SIGNING_PUBLIC_B64','CJ_REHEARSAL_SIGNING_PRIVATE_B64','CJ_BETA_CLEANUP_B64'}},
    'backup':{'operator':{'CJ_SUPABASE_OPERATOR_URI','CJ_BETA_RECOVERY_PRIVATE_B64'},
              'backup':{'CJ_BETA_BACKUP_ROOT','OSS_ACCESS_KEY_ID','OSS_ACCESS_KEY_SECRET'}},
}
TYPED_POLICY='CJ_BETA_TYPED_MEMORY_POLICY_B64'


def load_secret_environment(role,*,root=Path('/run/secrets')):
    """Docker receives only paths; secret bytes enter this process, not Config.Env."""
    expected=SECRET_FILES[role];values={}
    for file,names in expected.items():
        optional={TYPED_POLICY} if role=='api' and file=='api' else set()
        allowed=names|optional
        if any(name in os.environ for name in allowed):raise ValueError('persistent_container_secret_environment_refused')
        descriptor=os.open(Path(root)/(file+'.env'),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(descriptor,'rb') as source:
            metadata=os.fstat(source.fileno())
            if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode)!=0o600 or metadata.st_uid!=os.getuid():
                raise ValueError('owned_0600_secret_environment_file_required')
            raw=source.read(65537)
        if len(raw)>65536:raise ValueError('bounded_secret_environment_required')
        parsed={}
        for line in raw.decode('utf8').splitlines():
            name,separator,value=line.partition('=')
            if not separator or name not in allowed or name in parsed or not value or '\0' in value:
                raise ValueError('explicit_secret_environment_fields_required')
            parsed[name]=value
        if not names<=parsed.keys():raise ValueError('complete_secret_environment_required')
        values.update(parsed)
    os.environ.update(values)


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
    typed_memory:object=None
    subjects:frozenset=frozenset()

    @classmethod
    def load(cls,root,*,worker=False):
        authorization();root=Path(root)
        root.mkdir(mode=0o700,parents=True,exist_ok=True)
        subjects=json.loads(os.environ['CJ_BETA_SUBJECTS_JSON'],object_pairs_hook=reject_duplicates(ValueError,'duplicate_beta_subject_field'))
        if (type(subjects) is not list or not subjects
                or any(type(s) is not str or re.fullmatch('m4-synthetic-[a-z0-9-]{1,80}',s) is None for s in subjects)
                or len(set(subjects))!=len(subjects)):
            raise ValueError('explicit_unique_beta_synthetic_subjects_required')
        typed_memory=None
        if TYPED_POLICY in os.environ:
            if worker:raise ValueError('typed_memory_policy_is_API_only')
            from cj_memory.typed_local import TypedConfiguration
            typed_memory=TypedConfiguration.from_bytes(decoded(TYPED_POLICY))
            if not frozenset(typed_memory.collection.profiles)<=frozenset(subjects):
                raise ValueError('typed_memory_policy_outside_beta_invites')
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
        return cls(auth,context,context_path,descriptors,typed_memory,frozenset(subjects))

    def database(self):
        authorization()
        return SupabaseTestDatabase(os.environ['CJ_SUPABASE_RUNTIME_URI'],os.environ['CJ_SUPABASE_CA_FILE'],run_context=self.context,
            travel_context=self.typed_memory is not None,transaction_guard=runtime_transaction)

    def app(self):
        import time
        key=decoded('CJ_BETA_HISTORY_B64',length=32)
        codec=AeadCursorCodec(keys={'local-history-v1':key},active_key_id='local-history-v1',version='local-history-v1',
            clock=lambda:int(time.time()),max_ttl_seconds=300,max_token_bytes=2048,max_plaintext_bytes=512,max_binding_bytes=2048)
        history=HistoryWireConfiguration(20,16384,1_000_000,CursorPolicy(codec,300,2048))
        database=self.database()
        for subject in self.subjects:
            with database.connect(scope_for(ISSUER,subject)) as connection:
                existing=connection.execute('SELECT 1 FROM cj_memory_scope LIMIT 1').fetchone()
            if existing and (self.typed_memory is None or subject not in self.typed_memory.collection.profiles):
                raise ValueError('existing_beta_memory_requires_explicit_policy')
        message_subjects=None if self.typed_memory is None else self.subjects-frozenset(self.typed_memory.collection.profiles)
        app=create_local_app(conninfo_path=None,auth_dir=self.auth,database=database,run_context=self.context,
            confirmation_signer=ConfirmationSigner(decoded('CJ_BETA_CONFIRMATION_B64',length=32)),history_configuration=history,
            account_admission=True,needs_profile=os.environ.get('CJ_LOCAL_NEEDS_PROFILE'),message_subjects=message_subjects)
        if self.typed_memory is not None:
            from cj_memory.typed_api import register_typed_routes
            register_typed_routes(app,database=database,auth_dir=self.auth,configuration=self.typed_memory)
        return app

    def close(self):
        for fd in self.descriptors:os.close(fd)
        self.descriptors.clear()


def runtime_transaction(cursor):
    from . import checkpoint
    checkpoint.runtime_transaction(cursor,Path(os.environ['CJ_DEPLOY_CONTROL']))


def cleanup_transaction(cursor,runtime_database):
    from . import checkpoint
    # Cleanup has no schema-metadata grants. Keep its shared transaction barrier
    # while the separately approved runtime login checks the signed DB identity.
    # Cleanup writes still use only the independent cleanup login and its RLS.
    cursor.execute('SELECT pg_advisory_xact_lock_shared(%s)',(checkpoint.RELEASE_LOCK,))
    with runtime_database._open_runtime_connection() as runtime:
        checkpoint.require_release(runtime,Path(os.environ['CJ_DEPLOY_CONTROL']))
