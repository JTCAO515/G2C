"""Beta environment boundary. Persistent application secrets live only in 0600 env files."""
import base64
from dataclasses import dataclass,field,replace
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import stat
import zlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from cj_api.aead_cursor import AeadCursorCodec
from cj_api.history_config import CursorPolicy,HistoryWireConfiguration
from cj_api.local_app import create_local_app,scope_for,ISSUER
from cj_api.local_run_context import LocalRunContext,load_run_context
from cj_api.supabase_test_database import SupabaseTestDatabase
from cj_strict_json import reject_duplicates
from cj_trip.confirmation import ConfirmationSigner
from cj_usage.authorization_budget import DEADLINE,DEMO_DEADLINE


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
TYPED_POLICY_GZIP='CJ_BETA_TYPED_MEMORY_POLICY_GZIP_B64'
MEMORY_RUN_POLICY='CJ_BETA_MEMORY_RUN_POLICY_B64'
MEMORY_RUN_POLICY_GZIP='CJ_BETA_MEMORY_RUN_POLICY_GZIP_B64'
TYPED_MESSAGE_SUBJECTS='CJ_BETA_TYPED_MESSAGE_SUBJECTS_JSON'
MODEL_STREAM_SUBJECT='CJ_BETA_MODEL_STREAM_SUBJECT'
ASSEMBLY_SUBJECTS='CJ_BETA_ASSEMBLY_SUBJECTS_JSON'
ASSEMBLY_RUN_CREDENTIAL_SUBJECTS='CJ_BETA_ASSEMBLY_RUN_CREDENTIAL_SUBJECTS_JSON'
ASSEMBLY_MODEL_STREAM_SUBJECTS='CJ_BETA_ASSEMBLY_MODEL_STREAM_SUBJECTS_JSON'
ASSEMBLY_PROBE_MESSAGE='CJ_BETA_ASSEMBLY_PROBE_MESSAGE_ID'
DEMO_SUBJECTS='CJ_BETA_DEMO_SUBJECTS_JSON'
ASSEMBLY_CLEANUP={'CJ_SUPABASE_CLEANUP_URI','CJ_BETA_CLEANUP_B64'}


def load_secret_environment(role,*,root=Path('/run/secrets')):
    """Docker receives only paths; secret bytes enter this process, not Config.Env."""
    expected=SECRET_FILES[role];values={}
    for file,names in expected.items():
        optional=({TYPED_POLICY,TYPED_POLICY_GZIP,TYPED_MESSAGE_SUBJECTS}|ASSEMBLY_CLEANUP if role=='api' and file=='api' else
                  {MEMORY_RUN_POLICY,MEMORY_RUN_POLICY_GZIP,MODEL_STREAM_SUBJECT,ASSEMBLY_RUN_CREDENTIAL_SUBJECTS,ASSEMBLY_MODEL_STREAM_SUBJECTS,
                   ASSEMBLY_PROBE_MESSAGE,'CJ_BETA_CONFIRMATION_B64'}
                  if role=='worker' and file=='worker' else set())
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


def _policy_bytes(plain,gzip,label):
    if plain in os.environ and gzip in os.environ:
        raise ValueError('one_'+label+'_encoding_required')
    if gzip not in os.environ:return decoded(plain)
    inflater=zlib.decompressobj(16+zlib.MAX_WBITS)
    try:raw=inflater.decompress(decoded(gzip),262145)
    except zlib.error:raise ValueError('invalid_'+label+'_gzip') from None
    if len(raw)>262144:raise ValueError('bounded_'+label+'_required')
    if not inflater.eof or inflater.unused_data:
        raise ValueError('complete_single_'+label+'_gzip_required')
    return raw


def typed_policy_bytes():
    """API-only encodings of the same bounded, fully validated policy."""
    return _policy_bytes(TYPED_POLICY,TYPED_POLICY_GZIP,'typed_memory_policy')


def memory_run_policy_bytes():
    """Worker-only encodings; the original runtime policy validates the result."""
    return _policy_bytes(MEMORY_RUN_POLICY,MEMORY_RUN_POLICY_GZIP,'memory_run_policy')


