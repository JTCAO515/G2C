"""Bounded synthetic source producers for the real Supabase recovery rehearsal.

Only the two generated rehearsal identities are admitted to this private host.
FakeProvider tests storage/fences; it is never evidence for a real model. An
interrupted action is inspection-only, not a replacement identity or resend.
"""
import argparse
from dataclasses import asdict
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

from fastapi.testclient import TestClient
from psycopg import sql

import dev_auth
import run_worker
from local_run_context import provision_budget_connection
from deploy.hk import staging
import migrate
from cj_agent.provider import FakeProvider,ProviderUnknown
from cj_api.local_app import create_local_app,scope_for,ISSUER
from cj_api.local_cleanup import Configuration
from cj_api.local_account_admission_v2 import account_checker_for,subject_digest
from cj_api.supabase_cleanup import SupabaseCleanupConfiguration,SupabaseCleanupRuntime
from cj_api.supabase_test_database import SupabaseTestDatabase
from cj_auth.interfaces import AdmissionStatus
from cj_cleanup.core import encode,digest
from cj_cleanup.memory_payloads import hooks,hold_payloads
from cj_memory.domain import Service as MemoryService
from cj_memory.postgres import Repository
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory_jobs.service import Service as HistoryService
from cj_message.auth_boundary import Boundary
from cj_memory_withdrawal.erasure_driver_v2 import ErasureServiceV2
from cj_memory_withdrawal.erasure_service import ORDER
from cj_memory_withdrawal.account_cleanup import account_hooks
from . import checkpoint,configuration


