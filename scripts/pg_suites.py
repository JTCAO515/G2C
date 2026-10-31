"""Run PostgreSQL-backed suites against new private Unix-socket clusters (ADR-0004).

Each group gets a fresh cluster under .local/pg-suites/<group> (git-ignored), applies
working-tree SQL only, runs its suite, then stops the cluster. No TCP listener, no
ambient DSN, no existing instance. Replaces the pin-era per-feature harnesses.

Usage: uv run --no-sync python -B scripts/pg_suites.py [GROUP ...]
PostgreSQL binaries: CJ_PG_BINDIR, else `pg_config --bindir`.
"""
import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.local/pg-suites'
BACKEND = ROOT / 'backend'


def bindir():
    explicit = os.environ.get('CJ_PG_BINDIR')
    if explicit:
        return Path(explicit)
    return Path(subprocess.check_output(['pg_config', '--bindir'], text=True).strip())


def clean_env():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('PG', 'LIBPQ')) and k not in ('DATABASE_URL', 'CJ_DATABASE_URL')}
    env.update(LANG='C', LC_ALL='C', CJ_ENV='local', PYTHONDONTWRITEBYTECODE='1')
    return env


def pythonpath(*extra):
    domains = sorted(str(p) for p in BACKEND.iterdir() if p.is_dir())
    return os.pathsep.join([*map(str, extra), str(BACKEND), *domains])


@contextlib.contextmanager
def cluster(name, *, port, role, socket=None, pg=None, restart=None, root=None):
    root = Path(root) if root else WORK / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    socket = Path(socket) if socket else root / 's'
    if socket.exists():
        shutil.rmtree(socket)
    socket.mkdir(parents=True, mode=0o700)
    if len(str(socket / f'.s.PGSQL.{port}').encode()) >= 104:
        raise SystemExit(f'socket path too long for {name}; use a shorter checkout path')
    passfile = root / 'empty.pgpass'
    passfile.touch(mode=0o600)
    data, pg, env = root / 'data', pg or bindir(), clean_env()
    def run(*argv):
        subprocess.run([str(pg / argv[0]), *map(str, argv[1:])], env=env, check=True,
                       stdout=subprocess.DEVNULL)
    run('initdb', '-D', data, f'--username={role}', '--auth-local=trust', '--auth-host=reject',
        '--encoding=UTF8', '--locale=C')
    options = f"-c listen_addresses='' -k {socket} -p {port} -c unix_socket_permissions=0700"
    run('pg_ctl', '-D', data, '-l', root / 'postgres.log', '-o', options, '-w', 'start')
    if restart is not None:
        restart.append(lambda: (run('pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop'),
                                run('pg_ctl', '-D', data, '-l', root / 'postgres.log', '-o', options, '-w', 'start')))
    config = dict(host=str(socket), port=port, user=role, dbname='postgres', passfile=str(passfile),
                  connect_timeout=5, options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
    try:
        yield config
    finally:
        run('pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop')


def apply_sql(config, *paths, dbname=None):
    import psycopg
    with psycopg.connect(**dict(config, dbname=dbname or config['dbname'])) as c:
        for path in paths:
            c.execute((ROOT / path).read_text())


def script(path, *args, env=None):
    path = ROOT / path
    env = dict(env or clean_env(), PYTHONPATH=pythonpath(path.parent))
    return subprocess.run([sys.executable, '-B', path.name, *map(str, args)], cwd=path.parent, env=env).returncode


def site_packages():
    import psycopg
    return Path(psycopg.__file__).resolve().parents[1]


def fresh(*paths):
    for path in paths:
        path = BACKEND / path
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.exists():
            shutil.rmtree(path)


def pytest(path, env):
    return subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests'],
                          cwd=ROOT / path, env=env).returncode


def unittest_class(module_class, env):
    return subprocess.run([sys.executable, '-B', '-m', 'unittest', '-v', module_class],
                          cwd=BACKEND / 'cj_api/tests', env=env).returncode


