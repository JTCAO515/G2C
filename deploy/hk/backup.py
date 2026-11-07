"""Daily checkpoint + original OSS object reconciliation, with durable phases."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys

import psycopg

from .configuration import authorization,load_secret_environment
from . import checkpoint,oss_backup


def check_release():
    control = Path(os.environ['CJ_DEPLOY_CONTROL'])
    with checkpoint.operator() as (connection, _), connection.transaction():
        connection.execute('SET TRANSACTION READ ONLY')
        with connection.cursor() as cursor:
            checkpoint.runtime_transaction(cursor, control)


def run():
    authorization();control=Path(os.environ['CJ_DEPLOY_CONTROL']);root=Path(os.environ['CJ_BETA_BACKUP_ROOT'])
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=control/'daily.json';day=datetime.now(timezone.utc).strftime('%Y%m%d')
    # Outer operator lock is distinct from checkpoint's lock, so the daily
    # controller cannot race another timer while export takes its own DB lock.
    with checkpoint.lock(root):
        state=checkpoint.verified(path) if path.exists() else None
        if state is None or state['state']=='COMPLETE' and state['day']!=day:
            previous=None if state is None else state['day']
            state=dict(version='g2c-beta-daily.1',day=day,previous=previous,state='EXPORT_INTENT')
            checkpoint.atomic(path,state)
        package=root/state['day']
        if state['state']=='EXPORT_INTENT':
            if package.exists():
                # Export may have committed. Verify the original artifact and
                # current control/DB identity; never export it a second time.
                manifest=checkpoint.verified(package/'manifest.json')
                latest=checkpoint.verified(control/'latest.json')
                if manifest['dump_sha256']!=latest['dump_sha256'] or checkpoint.local.checksum(package/'database.dump')!=manifest['dump_sha256']:
                    raise ValueError('original_checkpoint_unknown')
                with checkpoint.operator() as (connection,_):checkpoint.require_release(connection,control)
            else:
                checkpoint.export(package,control,base=None if state['previous'] is None else root/state['previous'])
            state['state']='EXPORTED';checkpoint.atomic(path,state)
        if state['state']=='EXPORTED':
            result=oss_backup.upload_package(package,root/'upload-journal')
            state['state']='COMPLETE';checkpoint.atomic(path,state)
            print(json.dumps(dict(status='COMPLETE',day=state['day'],objects=result,actual_cost='UNKNOWN')))
        else:print(json.dumps(dict(status='READ_ONLY_COMPLETE',day=state['day'],actual_cost='UNKNOWN')))


if __name__=='__main__':
    arguments = sys.argv[1:]
    try:
        if arguments == ['--check-release']:
            load_secret_environment('recovery')
            check_release()
        elif not arguments:
            load_secret_environment('backup')
            run()
        else:
            raise ValueError('explicit backup operation required')
    except (oss_backup.oss.exceptions.BaseError,OSError,ValueError,KeyError,psycopg.Error):
        alert = ('beta_backup_source_release_unavailable' if arguments == ['--check-release']
                 else 'beta_backup_unavailable_original_journal_retained')
        print('ALERT '+alert,file=sys.stderr)
        raise SystemExit(1) from None