def authorization():
    if (os.environ.get('CJ_ENV')!='local' or os.environ.get('CJ_DEPLOY_TARGET')!='hk-beta'
            or os.environ.get('CJ_M4_SYNTHETIC_ONLY')!='1'):
        raise ValueError('explicit_hk_beta_synthetic_activation_required')
    try:end=datetime.fromisoformat(os.environ['CJ_TRIAL_VALID_UNTIL'])
    except (KeyError,ValueError):raise ValueError('verified_trial_expiry_required') from None
    from cj_api.supabase_test_database import hk_demo_enabled
    cutoff=datetime(2026,12,31,16,tzinfo=timezone.utc) if hk_demo_enabled() else datetime(2026,11,30,16,tzinfo=timezone.utc)
    if end.tzinfo is None or datetime.now(timezone.utc)>=min(end,cutoff):
        raise ValueError('trial_or_database_authorization_expired')


def local_database_target():
    target=os.environ.get('CJ_BETA_DB_TARGET','supabase')
    if target not in ('supabase','hk-local'):
        raise ValueError('explicit beta database target required')
    return target=='hk-local'


def _worker_assembly_pair(key,worker,assembly_subjects,error):
    if key not in os.environ:return frozenset()
    selected=json.loads(os.environ[key])
    if (not worker or not assembly_subjects or type(selected) is not list or len(selected)!=2
            or any(type(subject) is not str for subject in selected)
            or frozenset(selected)!=assembly_subjects):
        raise ValueError(error)
    return assembly_subjects


def demo_periods(context, now):
    current=context.current
    meter=current.meter
    if meter.period_end!=int(DEADLINE.timestamp()):
        raise ValueError('original HK Demo Meter period required')
    following=replace(context,current=replace(current,meter=replace(meter,
        period_start=meter.period_end,period_end=int(DEMO_DEADLINE.timestamp()))),
        history=(current,*context.history))
    if meter.period_start<=now<meter.period_end:return context,following
    if meter.period_end<=now<following.current.meter.period_end:return following,None
    raise ValueError('active HK Demo Meter period required')


def beta_subjects():
    subjects=json.loads(os.environ['CJ_BETA_SUBJECTS_JSON'],object_pairs_hook=reject_duplicates(ValueError,'duplicate_beta_subject_field'))
    if (type(subjects) is not list or not subjects
            or any(type(s) is not str or re.fullmatch('m4-synthetic-[a-z0-9-]{1,80}',s) is None for s in subjects)
            or len(set(subjects))!=len(subjects)):
        raise ValueError('explicit_unique_beta_synthetic_subjects_required')
    demo=json.loads(os.environ.get(DEMO_SUBJECTS,'[]'))
    if (type(demo) is not list or len(demo)>205
            or any(type(s) is not str or re.fullmatch(r'm4-synthetic-demo-[a-z0-9]{12}',s) is None for s in demo)
            or len(set(demo))!=len(demo)
            or set(demo)!={s for s in subjects if s.startswith('m4-synthetic-demo-')}
            or demo and not local_database_target()):
        raise ValueError('explicit HK local demo invitation subjects required')
    return subjects,frozenset(demo)