def group_trip():
    with cluster('trip', port=55435, role='cj015_private') as config:
        import psycopg
        with psycopg.connect(**config, autocommit=True) as c:
            c.execute("CREATE DATABASE cj015_test ENCODING 'UTF8' TEMPLATE template0")
        apply_sql(config, 'backend/trip/sql/candidate.sql', dbname='cj015_test')
        nopass = BACKEND / 'trip/private-pg/no-password-file'
        nopass.parent.mkdir(exist_ok=True)
        nopass.touch(mode=0o600)
        env = dict(clean_env(), TRIP_TEST_SOCKET=config['host'],
                   PYTHONPATH=pythonpath(BACKEND / 'trip'))
        return pytest('backend/trip', env)


def _config_group(name, port, role, env_name, sql, checks):
    with cluster(name, port=port, role=role) as config:
        apply_sql(config, *sql)
        path = WORK / name / 'test-config.json'
        path.write_text(json.dumps(config))
        env = dict(clean_env(), **{env_name: str(path)},
                   PYTHONPATH=pythonpath(BACKEND / 'cj_api/tests'))
        return max(unittest_class(check, env) for check in checks)


def group_feasibility():
    return _config_group('feas', 55461, 'cj005feas', 'CJ005_FEASIBILITY_PG_CONFIG',
                         ['backend/needs/sql/candidate.sql'],
                         ['feasibility_wire_checks.FeasibilityChecks', 'needs_cohost_checks.NeedsCohostChecks'])


def group_memory_management():
    return _config_group('mm', 55462, 'cj005mm', 'CJ005_MANAGEMENT_PG_CONFIG',
                         ['backend/memory/schema.sql', 'backend/memory_management/schema.sql'],
                         ['memory_management_wire_checks.ManagementWireChecks', 'memory_cohost_checks.CohostChecks'])


def group_memory():
    # Fixed sockets/roles are part of these check modules; each gets its own cluster.
    fresh('memory/.local')
    local = BACKEND / 'memory/.local'
    local.mkdir()
    (local / 'empty.pgpass').touch(mode=0o600)
    status = 0
    with cluster('memory', port=56111, role='cj011_owner', socket='/tmp/cj011-memory-01a16218'):
        env = dict(clean_env(), PYTHONPATH=pythonpath(BACKEND / 'memory/tests'))
        status |= script('backend/memory/tests/pg_checks.py', '--setup', env=env)
    # additional_checks.py only re-runs pg_checks test_10/test_11, already covered above.
    for name, port in (('guard', 56112), ('list', 56113), ('manual', 56114), ('cancel', 56115)):
        (local / name).mkdir()  # each check module creates its own passfile
        module = {'cancel': 'cancellation_receipt_checks'}.get(name, name + '_checks')
        with cluster('memory-' + name, port=port, role='cj011_' + name,
                     socket=f'/tmp/cj011-{name}-01a16218'):
            status |= script(f'backend/memory/tests/{module}.py')
    status |= script('backend/memory/tests/consume_current_checks.py')
    status |= script('backend/memory/tests/lifecycle_seam_checks.py')
    return status


def group_domain_runners():
    # Self-provisioning private-cluster runners owned by each domain.
    pg, driver = bindir(), site_packages()
    fresh('cleanup/.local', 'feedback/.local', 'memory_management/.local')
    status = 0
    status |= script('backend/cleanup/tests/private_pg.py', '--pg-bin', pg, '--driver', driver)
    status |= script('backend/cleanup/tests/private_close_pg.py', '--pg-bin', pg, '--driver', driver)
    status |= script('backend/cleanup/tests/private_progress_pg.py', '--pg-bin', pg, '--driver', driver,
                     '--auth-root', BACKEND / 'auth')
    status |= script('backend/feedback/tests/private_pg.py', '--pg-bin', pg)
    env = dict(clean_env(), CJ_PG16_BINDIR=str(pg), CJ_PG17_BINDIR=str(pg))
    status |= script('backend/memory_management/tests/run_private_pg.py', env=env)
    status |= script('backend/memory_management/tests/run_guarded_pg.py', env=env)
    status |= script('backend/usage/tests/pg_probe.py', env=env)
    status |= script('backend/usage/tests/pg_read_probe.py', env=env)
    return status


def group_run():
    # RUN checks connect as the OS user on the default port and expect PostgreSQL 16.
    import getpass
    pg16 = Path(os.environ.get('CJ_PG16_BINDIR', bindir()))
    fresh('run/.local')
    status = 0
    for socket, checks, after_restart in (
            ('run/.local/socket', 'pg_checks.py', 'pg_restart_read.py'),
            ('run/.local/binding/socket', 'pg_binding_checks.py', 'pg_binding_restart.py')):
        restart = []
        with cluster('run-' + checks[:-3], port=5432, role=getpass.getuser(), socket=BACKEND / socket,
                     pg=pg16, restart=restart):
            status |= script(f'backend/run/tests/{checks}')
            restart[0]()  # real server restart before the recovery read
            status |= script(f'backend/run/tests/{after_restart}')
    return status


