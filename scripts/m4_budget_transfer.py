"""One-way transfer of the existing shared journal. Never reset attempts/holds.

Seal runs on the stopped Mac producer; adopt runs only on the approved host.
Both sides retain identical immutable attempt bytes. Unknown transfer stays sealed.
"""
import argparse
import hashlib
import os
from pathlib import Path
import sqlite3

from cj_usage.authorization_budget import MAC_PRODUCER,HK_PRODUCER

SEALED='sealed-for-'+HK_PRODUCER


def seal(source,destination):
    source=Path(source);destination=Path(destination)
    if not source.is_file() or destination.exists():raise ValueError('existing_original_and_new_transfer_required')
    with sqlite3.connect(source,timeout=10) as connection:
        connection.execute('PRAGMA synchronous=FULL');connection.execute('BEGIN IMMEDIATE')
        connection.execute('CREATE TABLE IF NOT EXISTS producer(singleton INTEGER PRIMARY KEY CHECK(singleton=1),identity TEXT NOT NULL)')
        row=connection.execute('SELECT identity FROM producer WHERE singleton=1').fetchone()
        if row not in (None,(MAC_PRODUCER,),(SEALED,)):raise ValueError('original_mac_journal_required')
        connection.execute('INSERT OR REPLACE INTO producer VALUES(1,?)',(SEALED,));connection.commit()
        # Existing producers read the seal inside their write transaction. A
        # process holding the lock finishes first; no later begin/finish can pass.
        descriptor=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
        with sqlite3.connect(destination) as target:connection.backup(target)
    return hashlib.file_digest(destination.open('rb'),'sha256').hexdigest()


def adopt(path,expected_sha256):
    path=Path(path)
    if os.environ.get('CJ_DEPLOY_TARGET')!='hk-beta' or os.environ.get('CJ_M4_BUDGET_PRODUCER')!=HK_PRODUCER:
        raise ValueError('approved_host_activation_required')
    if not path.is_file() or hashlib.file_digest(path.open('rb'),'sha256').hexdigest()!=expected_sha256:
        raise ValueError('exact_transferred_original_required')
    with sqlite3.connect(path,timeout=10) as connection:
        connection.execute('PRAGMA synchronous=FULL');connection.execute('BEGIN IMMEDIATE')
        if connection.execute('SELECT identity FROM producer WHERE singleton=1').fetchone()!=(SEALED,):
            raise ValueError('sealed_original_transfer_required')
        connection.execute('UPDATE producer SET identity=? WHERE singleton=1',(HK_PRODUCER,))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('seal');a.add_argument('source',type=Path);a.add_argument('destination',type=Path)
    a=sub.add_parser('adopt');a.add_argument('path',type=Path);a.add_argument('--sha256',required=True)
    args=parser.parse_args()
    if args.command=='seal':print('SEALED_TRANSFER_SHA256='+seal(args.source,args.destination))
    else:adopt(args.path,args.sha256);print('PASS original shared attempts/holds adopted; Mac remains read only')


if __name__=='__main__':main()