@dataclass(repr=False)
class Runtime:
    auth:Path
    context:object
    context_path:Path
    descriptors:list
    typed_memory:object=None
    subjects:frozenset=frozenset()
    memory_runtime:object=None
    typed_message_subjects:frozenset=frozenset()
    assembly_subjects:frozenset=frozenset()
    assembly_run_credential_subjects:frozenset=frozenset()
    assembly_model_stream_subjects:frozenset=frozenset()
    demo_subjects:frozenset=frozenset()
    demo_next_context:LocalRunContext|None=None
    _database:SupabaseTestDatabase|None=field(default=None,init=False)

    @classmethod
    def load(cls,root,*,worker=False):
        authorization();root=Path(root)
        root.mkdir(mode=0o700,parents=True,exist_ok=True)
        subjects,demo_subjects=beta_subjects()
        assembly_subjects=frozenset()
        if ASSEMBLY_SUBJECTS in os.environ:
            selected=json.loads(os.environ[ASSEMBLY_SUBJECTS])
            if (type(selected) is not list or len(selected)!=2
                    or any(type(s) is not str or re.fullmatch(r'm4-synthetic-660-[a-f0-9]{12}-(zh|en)',s) is None
                           for s in selected)
                    or not frozenset(selected)<=frozenset(subjects)):
                raise ValueError('explicit_invited_bilingual_assembly_pair_required')
            zh,en=sorted(selected,reverse=True)
            if not zh.endswith('-zh') or not en.endswith('-en') or zh[:-2]!=en[:-2]:
                raise ValueError('explicit_invited_bilingual_assembly_pair_required')
            assembly_subjects=frozenset(selected)
        assembly_run_credential_subjects=_worker_assembly_pair(ASSEMBLY_RUN_CREDENTIAL_SUBJECTS,worker,
            assembly_subjects,'explicit_worker_assembly_run_credential_pair_required')
        assembly_model_stream_subjects=_worker_assembly_pair(ASSEMBLY_MODEL_STREAM_SUBJECTS,worker,
            assembly_subjects,'explicit_worker_assembly_model_stream_pair_required')
        typed_memory=None
        if TYPED_POLICY in os.environ or TYPED_POLICY_GZIP in os.environ:
            if worker:raise ValueError('typed_memory_policy_is_API_only')
            from cj_memory.typed_local import TypedConfiguration
            typed_memory=TypedConfiguration.from_bytes(typed_policy_bytes())
            if not frozenset(typed_memory.collection.profiles)<=frozenset(subjects):
                raise ValueError('typed_memory_policy_outside_beta_invites')
        memory_runtime=None
        if MEMORY_RUN_POLICY in os.environ or MEMORY_RUN_POLICY_GZIP in os.environ:
            if not worker:raise ValueError('memory_run_policy_is_worker_only')
            from cj_memory.typed_runtime import TypedRuntimeConfiguration
            memory_runtime=TypedRuntimeConfiguration.from_bytes(memory_run_policy_bytes())
            selected=frozenset(memory_runtime.selections)
            if (selected!=frozenset(memory_runtime.collection.collection.profiles)
                    or not selected<=frozenset(subjects)):
                raise ValueError('explicit_memory_run_selection_for_beta_invites_required')
        planning=assembly_subjects|demo_subjects
        if worker and planning and (memory_runtime is None
                or not planning<=frozenset(memory_runtime.selections)):
            raise ValueError('assembly_requires_canonical_typed_worker')
        typed_message_subjects=frozenset()
        if TYPED_MESSAGE_SUBJECTS in os.environ:
            if worker:raise ValueError('typed_message_subjects_are_API_only')
            selected=json.loads(os.environ[TYPED_MESSAGE_SUBJECTS],object_pairs_hook=reject_duplicates(ValueError,'duplicate_typed_message_field'))
            if (typed_memory is None or type(selected) is not list or not selected
                    or any(type(s) is not str for s in selected) or len(set(selected))!=len(selected)
                    or not frozenset(selected)<=frozenset(typed_memory.collection.profiles)):
                raise ValueError('explicit_typed_message_policy_subjects_required')
            typed_message_subjects=frozenset(selected)
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
        context=load_run_context(context_path,require_active=not demo_subjects)
        if context.version!='CJ-LOCAL-RUN@2':raise ValueError('registered_beta_run_context_required')
        next_context=None
        if demo_subjects:context,next_context=demo_periods(context,datetime.now(timezone.utc).timestamp())
        return cls(auth,context,context_path,descriptors,typed_memory,frozenset(subjects),memory_runtime,
                   typed_message_subjects,assembly_subjects,assembly_run_credential_subjects,assembly_model_stream_subjects,
                   demo_subjects,next_context)

    @property
    def planning_subjects(self):
        return self.assembly_subjects|self.demo_subjects

    def memory_configuration_for_scope(self,scope):
        if self.memory_runtime is not None and scope in {
                scope_for(ISSUER,subject) for subject in self.memory_runtime.selections}:
            return self.memory_runtime
        return None

    def database(self):
        authorization()
        if self._database is None:
            size=os.environ.get('CJ_BETA_DB_POOL_SIZE')
            if size is not None and re.fullmatch('[1-8]',size) is None:
                raise ValueError('bounded_beta_runtime_pool_required')
            local=local_database_target()
            ca=None if local else os.environ['CJ_SUPABASE_CA_FILE']
            self._database=SupabaseTestDatabase(os.environ['CJ_SUPABASE_RUNTIME_URI'],ca,run_context=self.context,
                travel_context=self.typed_memory is not None or self.memory_runtime is not None,
                needs_context=bool(self.planning_subjects),transaction_guard=runtime_transaction,
                pool_size=None if size is None else int(size),local_socket=local)
        return self._database

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
        for subject in self.typed_message_subjects:
            if subject in self.demo_subjects:
                scope=scope_for(ISSUER,subject)
                with database.connect(scope) as connection:
                    if connection.execute('SELECT public.cj_account_scope_current(%s)',(scope,)).fetchone()==(False,):
                        continue
            if not database.travel_profile(scope_for(ISSUER,subject)):
                raise ValueError('original_typed_message_travel_profile_required')
        message_subjects=(None if self.typed_memory is None else
                          self.subjects-(frozenset(self.typed_memory.collection.profiles)-self.typed_message_subjects))
        needs_profile=os.environ.get('CJ_LOCAL_NEEDS_PROFILE')
        signer=ConfirmationSigner(decoded('CJ_BETA_CONFIRMATION_B64',length=32))
        cleanup=None
        planning=self.planning_subjects
        if planning:
            if not planning<=self.typed_message_subjects or needs_profile!='manual-v1':
                raise ValueError('assembly_requires_original_typed_message_and_manual_needs')
            cleanup=assembly_cleanup(database)
        elif ASSEMBLY_CLEANUP & os.environ.keys():
            raise ValueError('cleanup_requires_explicit_assembly_pair')
        lio_memory_factory=None
        lio_profile_epoch_reader=None
        if self.demo_subjects:
            from cj_api.lio_memory_routes import LioMemoryCards
            from cj_api.local_lio_memory import lio_candidates
            from cj_memory.epoch_projection import CurrentScopeEpochReader

            lio_profile_epoch_reader=CurrentScopeEpochReader.for_api(database,self.typed_memory)

            def lio_memory_factory(boundary):
                candidates=lio_candidates(database,boundary,self.demo_subjects,self.typed_memory)
                return LioMemoryCards(candidates.collection,candidates.current)

        app=create_local_app(conninfo_path=None,auth_dir=self.auth,database=database,run_context=self.context,
            confirmation_signer=signer,history_configuration=history,
            account_admission=True,needs_profile=needs_profile,message_subjects=message_subjects,
            existing_display_reads=True,cleanup_configuration=cleanup,
            cleanup_subjects=planning or None,demo_dialogue_subjects=planning or None,
            lio_dialogue_subjects=self.demo_subjects or None,lio_memory_factory=lio_memory_factory,
            lio_calendar_subjects=self.demo_subjects or None,
            lio_exploration_subjects=self.demo_subjects or None,
            lio_profile_epoch_reader=lio_profile_epoch_reader)
        if self.typed_memory is not None:
            from cj_memory.typed_api import register_typed_routes
            typed_memory=self.typed_memory
            if self.demo_subjects:
                from cj_api.local_lio_memory import pilot_write_configuration
                typed_memory=pilot_write_configuration(typed_memory,self.demo_subjects)
            register_typed_routes(app,database=database,auth_dir=self.auth,configuration=typed_memory)
        if planning:
            from cj_trip.local_needs_app import register_local_needs_routes
            from cj_trip.local_manual_app import register_local_manual_routes
            from cj_trip.local_structured_read import register_local_structured_read_routes
            register_local_needs_routes(app,database=database,auth_dir=self.auth,confirmation_signer=signer,
                planning_only=True,selected_subjects=planning)
            register_local_manual_routes(app,database=database,auth_dir=self.auth,confirmation_signer=signer,
                editing_only=True,selected_subjects=planning)
            register_local_structured_read_routes(app,database=database,auth_dir=self.auth,
                selected_subjects=planning)
            register_assembly_erasure(app,database,self.auth,cleanup,planning)
        if self.demo_subjects:
            from .demo_login import register_demo_login
            register_demo_login(app)

        from cj_api.local_account_admission_v2 import permit_retirement_read_lease
        from cj_api.supabase_test_database import current_authorization,require_environment

        def require_current():
            current_authorization(local_socket=local_database_target())
            require_environment()

        @app.middleware('http')
        async def retirement_lease(request,call_next):
            path=request.url.path
            if ((request.method=='POST' and path in ('/v1/messages','/v2/messages'))
                    or (request.method=='GET' and (path in ('/v1/run-events','/v2/run-events')
                        or self.typed_memory is not None and path=='/v2/memories'))):
                with permit_retirement_read_lease(database,require_current):
                    return await call_next(request)
            return await call_next(request)
        return app

    def close(self):
        if self._database is not None:self._database.close()
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
    with runtime_database._open_dedicated_runtime_connection() as runtime:
        checkpoint.require_release(runtime,Path(os.environ['CJ_DEPLOY_CONTROL']))