def group_message():
    # MESSAGE checks pin their data directory under backend/message/.local-pg-0N.
    status = 0
    for private, port, checks in (('.local-pg-01', 55439, 'check_postgres.py'),
                                  ('.local-pg-02', 55440, 'check_history_postgres.py')):
        restart = []
        with cluster('message-' + private, port=port, role='cj009', root=BACKEND / 'message' / private,
                     restart=restart):
            status |= script(f'backend/message/tests/{checks}', 'setup')
            status |= script(f'backend/message/tests/{checks}')
            if checks == 'check_history_postgres.py':
                status |= subprocess.run([sys.executable, '-B', '-m', 'unittest', '-v', 'history_gate_tests'],
                                         cwd=BACKEND / 'message/tests', env=clean_env()).returncode
            restart[0]()
            status |= script(f'backend/message/tests/{checks}', 'restart-check')
    return status


def group_migrations():
    return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/migrate.py'), 'verify'], env=clean_env()).returncode


def group_feasibility_domain():
    # test_current_read provisions its own private cluster from CJ_PG17_BINDIR.
    return pytest('backend/feasibility', dict(clean_env(), CJ_PG17_BINDIR=str(bindir())))


def group_e2e():
    # P2a end to end: fresh cluster, migrations 1-10, local app, worker, SSE (FakeProvider).
    sys.path.insert(0, str(ROOT / 'scripts'))
    import migrate
    import psycopg
    with cluster('e2e', port=55480, role='cj_e2e') as config:
        with psycopg.connect(**config, autocommit=True) as conn:
            migrate.up(conn, migrate.load(), migrate.load()[-1]['version'])
        path = WORK / 'e2e' / 'conninfo.json'
        path.write_text(json.dumps(config))
        env = dict(clean_env(), CJ_E2E_CONNINFO=str(path))
        return subprocess.run([sys.executable, '-B', 'e2e_local.py'], cwd=BACKEND / 'agent/tests', env=env).returncode


def group_needs():
    # conftest provisions its own private cluster from CJ_PG17_BINDIR.
    fresh('needs/.local')
    return pytest('backend/needs', dict(clean_env(), CJ_PG17_BINDIR=str(bindir())))


def group_local_context_schema():
    # #170: real private PG permissions and revision-fence protocol, not host activation.
    return script('backend/cj_api/tests/local_context_schema_pg.py')


def group_local_needs_fence():
    # #170 module L1: canonical admission + runtime PG; formal host activates in PR4.
    return script('backend/cj_api/tests/local_needs_fence_pg.py')


def group_local_budget_exit():
    # #170 local quota module L1; formal host activates in PR4.
    return script('backend/cj_api/tests/local_budget_exit_pg.py')


def group_local_protection_schema():
    # #170 durable local protection schema/upgrade, not host activation.
    return script('backend/cj_api/tests/local_protection_schema_pg.py')


def group_local_run_host():
    # #170 formal local factory, operator CLI and worker on real runtime PG.
    return script('backend/cj_api/tests/local_run_host_pg.py')


def group_registered_usage_schema():
    # #242 schema/RLS/old-consumer contract checks; business execution stays UNRUN.
    return script('backend/cj_api/tests/registered_usage_schema_pg.py')


def group_registered_exit():
    # #242 formal @2 model host and three-kind registered infrastructure.
    return script('backend/cj_api/tests/registered_exit_pg.py')


def group_memory_run():
    # #227: actual signed API/worker on the restricted runtime role, never --real.
    sys.path.insert(0, str(ROOT / 'scripts'))
    import migrate
    import psycopg
    with cluster('memory_run', port=55489, role='cj227_private',
                 socket=f'/tmp/cj227-runtime-{os.getpid()}') as config:
        with psycopg.connect(**config, autocommit=True) as conn:
            migrate.up(conn, migrate.load(), migrate.load()[-1]['version'])
        path = WORK / 'memory_run/conninfo.json'
        path.write_text(json.dumps(config))
        return script('backend/memory/tests/runtime_host_pg.py',
                      env=dict(clean_env(), CJ_E2E_CONNINFO=str(path),
                               PYTHONPATH=pythonpath(BACKEND / 'agent/tests', ROOT / 'scripts')))


