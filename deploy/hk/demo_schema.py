"""One reviewed additive local PG upgrade, followed by a new signed backup base."""
import os
from pathlib import Path
import sys
from uuid import uuid4

import psycopg

import migrate
from . import checkpoint,demo_quota,local_postgres,staging
from .configuration import load_secret_environment,local_database_target


def schema_anchor(target):
    return f'demo-schema{target}'


def _require_idle(db):
    if db.execute("SELECT (SELECT count(*) FROM cj_message_delivery WHERE NOT acknowledged),"
                  "(SELECT count(*) FROM cj_run_record WHERE status IN ('queued','running'))").fetchone()!=(0,0):
        raise ValueError('original application work still in flight')


def _complete(marker,manifest,intent):
    if manifest['fences']!=intent['original_fences'] or manifest['lineage']!=intent['lineage']:
        raise ValueError('Demo upgrade fence state changed')
    complete=dict(state='COMPLETE',lineage=manifest['lineage'],
        dump_sha256=manifest['dump_sha256'],original_fences=intent['original_fences'])
    if 'quota_policy_sha256' in intent:
        complete['quota_policy_sha256']=intent['quota_policy_sha256']
    checkpoint.atomic(marker,complete)


def _preserve_unpublished(path):
    path.rename(path.with_name(f'{path.name}.unpublished-{uuid4().hex}'))
    checkpoint.local.sync_directory(path.parent)


def _original_latest(control):
    path=control/'latest.json'
    return checkpoint.verified(path) if path.exists() else None


def _migrate_quota_schema(db):
    migrate.up(db,migrate.load(),52)
    db.execute('INSERT INTO public.cj_demo_quota_upgrade VALUES (true)')


def _resume_publication(db,control,destination,intent,release,instance):
    manifest=checkpoint.verified(destination/'manifest.json')
    digest=manifest['dump_sha256']
    lineage=intent['lineage']
    if (manifest['version']!='g2c-beta-data-checkpoint.1'
            or manifest['schema']!=checkpoint.versions() or manifest['archived_instance']!=intent['original_instance']
            or manifest['lineage']!=lineage or manifest['fences']!=intent['original_fences']
            or checkpoint.local.checksum(destination/'database.dump')!=digest):
        raise ValueError('original quota backup mismatch')
    latest=control/'latest.json'
    previous=intent['original_checkpoint']
    desired=dict(version='g2c-beta-latest.1',dump_sha256=digest,lineage=lineage,consumed=False)
    actual=checkpoint.verified(latest) if latest.exists() else None
    if actual not in (desired,intent['original_latest']):
        raise ValueError('original quota latest checkpoint mismatch')
    if (release['instance'],release['checkpoint'])==(instance,digest):
        if actual!=desired:
            raise ValueError('original quota backup publication incomplete')
    elif ((release['instance'],release['checkpoint'])==(intent['original_instance'],previous)
          and instance!=intent['original_instance']):
        # The original export rotated the database identity before publishing
        # its release. Reconcile that exact signed archive against the live data.
        if (manifest['tables']!=migrate.inventory(db) or staging.state(db,manifest['tables'])!=manifest['row_state']
                or staging.sequence_state(db,staging.sequence_names(db))!=manifest['sequences']):
            raise ValueError('original quota database differs from signed backup')
        for path in (latest,control/'release.json'):
            pending=path.with_suffix('.tmp')
            if pending.exists():
                _preserve_unpublished(pending)
        checkpoint.atomic(latest,desired)
        checkpoint.atomic(control/'release.json',
            dict(version='g2c-beta-release.1',instance=instance,lineage=lineage,checkpoint=digest),public=True)
    else:
        raise ValueError('original quota release identity unavailable')
    return manifest


