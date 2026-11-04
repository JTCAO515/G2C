"""One original Mac journal → one fixed HK journal; never reset or re-adopt."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from cj_usage import authorization_budget as budget

MAC_ROOT=Path.home()/'.local/share/g2c/m4-real-services'
HK_ROOT=Path('/budget')
SEALED='sealed-for-'+budget.HK_PRODUCER


def checksum(path):
    with Path(path).open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def save(path,value,*,new=False):
    temporary=path.with_suffix('.tmp')
    with temporary.open('x') as output:
        os.chmod(temporary,0o600);json.dump(value,output);output.flush();os.fsync(output.fileno())
    if new:
        os.link(temporary,path);temporary.unlink()
    else:temporary.replace(path)
    descriptor=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def attempts(connection):
    info=connection.execute('PRAGMA table_info(attempt)').fetchall()
    if [r[1] for r in info]!=['id','kind','input_sha','state','receipt'] or info[0][5]!=1:
        raise ValueError('original_attempt_schema_required')
    rows=connection.execute('SELECT id,kind,input_sha,state,receipt FROM attempt ORDER BY id').fetchall()
    if not rows:raise ValueError('existing_nonempty_M4_shared_history_required')
    for identity,kind,digest,state,receipt in rows:
        if (type(identity) is not str or not 1<=len(identity)<=128 or kind not in budget.LIMITS
                or type(digest) is not str or re.fullmatch('[0-9a-f]{64}',digest) is None
                or state not in ('INTENT','RECEIVED') or (state=='INTENT')!=(receipt is None)
                or receipt is not None and type(json.loads(receipt)) is not dict):
            raise ValueError('original_attempt_history_invalid')
    return len(rows),hashlib.sha256(budget.canonical(rows)).hexdigest()


def seal(source,destination):
    source=Path(source);destination=Path(destination)
    if source!=MAC_ROOT/'m4-outflows.sqlite' or not source.is_file() or destination.exists():
        raise ValueError('fixed_original_source_and_new_transfer_required')
    marker=MAC_ROOT/'transfer.json'
    if marker.exists():raise ValueError('original_transfer_read_only_no_second_export')
    with sqlite3.connect(source.resolve().as_uri()+'?mode=rw',uri=True,timeout=10) as connection:
        connection.execute('PRAGMA synchronous=FULL');connection.execute('BEGIN IMMEDIATE')
        count,digest=attempts(connection)
        connection.execute('CREATE TABLE IF NOT EXISTS producer(singleton INTEGER PRIMARY KEY CHECK(singleton=1),identity TEXT NOT NULL,ledger_id TEXT NOT NULL)')
        connection.execute('INSERT OR IGNORE INTO producer VALUES(1,?,?)',(budget.MAC_PRODUCER,uuid.uuid4().hex))
        row=connection.execute('SELECT identity,ledger_id FROM producer WHERE singleton=1').fetchone()
        if row[0]!=budget.MAC_PRODUCER:raise ValueError('original_Mac_producer_required')
        original=dict(state='INTENT',ledger_id=row[1],transfer_id=uuid.uuid4().hex,attempt_count=count,attempts_sha256=digest)
        save(marker,original,new=True)
        connection.execute('UPDATE producer SET identity=? WHERE singleton=1',(SEALED,))
        connection.execute('CREATE TABLE transfer(transfer_id TEXT PRIMARY KEY,ledger_id TEXT NOT NULL,attempt_count INTEGER NOT NULL,attempts_sha256 TEXT NOT NULL)')
        connection.execute('INSERT INTO transfer VALUES(?,?,?,?)',(original['transfer_id'],row[1],count,digest));connection.commit()
        descriptor=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
        with sqlite3.connect(destination) as target:connection.backup(target)
    original.update(state='SEALED',package_sha256=checksum(destination));save(marker,original)
    return original['package_sha256']


def adopt(package,expected_sha256):
    package=Path(package);anchor=budget.HK_ANCHOR;target=HK_ROOT/'m4-outflows.sqlite'
    if os.environ.get('CJ_DEPLOY_TARGET')!='hk-beta' or os.environ.get('CJ_M4_BUDGET_PRODUCER')!=budget.HK_PRODUCER:
        raise ValueError('approved_host_activation_required')
    if not package.is_file() or checksum(package)!=expected_sha256:raise ValueError('exact_original_transfer_required')
    anchor.parent.mkdir(mode=0o700,parents=True,exist_ok=True);HK_ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (anchor.parent/'adoption.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if anchor.exists():raise ValueError('original_HK_adoption_read_only_no_replay')
        if target.exists():raise ValueError('existing_host_journal_not_overwritten')
        with sqlite3.connect(package.resolve().as_uri()+'?mode=ro',uri=True,timeout=10) as source:
            source.execute('BEGIN')
            count,digest=attempts(source)
            records=source.execute('SELECT transfer_id,ledger_id,attempt_count,attempts_sha256 FROM transfer').fetchall()
            if len(records)!=1:raise ValueError('one_original_transfer_required')
            transfer_id,ledger_id,record_count,record_digest=records[0]
            if ((count,digest)!=(record_count,record_digest)
                    or source.execute('SELECT identity,ledger_id FROM producer WHERE singleton=1').fetchone()!=(SEALED,ledger_id)):
                raise ValueError('sealed_original_history_required')
            state=dict(state='INTENT',ledger_id=ledger_id,transfer_id=transfer_id,attempt_count=count,
                attempts_sha256=digest,package_sha256=expected_sha256)
            save(anchor,state,new=True)
            descriptor=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
            with sqlite3.connect(target) as live:
                live.execute('PRAGMA synchronous=FULL');source.backup(live)
                live.execute('UPDATE producer SET identity=? WHERE singleton=1',(budget.HK_PRODUCER,))
                if attempts(live)!=(count,digest):raise ValueError('copied_original_history_differs')
        state['state']='ADOPTED';save(anchor,state)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('seal');a.add_argument('source',type=Path);a.add_argument('destination',type=Path)
    a=sub.add_parser('adopt');a.add_argument('package',type=Path);a.add_argument('--sha256',required=True)
    args=parser.parse_args()
    if args.command=='seal':print('SEALED_TRANSFER_SHA256='+seal(args.source,args.destination))
    else:adopt(args.package,args.sha256);print('PASS fixed host adopted original attempts/holds; Mac stays read only')


if __name__=='__main__':main()