def group_travel_context():
    return script('backend/cj_api/tests/travel_context_pg.py')


def group_trip_message():
    return script('backend/cj_api/tests/trip_message_pg.py')


def group_travel_message():
    return script('backend/cj_api/tests/travel_message_pg.py')


def group_place_tool():
    return script('backend/cj_api/tests/place_tool_pg.py')


def _fresh_runtime_check(name, port, role, socket, check):
    # Shared test setup only; every check gets its own restricted fresh PG.
    sys.path.insert(0,str(ROOT/'scripts'))
    import migrate
    import psycopg
    with cluster(name,port=port,role=role,socket=socket) as config:
        with psycopg.connect(**config,autocommit=True) as conn:
            migrate.up(conn,migrate.load(),migrate.load()[-1]['version'])
        path=WORK/name/'conninfo.json';path.write_text(json.dumps(config))
        return script(check,env=dict(clean_env(),CJ_E2E_CONNINFO=str(path)))


def group_memory_typed():
    # #227: genuine B leases, signed typed API, runtime-role PG and actual worker/CLI.
    return _fresh_runtime_check('memory_typed',55496,'cj227_typed',
        f'/tmp/cj227-typed-{os.getpid()}','backend/memory/tests/typed_pg.py')


def group_trip_manual():
    # #285: canonical AUTH, restricted PG, sole Proposal/confirmation/act path.
    return _fresh_runtime_check('trip_manual',55487,'cj285_manual',
        f'/tmp/cj285-manual-{os.getpid()}','backend/trip/tests/manual_pg.py')


def group_fact_tool():
    return script('backend/cj_api/tests/fact_tool_pg.py')


def group_needs_runtime():
    return script('backend/cj_api/tests/needs_runtime_pg.py')


def group_feasibility_runtime():
    return _fresh_runtime_check('feasibility_runtime',55498,'cj281_runtime',
        f'/tmp/cj281-runtime-{os.getpid()}','backend/feasibility/tests/runtime_pg.py')


def group_needs_trip():
    return _fresh_runtime_check('needs_trip',55499,'cj204_source',
        f'/tmp/cj204-source-{os.getpid()}','backend/draft/tests/needs_runtime_pg.py')


def group_needs_actions():
    return _fresh_runtime_check('needs_actions',55500,'cj285_needs',
        f'/tmp/cj285-needs-{os.getpid()}','backend/trip/tests/needs_actions_pg.py')


GROUPS = {'e2e': group_e2e, 'migrations': group_migrations, 'feasibility_domain': group_feasibility_domain, 'message': group_message, 'run': group_run, 'needs': group_needs, 'trip': group_trip, 'feasibility': group_feasibility, 'memory_management': group_memory_management,
          'memory': group_memory, 'domain_runners': group_domain_runners,
          'local_context_schema': group_local_context_schema, 'local_needs_fence': group_local_needs_fence, 'local_budget_exit': group_local_budget_exit, 'local_protection_schema': group_local_protection_schema, 'local_run_host': group_local_run_host, 'registered_usage_schema': group_registered_usage_schema, 'registered_exit': group_registered_exit, 'memory_run': group_memory_run, 'travel_context': group_travel_context, 'travel_message': group_travel_message, 'trip_message': group_trip_message, 'place_tool': group_place_tool,'memory_typed': group_memory_typed,'trip_manual': group_trip_manual,'fact_tool': group_fact_tool,'needs_runtime': group_needs_runtime,'feasibility_runtime': group_feasibility_runtime,'needs_trip': group_needs_trip,'needs_actions': group_needs_actions}


def main(argv):
    names = argv or list(GROUPS)
    results = {}
    for name in names:
        print(f'::group::pg suite {name}', flush=True)
        try:
            results[name] = GROUPS[name]()
        except Exception as error:  # report and continue with remaining groups
            print(f'::error::pg suite {name}: {type(error).__name__}: {error}', flush=True)
            results[name] = 1
        print('::endgroup::', flush=True)
    print(json.dumps(results))
    return 1 if any(results.values()) else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