def upgrade(control,backups,*,target=49,schema_root=None):
    if not local_database_target():raise ValueError('HK local Demo upgrade required')
    local_postgres.require_serving(control)
    expected=checkpoint.versions()
    if target not in (49,50,51,52,53) or expected!=list(range(1,target+1)):
        raise ValueError('exact Demo migration chain required')
    anchor=schema_anchor(target)
    marker=control/(anchor+'.json')
    destination=backups/anchor
    with checkpoint.lock(control),checkpoint.operator() as (db,_),db.transaction():
        db.execute('SELECT pg_advisory_xact_lock(%s)',(checkpoint.RELEASE_LOCK,))
        release=checkpoint.verified(control/'release.json')
        if (marker.exists() or destination.exists() or release.get('version')!='g2c-beta-release.1'
                or checkpoint.identity(db)!=(release['instance'],release['lineage'])
                or migrate.applied(db)!=expected[:-1]):
            raise ValueError('reconcile original Demo schema action before retry')
        _require_idle(db)
        intent=dict(state='INTENT',lineage=release['lineage'],original_fences=checkpoint.local.fence_state(db))
        if target in (52,53):
            latest=_original_latest(control)
            if latest is None:
                if release['checkpoint']!='fresh':
                    raise ValueError('original quota latest checkpoint unavailable')
            elif (latest['version']!='g2c-beta-latest.1' or latest['lineage']!=release['lineage']
                  or latest['dump_sha256']!=release['checkpoint'] or type(latest['consumed']) is not bool):
                raise ValueError('original quota latest checkpoint mismatch')
            intent.update(original_instance=release['instance'],original_checkpoint=release['checkpoint'],
                          original_latest=latest)
            if target==52:
                current_count,next_count=demo_quota.upgrade(db)
                policy,roster=demo_quota.original_policy()
                intent.update(quota_policy_sha256=policy,quota_roster_sha256=roster)
            pending=marker.with_suffix('.tmp')
            if pending.exists():
                _preserve_unpublished(pending)
        checkpoint.atomic(marker,intent)
        if target==52:
            _migrate_quota_schema(db)
        else:
            migrate.up(db,migrate.load(),target)
    manifest=checkpoint.export(destination,control,schema_root=schema_root)
    _complete(marker,manifest,intent)
    if target==52:
        print(f'Quota raised for {current_count} current and {next_count} next-period ledgers')
    print(f'PASS exact additive {target} with original deletion fences and new signed local backup base')


def resume_quota(control,backups,*,schema_root=None):
    """Continue the original quota intent with the exact original policy and release."""
    if not local_database_target() or checkpoint.versions()!=list(range(1,53)):
        raise ValueError('exact HK quota schema required')
    local_postgres.require_serving(control)
    marker=control/'demo-schema52.json'
    destination=backups/'demo-schema52'
    with checkpoint.lock(control),checkpoint.operator() as (db,_),db.transaction():
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        db.execute('SELECT pg_advisory_xact_lock(%s)',(checkpoint.RELEASE_LOCK,))
        intent=checkpoint.verified(marker)
        release=checkpoint.verified(control/'release.json')
        instance,lineage=checkpoint.identity(db)
        applied=migrate.applied(db)
        expected=checkpoint.versions()
        if (intent['state']!='INTENT' or release['version']!='g2c-beta-release.1'
                or release['lineage']!=lineage or lineage!=intent['lineage']
                or checkpoint.local.fence_state(db)!=intent['original_fences']
                or demo_quota.original_policy()!=(intent['quota_policy_sha256'],intent['quota_roster_sha256'])):
            raise ValueError('original quota upgrade state unavailable')
        _require_idle(db)
        original_release=(instance,release['instance'],release['checkpoint'])==(
            intent['original_instance'],intent['original_instance'],intent['original_checkpoint'])
        if applied==expected[:-1]:
            if not original_release or destination.exists() or _original_latest(control)!=intent['original_latest']:
                raise ValueError('original rolled-back quota state unavailable')
            demo_quota.upgrade(db,resume=True)
            _migrate_quota_schema(db)
        elif applied==expected and db.execute('SELECT singleton FROM public.cj_demo_quota_upgrade').fetchall()==[(True,)]:
            demo_quota.verify_applied(db)
        else:
            raise ValueError('original quota schema unavailable')
        if not original_release:
            manifest=_resume_publication(db,control,destination,intent,release,instance)
            pending=marker.with_suffix('.tmp')
            if pending.exists():
                _preserve_unpublished(pending)
            _complete(marker,manifest,intent)
            return
        if destination.exists():
            # The original release still names the old instance and checkpoint.
            # Keep the unpublished attempt and create a fresh backup of the same committed state.
            _preserve_unpublished(destination)
    manifest=checkpoint.export(destination,control,schema_root=schema_root)
    _complete(marker,manifest,intent)


