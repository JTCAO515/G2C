"""Apply or revert the registered migration chain (backend/migrations/manifest.json).

  migrate.py up      [--to N] --conninfo-json PATH   apply pending migrations in order
  migrate.py down    [--to N] --conninfo-json PATH   revert applied migrations down to N (default 0)
  migrate.py status           --conninfo-json PATH   print applied versions
  migrate.py verify                                  up -> down -> up on a fresh private cluster

Every file is checked against its manifest sha256 before use. Each step runs in one
transaction together with its ledger row in cj.schema_migrations. Connection parameters
come only from an explicit JSON file; ambient PG* variables are refused.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'backend/migrations/manifest.json'


def load():
    manifest = json.loads(MANIFEST.read_text())
    migrations = sorted(manifest['migrations'], key=lambda m: m['version'])
    versions = [m['version'] for m in migrations]
    if versions != list(range(1, len(versions) + 1)):
        raise SystemExit(f'manifest versions must be contiguous from 1: {versions}')
    for m in migrations:
        for key in ('file', 'down'):
            digest = hashlib.sha256((ROOT / m[key]).read_bytes()).hexdigest()
            if digest != m[key == 'file' and 'sha256' or 'down_sha256']:
                raise SystemExit(f'sha256 mismatch for {m[key]}; update the manifest deliberately')
    return migrations


def applied(conn):
    exists = conn.execute("SELECT to_regclass('cj.schema_migrations')").fetchone()[0]
    if exists is None:
        return []
    return [row[0] for row in conn.execute('SELECT version FROM cj.schema_migrations ORDER BY version')]


def up(conn, migrations, target):
    done = applied(conn)
    for m in migrations:
        if m['version'] in done or m['version'] > target:
            continue
        if done and m['version'] != max(done) + 1:
            raise SystemExit(f'gap before migration {m["version"]}; applied={done}')
        with conn.transaction():
            conn.execute((ROOT / m['file']).read_text())
            if m['version'] != 1:  # 0001 inserts its own ledger row
                conn.execute('INSERT INTO cj.schema_migrations(version) VALUES (%s)', (m['version'],))
        done.append(m['version'])
        print(f'up {m["version"]:04d} {m["name"]}', flush=True)


def down(conn, migrations, target):
    done = applied(conn)
    for m in reversed(migrations):
        if m['version'] not in done or m['version'] <= target:
            continue
        if m['version'] != max(done):
            raise SystemExit(f'cannot revert {m["version"]} before {max(done)}')
        with conn.transaction():
            conn.execute((ROOT / m['down']).read_text())
            if m['version'] != 1:
                conn.execute('DELETE FROM cj.schema_migrations WHERE version=%s', (m['version'],))
        done.remove(m['version'])
        print(f'down {m["version"]:04d} {m["name"]}', flush=True)


def inventory(conn):
    return sorted(row[0] for row in conn.execute(
        "SELECT schemaname||'.'||tablename FROM pg_tables WHERE schemaname IN ('public','cj')"))


def connect(path):
    import psycopg
    if any(k.startswith(('PG', 'LIBPQ')) for k in os.environ):
        raise SystemExit('ambient PG*/LIBPQ* configuration refused')
    return psycopg.connect(**json.loads(Path(path).read_text()), autocommit=True)


def verify(migrations):
    sys.path.insert(0, str(Path(__file__).parent))
    from pg_suites import cluster
    import psycopg
    top = migrations[-1]['version']
    with cluster('migrations', port=55470, role='cj_migrate') as config:
        with psycopg.connect(**config, autocommit=True) as conn:
            assert inventory(conn) == [], 'fresh cluster must be empty'
            up(conn, migrations, top)
            full = inventory(conn)
            assert applied(conn) == list(range(1, top + 1)), applied(conn)
            down(conn, migrations, 0)
            assert inventory(conn) == [], f'down left objects: {inventory(conn)}'
            up(conn, migrations, top)
            assert inventory(conn) == full, 'second up differs from first'
    print(f'PASS migrations 1..{top}: up, full down to empty, up again ({len(full)} tables)')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('up', 'down', 'status', 'verify'))
    parser.add_argument('--to', type=int)
    parser.add_argument('--conninfo-json')
    args = parser.parse_args()
    migrations = load()
    if args.command == 'verify':
        return verify(migrations)
    if not args.conninfo_json:
        raise SystemExit('--conninfo-json is required')
    with connect(args.conninfo_json) as conn:
        if args.command == 'up':
            up(conn, migrations, args.to or migrations[-1]['version'])
        elif args.command == 'down':
            down(conn, migrations, args.to or 0)
        print(json.dumps({'applied': applied(conn)}))


if __name__ == '__main__':
    main()
