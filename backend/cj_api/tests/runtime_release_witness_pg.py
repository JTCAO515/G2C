"""Actual runtime-role native release/restore barrier; no Hong Kong changes."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
from threading import Event
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import psycopg

from cj_api.local_app import LocalDatabase,ISSUER,scope_for
from cj_api.local_worker_context import checker_for
from cj_api.runtime_release_witness import NativeReleaseWitness
from cj_auth.interfaces import AdmissionStatus
import local_history_pg as harness
from deploy.hk import checkpoint,configuration
from runtime_adapter import Unavailable
import dev_auth


def exercise(auth,conninfo):
    dev_auth.init(auth,['release-owner'])
    token=dev_auth.token(auth,'release-owner',30);checker=checker_for(auth)
    scope=scope_for(ISSUER,'release-owner');database=LocalDatabase(conninfo)
    control=auth.parent/'release-control';control.mkdir(mode=0o700)
    key=Ed25519PrivateKey.generate()
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,11,14,tzinfo=timezone.utc)
    environment=dict(CJ_ENV='local',CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',
        CJ_DEPLOY_CONTROL=str(control),
        CJ_TRIAL_VALID_UNTIL='2026-11-15T00:00:00+00:00',
        CJ_BETA_RECOVERY_PRIVATE_B64=base64.b64encode(key.private_bytes(serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,serialization.NoEncryption())).decode(),
        CJ_BETA_RECOVERY_PUBLIC_B64=base64.b64encode(key.public_key().public_bytes(
            serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode())
    # Use the actual HK before_scope hook too: it verifies the release during
    # bind, before the reader's explicit second verification.
    database._before_scope=configuration.runtime_transaction
    def guard():
        decision=checker.check(token)
        if decision.status is not AdmissionStatus.ALLOWED:
            raise Unavailable('LOCAL_ORIGINAL_AUTH_WITHHELD')
        assert scope_for(decision.principal.issuer,decision.principal.subject)==scope
    source=NativeReleaseWitness(database,scope,control,guard=guard,release=checkpoint)
    config=json.loads(conninfo.read_bytes())
    with patch.dict(os.environ,environment),patch('deploy.hk.configuration.datetime',Clock),\
            psycopg.connect(**config,autocommit=True)as admin:
        instance,lineage=checkpoint.identity(admin)
        def signed(current):
            checkpoint.atomic(control/'release.json',dict(version='g2c-beta-release.1',
                instance=current,lineage=lineage,checkpoint='local-fixture'),public=True)
        signed(instance)
        before=source.observe()
        assert (before.instance,before.lineage)==(instance,lineage)
        assert source.with_current(before,lambda value:b'bounded-local-metadata')==b'bounded-local-metadata'
        try:source.with_current(before,lambda value:iter([b'late']))
        except Unavailable:pass
        else:raise AssertionError('lazy projection escaped native release lifetime')
        with database.connect(scope)as current:
            assert current.execute('SELECT current_user').fetchone()[0]=='cj_m1_runtime'
        try:
            with database.connect(scope)as current:
                checkpoint.rotate(current)
        except psycopg.errors.InsufficientPrivilege:pass
        else:raise AssertionError('runtime role rotated the native epoch')
        release=(control/'release.json').read_bytes()
        invalid=json.loads(release);invalid['value']['instance']='00000000-0000-0000-0000-000000000000'
        (control/'release.json').write_text(json.dumps(invalid))
        try:source.observe()
        except Unavailable:pass
        else:raise AssertionError('tampered signed release accepted')
        (control/'release.json').write_bytes(release)

        projected=[]
        with psycopg.connect(**config)as held:
            held.execute('SELECT pg_advisory_xact_lock(%s)',(checkpoint.RELEASE_LOCK,))
            try:source.with_current(before,lambda value:projected.append(value)or b'not-reached')
            except Unavailable as error:
                assert isinstance(error.__context__,psycopg.errors.LockNotAvailable)
            else:raise AssertionError('exclusive native restore did not stop the bounded reader')
        assert not projected and source.observe()==before

        entered=Event()
        def restore_generation():
            with psycopg.connect(**config)as writer:
                entered.set()
                writer.execute('SELECT pg_advisory_xact_lock(%s)',(checkpoint.RELEASE_LOCK,))
                return checkpoint.rotate(writer)
        with ThreadPoolExecutor(max_workers=1)as pool:
            pending=[]
            def project(value):
                pending.append(pool.submit(restore_generation));assert entered.wait(5)
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    row=admin.execute("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' "
                        "AND query LIKE 'SELECT pg_advisory_xact_lock(%'").fetchone()[0]
                    if row:break
                    time.sleep(.01)
                else:raise AssertionError('native restore writer did not block')
                assert not pending[0].done()
                return b'original-release-projection'
            assert source.with_current(before,project)==b'original-release-projection'
            after_instance=pending[0].result(timeout=10)
        # The unchanged old signed file cannot authorize the changed database.
        try:source.observe()
        except Unavailable:pass
        else:raise AssertionError('old signed release authorized a rotated database')
        signed(after_instance);after=source.observe();assert before!=after
        try:source.with_current(before,lambda value:b'stale-baseline')
        except Unavailable:pass
        else:raise AssertionError('old fixture reused after native generation change')
        def broken_projection(value):raise ValueError('local internal projection bug')
        try:source.with_current(after,broken_projection)
        except ValueError:pass
        else:raise AssertionError('internal projection bug was hidden as source success')
        def revoke_during_projection(value):
            (auth/'invited.json').write_text('[]')
            return b'earlier-result-must-be-withheld'
        try:source.with_current(after,revoke_during_projection)
        except Unavailable:pass
        else:raise AssertionError('revoked projection returned earlier private bytes')
        (auth/'invited.json').write_text('[]')
        try:source.observe()
        except Unavailable:pass
        else:raise AssertionError('revoked caller reused a release observation')
    print('PASS real runtime SELECT-only epoch, native shared/exclusive release barrier, '
        'signed-file/database mismatch and rotation rejection, current AUTH; HK/full fixture UNRUN')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