def assembly_cleanup(database):
    from cj_api.local_cleanup import Configuration
    from cj_api.supabase_cleanup import SupabaseCleanupConfiguration
    from cj_cleanup.device_v4 import TARGETS
    from cj_memory_withdrawal.account_cleanup import account_hooks

    key_id='hk-beta-assembly'
    inventory=('business/message','business/usage','business/memory-authoritative','business/trip-authoritative',
        'business/needs-current-planning','business/feedback-private-actions','business/cleanup-metadata',
        'business/memory-management-actions','checkpoints/run','memory-derived',*TARGETS,'external-processing')
    config=Configuration({key_id:decoded('CJ_BETA_CLEANUP_B64',length=32)},key_id,3600,inventory,
        Path(__file__).resolve().parents[2]/'backend/storage-registry.json',extra_hooks=account_hooks,control_records=True)
    local=local_database_target()
    ca=None if local else Path(os.environ['CJ_SUPABASE_CA_FILE'])
    return SupabaseCleanupConfiguration(config,os.environ['CJ_SUPABASE_CLEANUP_URI'],ca,
        lambda cursor:cleanup_transaction(cursor,database),local_socket=local)


def register_assembly_erasure(app,database,auth_dir,configuration,subjects):
    import uuid
    from cj_api.local_account_admission_v2 import account_checker_for
    from cj_api.supabase_cleanup import SupabaseCleanupRuntime
    from cj_cleanup.memory_payloads import hold_payloads,hooks
    from cj_memory.postgres import Repository
    from cj_memory_jobs.service import Service
    from cj_memory_withdrawal.erasure_api import register
    from cj_memory_withdrawal.erasure_driver_v2 import ErasureServiceV2
    from cj_message.auth_boundary import Boundary

    checker=account_checker_for(auth_dir,database,selected_subjects=subjects)
    boundary=Boundary(checker,lambda principal:database.message_repository(scope_for(principal.issuer,principal.subject)),
        lambda:uuid.uuid4().hex)

    def repository(principal,scope):
        return Repository(lambda:database.connect(scope),scope,typed_context=True,
            transaction_binder=lambda connection,cursor:connection.bind_scope(cursor))

    cleanup=SupabaseCleanupRuntime(database,configuration,scope_for)
    service=ErasureServiceV2(Service(boundary,repository),cleanup,hooks,hold_payloads=hold_payloads,
        max_sources=1000,max_jobs=1000,max_association_bytes=1_000_000)
    register(app,service)