class Host:
    def __init__(self,runtime,database,cleanup_factory,operator,control,backup_root):
        self.control=Path(control);self.state_path=self.control/'cloud-rehearsal.json'
        self.base=Path(backup_root)/'base'
        self.runtime=runtime;self.database=database;self.operator=operator
        all_subjects=json.loads((self.runtime.auth/'invited.json').read_bytes())
        selected=sorted(s for s in all_subjects if re.fullmatch(r'm4-synthetic-recovery-[0-9a-f]{12}-[ab]',s))
        if (len(selected)!=2 or all_subjects!=selected or selected[0][:-1]!=selected[1][:-1]):raise ValueError('exact_original_two_rehearsal_subjects_required')
        self.subjects=selected;self.nonce=selected[0].rsplit('-',2)[1]
        # A separate narrowed invite file cannot make FakeProvider consume a
        # pending message belonging to an active beta/device tester.
        self.auth=self.runtime.auth.parent/'selected-auth';self.auth.mkdir(mode=0o700)
        (self.auth/'public.pem').write_bytes((self.runtime.auth/'public.pem').read_bytes())
        (self.auth/'invited.json').write_text(json.dumps(selected))
        (self.auth/'private.pem').symlink_to(self.runtime.auth/'private.pem')
        self.checker=account_checker_for(self.auth,self.database)
        registry=self.runtime.auth.parent/'registry.json'
        registry.write_bytes(encode(dict(version='g2c-beta-rehearsal-components.1',stores=[
            dict(id='memory-derived',cleanup_protocol='CLEANUP@1.1'),dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),
            dict(id='business',objects=[dict(id=name.split('/')[1],cleanup_protocol='CLEANUP@1.1') for name in ORDER if name.startswith('business/')])])))
        key=configuration.decoded('CJ_BETA_CLEANUP_B64',length=32)
        local=Configuration({'beta-rehearsal':key},'beta-rehearsal',3600,ORDER,registry,
            extra_hooks=account_hooks)
        self.cleanup_configuration,self.cleanup=cleanup_factory(local)
        self.app=create_local_app(conninfo_path=None,auth_dir=self.auth,database=self.database,run_context=self.runtime.context,
            travel_context=True,trip_context=True,cleanup_configuration=self.cleanup_configuration,account_admission=True)
        self.item='rehearsal-item-'+self.nonce
        deadline=min(datetime.now(timezone.utc)+timedelta(hours=2),datetime(2026,11,30,16,tzinfo=timezone.utc))
        profile=dict(subjects=['self'],slots={'diet.spicy':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
        collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=deadline.isoformat(),
            profiles={subject:profile for subject in selected}),travel_contexts={subject:[] for subject in selected})
        self.memory=TypedRuntimeConfiguration.from_bytes(encode(dict(version='local-memory-run.2',collection=collection,
            selections={subject:dict(subject='self',slots=['diet.spicy'],max_bytes=8000) for subject in selected})))
        boundary=Boundary(self.checker,lambda principal:self.database.message_repository(scope_for(principal.issuer,principal.subject)),lambda:uuid.uuid4().hex)
        self.collection=HistoryService(boundary,self.repository)
        self.erasure=ErasureServiceV2(self.collection,self.cleanup,hooks,hold_payloads=hold_payloads,
            max_sources=1000,max_jobs=1000,max_association_bytes=1_000_000)

    def close(self):self.runtime.close()
    def token(self,subject):return dev_auth.token(self.auth,subject,15)
    def scope(self,subject):return scope_for(ISSUER,subject)

    def repository(self,principal,scope):
        with self.database.connect(scope) as connection:connection.execute('INSERT INTO cj_memory_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',(scope,))
        return Repository(lambda:self.database.connect(scope),scope,typed_context=True,transaction_binder=lambda conn,cur:conn.bind_scope(cur))

    def load(self):
        state=checkpoint.verified(self.state_path)
        if (state.get('version')!='g2c-beta-cloud-rehearsal.1' or state.get('subjects')!=self.subjects or state.get('item')!=self.item):
            raise ValueError('original_rehearsal_identity_required')
        return state

    def save(self,state):checkpoint.atomic(self.state_path,state)

    def send(self,client,subject):
        headers={'Authorization':'Bearer '+self.token(subject),'Content-Type':'application/octet-stream'}
        chat='recovery-chat-'+subject[-1]
        response=client.put('/v1/conversations',params=dict(conversation_id=chat),headers=headers)
        if response.status_code!=200:raise ValueError('original_synthetic_conversation_unavailable')
        head=response.json()
        response=client.post('/v1/messages',content=encode(dict(version='MESSAGE-send.1',conversation_id=chat,message_id=chat,
            text='SYNTHETIC recovery fixture; use my explicitly saved synthetic preference.',trip_id=None,creation_intent='none',
            expected_generation=head['generation'],expected_sequence=0)),headers=headers)
        if response.status_code!=200:raise ValueError('original_synthetic_message_unavailable')
        return response.json()['receipt']

    def seed(self):
        if self.state_path.exists():return self.inspect()
        state=dict(version='g2c-beta-cloud-rehearsal.1',subjects=self.subjects,item=self.item,stage='SEED_INTENT',real_model_calls=0)
        a,b=self.subjects
        with self.operator() as (connection,_),connection.transaction():
            connection.execute('SELECT pg_advisory_xact_lock_shared(%s)',(checkpoint.RELEASE_LOCK,))
            checkpoint.require_release(connection,self.control)
            self.save(state)
            for subject in self.subjects:provision_budget_connection(connection,self.runtime.context,subject)
        with TestClient(self.app) as client:self.send(client,a)
        model=FakeProvider();outcomes=run_worker.run_once(self.database,model,self.auth,account_admission=True)
        if len(outcomes)!=1 or outcomes[0].status!='completed':raise ValueError('original_account_fixture_run_incomplete')
        token=self.token(b);decision=self.checker.check(token)
        if decision.status is not AdmissionStatus.ALLOWED:raise ValueError('original_memory_owner_not_admitted')
        principal=decision.principal;scope=self.scope(b);repository=self.repository(principal,scope)
        policy=self.memory.collection.policy(b);service=MemoryService(repository,manual_policy=policy)
        def guard(stage):
            current=self.checker.check(token)
            if current.status is not AdmissionStatus.ALLOWED or current.principal!=principal:raise ValueError('original_memory_owner_changed')
            return principal,scope
        command=encode(dict(version='MEMORY-manual.2',operation_id='recovery-save-'+self.nonce,item_id=self.item,subject='self',slot='diet.spicy',
            kind='preference',text='SYNTHETIC no spicy food',extent='long_term',context=None,occurred_at='UNKNOWN'))
        service.with_operation(guard,lambda context:encode(asdict(context.save_manual_typed(command))))
        with TestClient(self.app) as client:self.send(client,b)
        class Unknown(FakeProvider):
            def stream(self,*args,**kwargs):self.calls+=1;raise ProviderUnknown('synthetic original unknown')
        uncertain=Unknown();outcomes=run_worker.run_once(self.database,uncertain,self.auth,memory_configuration=self.memory,account_admission=True)
        if len(outcomes)!=1 or outcomes[0].status!='unknown' or uncertain.calls!=1:raise ValueError('original_uncertain_fixture_run_unavailable')
        state.update(seeded_at=time.time(),unknown_run_id=outcomes[0].run_id);self.save(state)
        proof=self.inspect();self.require_seeded(proof)
        state.update(stage='SEEDED');self.save(state)
        return self.inspect()

    def erase(self):
        state=self.load()
        if state['stage']!='SEEDED':return self.inspect()
        # A real signed base must have been exported before any deletion.
        base=self.require_base(state)
        state.update(stage='ERASURE_INTENT',base_dump_sha256=base['dump_sha256']);self.save(state)
        a,b=self.subjects;token=self.token(a);admission=self.checker.check(token)
        if admission.status is not AdmissionStatus.ALLOWED:raise ValueError('original_account_not_admitted')
        state['account_subject_digest']=subject_digest(admission.principal);self.save(state)
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
        with TestClient(self.app) as client:
            def post(url,value):
                response=client.post(url,content=encode(value),headers=headers)
                if response.status_code!=200:raise ValueError('original_account_cleanup_unavailable')
                return response.json()
            device=post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='recovery-register-'+self.nonce,device_id='recovery-device-'+self.nonce,state_ref=digest(b'synthetic recovery device')))
            operation=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='recovery-retire-'+self.nonce,binding_id=device['binding_id']))
            state['account_operation_id']=operation['operation_id'];self.save(state)
            result=post('/v1/account-cleanup-operations/'+operation['operation_id']+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=operation['registry_digest'],confirmation='DELETE_ACCOUNT'))
            if result['business_access']!='revoked' or result['online_status']!='complete':raise ValueError('original_selected_account_cleanup_incomplete')
        result=json.loads(self.erasure.delete(self.token(b),self.erasure_command()))
        if result['online_status']!='complete':raise ValueError('original_item_cleanup_incomplete')
        state.update(memory_action_id='recovery-delete-'+self.nonce,memory_operation_id=result['operation_id']);self.save(state)
        proof=self.inspect();self.require_deleted(proof)
        state.update(stage='DELETED');self.save(state)
        return self.inspect()

    def erasure_command(self):
        return encode(dict(version='MEMORY-ERASURE@1',action_id='recovery-delete-'+self.nonce,item_id=self.item,expected_version=1,derived_range='owned_trip_derived_scope'))

    @staticmethod
    def require_seeded(proof):
        if (proof['rows']!=dict(account_messages=1,retained_messages=1,selected_memory=1)
                or proof['account_access']!='allowed' or proof['memory_owner_access']!='allowed'):
            raise ValueError('original_seed_physical_state_unavailable')

    @staticmethod
    def require_deleted(proof):
        if (proof['rows']!=dict(account_messages=0,retained_messages=1,selected_memory=0)
                or proof['account_access']!='denied' or proof['memory_owner_access']!='allowed'
                or any(proof['fence_counts'][name]!=1 for name in ('cj_account_fence','item','action'))):
            raise ValueError('original_erasure_physical_or_fence_proof_unavailable')

    def require_base(self,state):
        # This artifact must contain the completed original seed, not merely a
        # signed pointer or an earlier backup. No target mutation precedes this.
        base=checkpoint.verified(self.base/'manifest.json');latest=checkpoint.verified(self.control/'latest.json')
        if (base.get('version')!='g2c-beta-data-checkpoint.1' or base.get('base') is not None
                or base['schema']!=checkpoint.versions() or base['at']<state['seeded_at']
                or latest.get('version')!='g2c-beta-latest.1' or latest['consumed']
                or latest['dump_sha256']!=base['dump_sha256'] or latest['lineage']!=base['lineage']
                or checkpoint.local.checksum(self.base/'database.dump')!=base['dump_sha256']):
            raise ValueError('original_seeded_base_checkpoint_required')
        self.require_seeded(self.inspect())
        with self.operator() as (connection,_):
            # Acquire the session barrier before creating the repeatable-read
            # snapshot. A writer finishing while we wait must be visible.
            connection.execute('SELECT pg_advisory_lock(%s)',(checkpoint.RELEASE_LOCK,))
            try:
                with connection.transaction():
                    connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                    checkpoint.require_release(connection,self.control)
                    connection.execute("SET TIME ZONE 'UTC'")
                    for table in base['tables']:
                        connection.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(sql.Identifier(*table.split('.'))))
                    if (checkpoint.identity(connection)[1]!=base['lineage'] or migrate.inventory(connection)!=base['tables']
                            or staging.state(connection,base['tables'])!=base['row_state']
                            or staging.sequence_state(connection,list(base['sequences']))!=base['sequences']
                            or checkpoint.local.fence_state(connection)!=base['fences']):
                        raise ValueError('original_seeded_base_does_not_match_current_source')
            finally:connection.execute('SELECT pg_advisory_unlock(%s)',(checkpoint.RELEASE_LOCK,))
        return base

    def inspect(self):
        state=self.load();a,b=self.subjects;owner_a=digest(self.scope(a).encode());owner_b=digest(self.scope(b).encode())
        with self.operator() as (connection,_):
            prepared=connection.execute('SELECT operation_id FROM cj_cleanup_request WHERE subject_digest=%s AND action_id=%s',
                (state.get('account_subject_digest'),'recovery-retire-'+self.nonce)).fetchone()
            account_operation=None if prepared is None else prepared[0]
            action=connection.execute("SELECT operation_id,original_input_sha256 FROM cj_memory_erasure_fence WHERE scope_digest=%s AND kind='action' AND reference_sha256=%s",
                (owner_b,digest(('recovery-delete-'+self.nonce).encode()))).fetchone()
            memory_operation=None if action is None else action[0]
            if (state.get('account_operation_id') is not None and state['account_operation_id']!=account_operation
                    or state.get('memory_operation_id') is not None and state['memory_operation_id']!=memory_operation
                    or action is not None and action[1]!=digest(self.erasure_command())):
                raise ValueError('original_erasure_action_binding_differs')
            rows=dict(account_messages=connection.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(self.scope(a),)).fetchone()[0],
                retained_messages=connection.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(self.scope(b),)).fetchone()[0],
                selected_memory=connection.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s AND item_id=%s',(self.scope(b),self.item)).fetchone()[0])
            account=connection.execute('SELECT count(*) FROM cj_account_fence WHERE owner_digest=%s AND subject_digest=%s AND operation_id=%s',
                (owner_a,state.get('account_subject_digest'),account_operation)).fetchone()[0]
            item=connection.execute("SELECT count(*) FROM cj_memory_erasure_fence WHERE scope_digest=%s AND kind='item' AND reference_sha256=%s",
                (owner_b,digest(self.item.encode()))).fetchone()[0]
            action=connection.execute("SELECT count(*) FROM cj_memory_erasure_fence WHERE scope_digest=%s AND kind='action' AND reference_sha256=%s AND operation_id=%s",
                (owner_b,digest(('recovery-delete-'+self.nonce).encode()),memory_operation)).fetchone()[0]
        proof=dict(mode='READ_ONLY',stage=state['stage'],subjects=self.subjects,item=self.item,rows=rows,
            account_access=self.checker.check(self.token(a)).status.value,memory_owner_access=self.checker.check(self.token(b)).status.value,
            fence_counts=dict(cj_account_fence=account,item=item,action=action),
            account_operation_id=account_operation,memory_operation_id=memory_operation,
            original_unknown_run_id=state.get('unknown_run_id'),real_model_calls=0,actual_cost='UNKNOWN')
        if state['stage']=='SEEDED':self.require_seeded(proof)
        if state['stage']=='DELETED':self.require_deleted(proof)
        return proof


