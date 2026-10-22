"""One-shot fresh private PG test. Never reuse an existing directory or apply candidates."""
import argparse
import json
import os
from pathlib import Path
import shlex
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = None
PG = Path('/opt/homebrew/Cellar/postgresql@16/16.15/bin')
USER = 'cj005i'
PORT = '55447'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}


def run(argv, **kwargs):
    result = subprocess.run([str(a) for a in argv], env=ENV,
                            capture_output=True, text=True, **kwargs)
    if result.returncode:
        (PRIVATE / 'command-failure.log').write_text(result.stderr)
        result.check_returncode()
    return result


def main():
    global PRIVATE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-name', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'\.local-cj005-init-[a-z0-9-]+', args.target_name):
        raise RuntimeError('task-private target name required')
    PRIVATE = ROOT / args.target_name
    if any(k.startswith('PG') or k in ('DATABASE_URL', 'CJ_DATABASE_URL') for k in os.environ):
        raise RuntimeError('inherited target configuration refused')
    if PRIVATE.exists() or PRIVATE.is_symlink():
        raise RuntimeError('existing private root refused')
    if len(str(PRIVATE / 's' / ('.s.PGSQL.' + PORT)).encode()) >= 104:
        raise RuntimeError('socket path too long')
    PRIVATE.mkdir(mode=0o700)
    (PRIVATE / 's').mkdir(mode=0o700)
    run([PG / 'initdb', '-D', PRIVATE / 'data', '--username='+USER,
         '--auth-local=trust', '--auth-host=reject', '--encoding=UTF8', '--locale=C', '--no-clean'])
    started = False
    try:
        run([PG / 'pg_ctl', '-D', PRIVATE / 'data', '-l', PRIVATE / 'postgres.log',
             '-o', shlex.join(['-c', 'listen_addresses=', '-k', str(PRIVATE / 's'),
                              '-p', PORT, '-c', 'unix_socket_permissions=0700']), '-w', 'start'])
        started = True
        check = [sys.executable, '-B', ROOT / 'scripts/check-empty-db-init.py',
                 '--source-repo', ROOT, '--inspect-target', '--target-root', PRIVATE,
                 '--pg-bin', PG, '--user', USER, '--port', PORT]
        state = json.loads(run(check).stdout)
        assert state['target_admission'] == 'PASS' and state['apply'] == 'BLOCKED'
        # Accepted registered foundation v1 only: exercise duplicate-initialization rejection.
        # No MESSAGE/RUN/USAGE SQL is executed.
        run([PG / 'psql', '-X', '-w', '-v', 'ON_ERROR_STOP=1', '-h', PRIVATE / 's',
             '-p', PORT, '-U', USER, '-d', 'postgres', '-f',
             ROOT / 'backend/migrations/0001_foundation.sql'])
        repeated = subprocess.run([str(x) for x in check], env=ENV, capture_output=True)
        assert repeated.returncode == 2
        print('PASS: fresh private PG16 empty admission; registered foundation seed; repeated/nonempty target refused; candidate apply BLOCKED')
    finally:
        if started or (PRIVATE / 'data/postmaster.pid').exists():
            run([PG / 'pg_ctl', '-D', PRIVATE / 'data', '-m', 'fast', '-w', 'stop'])
        assert not (PRIVATE / 'data/postmaster.pid').exists()
        assert not (PRIVATE / 's' / ('.s.PGSQL.' + PORT)).exists()
        print('PASS: private PostgreSQL stopped; no PID or socket; files retained')


if __name__ == '__main__':
    main()