def resume_schema53(control,backups,*,schema_root=None):
    """Reconcile the original signed wire-origin upgrade, never a new attempt."""
    if not local_database_target() or checkpoint.versions()!=list(range(1,54)):
        raise ValueError('exact HK wire-origin schema required')
    local_postgres.require_serving(control)
    marker=control/'demo-schema53.json'
    destination=backups/'demo-schema53'
    with checkpoint.lock(control),checkpoint.operator() as (db,_),db.transaction():
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        db.execute('SELECT pg_advisory_xact_lock(%s)',(checkpoint.RELEASE_LOCK,))
        intent=checkpoint.verified(marker)
        release=checkpoint.verified(control/'release.json')
        instance,lineage=checkpoint.identity(db)
        applied=migrate.applied(db)
        expected=checkpoint.versions()
        if (intent['state']!='INTENT' or release['version']!='g2c-beta-release.1'
                or release['lineage']!=lineage or lineage!=intent['lineage']
                or checkpoint.local.fence_state(db)!=intent['original_fences']):
            raise ValueError('original wire-origin upgrade state unavailable')
        _require_idle(db)
        original_release=(instance,release['instance'],release['checkpoint'])==(
            intent['original_instance'],intent['original_instance'],intent['original_checkpoint'])
        if applied==expected[:-1]:
            if not original_release or destination.exists() or _original_latest(control)!=intent['original_latest']:
                raise ValueError('original rolled-back wire-origin state unavailable')
            migrate.up(db,migrate.load(),53)
        elif applied!=expected:
            raise ValueError('original wire-origin schema unavailable')
        if not original_release:
            manifest=_resume_publication(db,control,destination,intent,release,instance)
            pending=marker.with_suffix('.tmp')
            if pending.exists():_preserve_unpublished(pending)
            _complete(marker,manifest,intent)
            return
        if destination.exists():_preserve_unpublished(destination)
    manifest=checkpoint.export(destination,control,schema_root=schema_root)
    _complete(marker,manifest,intent)


def daily_base(control,root,previous):
    if previous is None:return None
    regular=root/previous
    prior=checkpoint.verified(regular/'manifest.json')
    current=checkpoint.versions()
    if prior['schema']==current:return regular
    anchor=schema_anchor(current[-1])
    marker=checkpoint.verified(control/(anchor+'.json'))
    base=root/anchor
    manifest=checkpoint.verified(base/'manifest.json')
    if (not local_database_target() or marker['state']!='COMPLETE'
            or prior['lineage']!=manifest['lineage'] or marker['lineage']!=manifest['lineage']
            or manifest['schema']!=current or marker['dump_sha256']!=manifest['dump_sha256']
            or any(not set(prior['fences'][name])<=set(rows) for name,rows in manifest['fences'].items())):
        raise ValueError('original signed Demo backup base required')
    return base


if __name__=='__main__':
    try:
        arguments=sys.argv[1:]
        if arguments not in ([],['--target','50'],['--target','51'],['--target','52'],['--target','53'],
                             ['--resume-quota'],['--resume-schema53']):
            raise ValueError('explicit Demo schema upgrade required')
        load_secret_environment('recovery')
        control=Path(os.environ['CJ_DEPLOY_CONTROL'])
        if arguments==['--resume-quota']:
            resume_quota(control,Path('/backups'))
            print('PASS original HK quota backup resumed')
        elif arguments==['--resume-schema53']:
            resume_schema53(control,Path('/backups'))
            print('PASS original HK wire-origin backup resumed')
        else:
            upgrade(control,Path('/backups'),target=int(arguments[1]) if arguments else 49)
    except (OSError,ValueError,KeyError,psycopg.Error):
        print('ALERT Demo schema upgrade unavailable; reconcile original state',file=sys.stderr)
        raise SystemExit(1) from None
