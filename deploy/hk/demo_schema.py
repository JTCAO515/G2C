"""One reviewed additive local PG upgrade, followed by a new signed backup base."""
import os
from pathlib import Path
import sys

import psycopg

import migrate
from . import checkpoint,demo_quota,local_postgres
from .configuration import load_secret_environment,local_database_target


def schema_anchor(target):
    return f'demo-schema{target}'


def upgrade(control,backups,*,target=49,schema_root=None):
    if not local_database_target():raise ValueError('HK local Demo upgrade required')
    local_postgres.require_serving(control)
    expected=checkpoint.versions()
    if target not in (49,50,51,52) or expected!=list(range(1,target+1)):
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
        if db.execute("SELECT (SELECT count(*) FROM cj_message_delivery WHERE NOT acknowledged),"
                "(SELECT count(*) FROM cj_run_record WHERE status IN ('queued','running'))").fetchone()!=(0,0):
            raise ValueError('original application work still in flight')
        before=checkpoint.local.fence_state(db)
        if target==52:
            current_count,next_count=demo_quota.upgrade(db)
        checkpoint.atomic(marker,dict(state='INTENT',lineage=release['lineage'],original_fences=before))
        migrate.up(db,migrate.load(),target)
    manifest=checkpoint.export(destination,control,schema_root=schema_root)
    if manifest['fences']!=before or manifest['lineage']!=release['lineage']:
        raise ValueError('Demo upgrade fence state changed')
    checkpoint.atomic(marker,dict(state='COMPLETE',lineage=manifest['lineage'],
        dump_sha256=manifest['dump_sha256'],original_fences=before))
    if target==52:
        print(f'Quota raised for {current_count} current and {next_count} next-period ledgers')
    print(f'PASS exact additive {target} with original deletion fences and new signed local backup base')


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
        if arguments not in ([],['--target','50'],['--target','51'],['--target','52']):
            raise ValueError('explicit Demo schema upgrade required')
        load_secret_environment('recovery')
        upgrade(Path(os.environ['CJ_DEPLOY_CONTROL']),Path('/backups'),target=int(arguments[1]) if arguments else 49)
    except (OSError,ValueError,KeyError,psycopg.Error):
        print('ALERT Demo schema upgrade unavailable; reconcile original state',file=sys.stderr)
        raise SystemExit(1) from None
