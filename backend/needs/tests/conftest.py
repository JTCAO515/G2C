"""Every invocation creates and preserves a NEW task-private PG cluster, Unix only."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'backend/needs'), str(ROOT / 'backend/auth')]


@pytest.fixture(scope='session')
def pg():
    # Test process only: reject all inherited libpq environment choices.
    for key in list(os.environ):
        if key.startswith('PG'): del os.environ[key]
    base = ROOT / 'backend/needs/.local'
    base.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='p', dir=base))
    data, socket, passfile = root / 'data', root / 's', root / 'empty.pass'
    socket.mkdir(mode=0o700)
    passfile.touch(mode=0o600)
    bindir = Path('/opt/homebrew/opt/postgresql@17/bin')
    assert (bindir / 'initdb').is_file(), 'explicit PostgreSQL 17 installation required'
    env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C'}
    role, port = 'cj013_synthetic', 56413
    def run(*args):
        return subprocess.run([str(bindir / args[0]), *args[1:]], env=env,
                              text=True, capture_output=True, check=True).stdout
    run('initdb', '-D', str(data), '-U', role, '--auth-local=trust', '--auth-host=reject', '--encoding=UTF8', '--no-locale')
    options = f"-k {socket} -p {port} -c listen_addresses='' -c unix_socket_permissions=0700"
    def start(): run('pg_ctl', '-D', str(data), '-l', str(root / 'postgres.log'), '-o', options, '-w', 'start')
    def stop(): run('pg_ctl', '-D', str(data), '-m', 'fast', '-w', 'stop')
    def connect():
        return psycopg.connect(host=str(socket), port=port, user=role, dbname='postgres',
                               password='', passfile=str(passfile), connect_timeout=3,
                               sslmode='disable', options='')
    started = False
    try:
        start(); started = True
        with connect() as conn:
            assert conn.execute('SHOW listen_addresses').fetchone()[0] == ''
            conn.execute((ROOT / 'backend/needs/sql/candidate.sql').read_text())
        class Cluster:
            def __init__(self): self.connect = connect
            def restart(self): stop(); start()
        print(f'NEW_PRIVATE_PG={root}; role={role}; port={port}; TCP=disabled; synthetic_only=true')
        yield Cluster()
    finally:
        if started:
            stop()
            assert not (data / 'postmaster.pid').exists()
            (root / 'STOPPED').write_text('Stopped; cluster preserved; no TCP listener\n')
            print(f'PG_STOPPED_PRESERVED={root}')


@pytest.fixture
def scope(pg):
    import uuid
    value = 's-' + uuid.uuid4().hex
    with pg.connect() as conn:
        conn.execute('INSERT INTO cj_needs_scope VALUES (%s)', (value,))
    return value
