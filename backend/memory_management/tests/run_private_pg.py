"""Create one fresh CJ019-only cluster, check, restart, stop and preserve it.

No inherited PG environment/DSN, no TCP listener, no external services. Invoke
with an already installed Python3.11+/psycopg3.2.10; never installs dependencies.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import psycopg

ROOT = Path(__file__).resolve().parents[1]
BIN = Path('/opt/homebrew/opt/postgresql@16/bin')
ROLE = 'cj019_owner'
PORT = 56219  # Task-private Unix socket only; no TCP listener.


def main():
    if sys.version_info < (3, 11) or psycopg.__version__ != '3.2.10':
        raise RuntimeError('requires Python 3.11+ and fixed psycopg 3.2.10')
    local = ROOT / '.local'
    local.mkdir(exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='pg-', dir=local))
    socket = Path(tempfile.mkdtemp(prefix='cj019-', dir='/private/tmp'))
    socket.chmod(0o700)
    data = run / 'data'
    passfile = run / 'empty.pgpass'
    passfile.touch(mode=0o600)
    config = dict(host=str(socket), port=PORT, user=ROLE, dbname='postgres',
                  passfile=str(passfile), connect_timeout=3,
                  options='-c statement_timeout=8000 -c lock_timeout=5000')
    config_path = run / 'connection.json'
    config_path.write_text(json.dumps(config, indent=2))
    env = dict(PATH='/opt/homebrew/bin:/usr/bin:/bin', LANG='C', LC_ALL='C',
               PYTHONDONTWRITEBYTECODE='1')
    report_path = ROOT / 'evidence' / (run.name + '.txt')
    running = False
    with report_path.open('x') as report:
        def record(text):
            print(text, flush=True)
            report.write(text + '\n')
            report.flush()
        def command(args):
            result = subprocess.run([str(x) for x in args], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, timeout=45)
            record(result.stdout.rstrip())
            if result.returncode:
                raise RuntimeError('task-private command failed: ' + str(args[0]))
        def start():
            command([BIN/'pg_ctl', '-D', data, '-l', run/'server.log',
                     '-o', "-c listen_addresses='' -c unix_socket_permissions=0700 -k "
                     + str(socket) + ' -p ' + str(PORT), '-w', 'start'])
        record('CJ019 local real PostgreSQL / synthetic authority fixtures')
        record('data=' + str(data) + '\nsocket=' + str(socket))
        record('PG environment replaced; empty explicit passfile; no TCP listener')
        try:
            command([BIN/'postgres', '--version'])
            command([BIN/'initdb', '-D', data, '-U', ROLE, '--encoding=UTF8',
                     '--locale=C', '--auth-local=trust', '--auth-host=reject'])
            # status can be queried safely even if startup ACK is interrupted.
            try:
                start()
            finally:
                status = subprocess.run([str(BIN/'pg_ctl'), '-D', str(data), 'status'],
                                        env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
                running = status.returncode == 0
            with psycopg.connect(**config) as conn:
                settings = conn.execute("SELECT current_user,current_database(),current_setting('listen_addresses'),current_setting('data_directory'),current_setting('server_encoding')").fetchone()
                if settings != (ROLE, 'postgres', '', str(data), 'UTF8'):
                    raise RuntimeError('unexpected private PG identity/settings')
                record('PASS private PG identity/settings: ' + repr(settings))
                conn.execute((ROOT.parent/'memory'/'schema.sql').read_text())
                conn.execute((ROOT/'schema.sql').read_text())
                conn.execute("INSERT INTO cj_memory_scope(scope) VALUES ('A'),('B')")
            command([sys.executable, '-B', ROOT/'tests'/'checks.py', config_path])
            command([BIN/'pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop'])
            running = False
            try:
                start()
            finally:
                status = subprocess.run([str(BIN/'pg_ctl'), '-D', str(data), 'status'],
                                        env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
                running = status.returncode == 0
            command([sys.executable, '-B', ROOT/'tests'/'checks.py', config_path,
                     '--restart'])
            record('PASS checks and actual server restart')
        finally:
            if running:
                command([BIN/'pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop'])
            if data.exists():
                status = subprocess.run([str(BIN/'pg_ctl'), '-D', str(data), 'status'],
                                        env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
                record('final pg_ctl status=' + str(status.returncode))
                if status.returncode != 3:
                    raise RuntimeError('private PG shutdown not confirmed')
            if (data/'postmaster.pid').exists() or (socket/('.s.PGSQL.' + str(PORT))).exists():
                raise RuntimeError('private PG PID/socket still present')
            record('PASS safe stop: no running server/PID/socket; data/logs preserved')
        record('evidence=' + str(report_path))


if __name__ == '__main__':
    main()
