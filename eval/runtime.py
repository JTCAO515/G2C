"""Disposable local signed API/PG support. No external provider selection."""
from contextlib import contextmanager
from pathlib import Path
import json
import os
import sys
import tempfile
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'backend/agent/tests')]


@contextmanager
def private_database(name):
    import migrate
    import pg_suites
    import psycopg

    # Unique socket and directory: never an ambient DSN or another line's PG.
    with tempfile.TemporaryDirectory(prefix='g2c-eval-') as folder:
        root = Path(folder)
        with pg_suites.cluster(name, port=55971, role='cj_eval_initializer',
                              root=root / 'pg', socket=root / 's') as config:
            with psycopg.connect(**config, autocommit=True) as conn:
                migrations = migrate.load()
                migrate.up(conn, migrations, migrations[-1]['version'])
            path = root / 'conninfo.json'
            path.write_text(json.dumps(config))
            previous = os.environ.get('CJ_E2E_CONNINFO')
            os.environ['CJ_E2E_CONNINFO'] = str(path)
            try:
                yield path
            finally:
                if previous is None:
                    del os.environ['CJ_E2E_CONNINFO']
                else:
                    os.environ['CJ_E2E_CONNINFO'] = previous


@contextmanager
def harness(kind='Harness'):
    import e2e_local
    from importlib import reload

    e2e_local = reload(e2e_local)  # binds this experiment's fresh PG, no stale DSN
    cls = getattr(e2e_local, kind)
    cls.setUpClass()
    try:
        yield cls()
    finally:
        cls.tearDownClass()


def implementation_probe(relative_path):
    """Run an existing real fault program, retaining its full assertion output."""
    import pg_suites

    path = ROOT / relative_path
    result = subprocess.run([sys.executable, '-B', str(path)], cwd=path.parent,
                            env=dict(pg_suites.clean_env(),
                                     PYTHONPATH=pg_suites.pythonpath(path.parent)),
                            text=True, capture_output=True, timeout=180)
    observed = dict(program=relative_path, exit_code=result.returncode,
                    stdout=result.stdout, stderr=result.stderr)
    if result.returncode:
        raise AssertionError(json.dumps(observed, ensure_ascii=False))
    return observed