def from_environment():
    configuration.authorization()
    for name in ('SUBJECTS_JSON','SIGNING_PUBLIC_B64','SIGNING_PRIVATE_B64'):
        os.environ['CJ_BETA_'+name]=os.environ['CJ_REHEARSAL_'+name]
    runtime=configuration.Runtime.load('/tmp/g2c-cloud-rehearsal',worker=True)
    database=SupabaseTestDatabase(os.environ['CJ_SUPABASE_RUNTIME_URI'],os.environ['CJ_SUPABASE_CA_FILE'],
        run_context=runtime.context,travel_context=True,trip_context=True,transaction_guard=configuration.runtime_transaction)
    def cleanup_factory(options):
        value=SupabaseCleanupConfiguration(options,os.environ['CJ_SUPABASE_CLEANUP_URI'],Path(os.environ['CJ_SUPABASE_CA_FILE']),
            lambda cursor:configuration.cleanup_transaction(cursor,database))
        return value,SupabaseCleanupRuntime(database,value,scope_for)
    return Host(runtime,database,cleanup_factory,checkpoint.operator,Path('/control'),Path('/backups/cloud-rehearsal'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('seed','erase','inspect'));args=parser.parse_args()
    configuration.load_secret_environment('rehearsal');host=None
    try:
        host=from_environment()
        with checkpoint.lock(host.control):result={'seed':host.seed,'erase':host.erase,'inspect':host.inspect}[args.command]()
        print(json.dumps(result))
    except Exception as error:
        print(json.dumps(dict(state='UNAVAILABLE_OR_HOLD',error_type=type(error).__name__,real_model_calls=0)),file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        if host is not None:host.close()


if __name__=='__main__':main()
