#!/usr/bin/env python3
"""Validate pinned initialization inputs; optionally inspect a private target read-only.

This is an admission check, not an apply command. It never executes artifact SQL.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'backend/migrations/initialization-plan.json'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL)


def validate_sources(repo, plan):
    if plan['apply_enabled'] is not False or plan['apply_order'] is not None:
        raise ValueError('unsupported apply-enabled plan')
    if len({a['id'] for a in plan['artifacts']}) != len(plan['artifacts']):
        raise ValueError('duplicate artifact')
    for item in plan['artifacts']:
        revision, path = item['artifact_revision'], item['path']
        if not re.fullmatch('[0-9a-f]{40}', revision):
            raise ValueError('non-fixed artifact revision')
        subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', revision,
                        plan['accepted_tree']], check=True, capture_output=True)
        raw = git(repo, 'show', f'{revision}:{path}')
        if raw != git(repo, 'show', f"{plan['accepted_tree']}:{path}"):
            raise ValueError('artifact differs from accepted tree')
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('artifact hash mismatch')
        tables = re.findall(r'CREATE TABLE\s+([\w.]+)', raw.decode(), re.I)
        refs = re.findall(r'REFERENCES\s+([\w.]+)', raw.decode(), re.I)
        if tables != item['tables'] or refs != item['intra_file_references']:
            raise ValueError('SQL inventory mismatch')
        # Inventory only: no inference of execution order or privilege correctness.
        if set(refs) - set(tables) or item['sql_requires_artifact']:
            raise ValueError('external SQL dependency requires owner review')
    foundation = plan['artifacts'][0]
    manifest = json.loads(git(repo, 'show', f"{plan['accepted_tree']}:backend/migrations/manifest.json"))
    if manifest['migrations'][0]['sha256'] != foundation['sha256']:
        raise ValueError('foundation manifest mismatch')


def classify(snapshot):
    if snapshot['initialized']:
        raise ValueError('ALREADY_INITIALIZED: repeated target refused')
    if snapshot['objects']:
        raise ValueError('NONEMPTY_TARGET: user objects refused')


def inspect_target(args):
    if any(k.startswith('PG') or k in ('DATABASE_URL', 'CJ_DATABASE_URL') for k in os.environ):
        raise ValueError('inherited PostgreSQL configuration refused')
    if not all((args.target_root, args.pg_bin, args.user, args.port)):
        raise ValueError('explicit target-root, pg-bin, user and port required')
    root = Path(args.target_root).absolute()
    if root.parent != ROOT or not re.fullmatch(r'\.local-cj005-init-[a-z0-9-]+', root.name):
        raise ValueError('target must be an explicit task-private initialization directory')
    for path in (root, root / 'data', root / 's'):
        if path.is_symlink() or not path.is_dir() or path.resolve() != path:
            raise ValueError('missing or symlinked target path refused')
    psql = Path(args.pg_bin) / 'psql'
    # Clean subprocess environment; no URI, network host, service file or password fallback.
    env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'PGOPTIONS':
           '-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000 -c search_path=pg_catalog',
           'PGPASSFILE': '/dev/null', 'PGSERVICEFILE': '/dev/null', 'PSQLRC': '/dev/null'}
    query = """
SELECT json_build_object(
 'data',current_setting('data_directory'),
 'listen',current_setting('listen_addresses'),
 'socket',current_setting('unix_socket_directories'),
 'user',current_user,'database',current_database(),
 'readonly',current_setting('transaction_read_only'),
 'initialized',to_regclass('cj.schema_migrations') IS NOT NULL,
 'objects',EXISTS(SELECT 1 FROM pg_namespace WHERE nspname NOT IN
 ('public','information_schema') AND nspname !~ '^pg_')
 OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public')
 OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public')
 OR EXISTS(SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
 WHERE n.nspname='public')
 OR EXISTS(SELECT 1 FROM pg_extension WHERE extname <> 'plpgsql')
 OR EXISTS(SELECT 1 FROM pg_event_trigger));
"""
    result = subprocess.run([str(psql), '-X', '-w', '-A', '-t', '-v', 'ON_ERROR_STOP=1',
                             '-h', str(root / 's'), '-p', str(args.port), '-U', args.user,
                             '-d', 'postgres', '-c', query], env=env, capture_output=True,
                            text=True, check=True, timeout=10)
    state = json.loads(result.stdout)
    if (state['data'] != str(root / 'data') or state['socket'] != str(root / 's')
            or state['listen'] != '' or state['user'] != args.user
            or state['database'] != 'postgres' or state['readonly'] != 'on'):
        raise ValueError('target identity/private/read-only fence mismatch')
    classify(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-repo', required=True, type=Path)
    parser.add_argument('--inspect-target', action='store_true')
    parser.add_argument('--target-root')
    parser.add_argument('--pg-bin')
    parser.add_argument('--user')
    parser.add_argument('--port', type=int)
    args = parser.parse_args()
    try:
        plan = json.loads(PLAN.read_text())
        validate_sources(args.source_repo, plan)
        if args.inspect_target:
            inspect_target(args)
        elif any((args.target_root, args.pg_bin, args.user, args.port)):
            raise ValueError('target options require --inspect-target')
        print(json.dumps({'plan': plan['plan_revision'], 'source_validation': 'PASS',
                          'target_admission': 'PASS' if args.inspect_target else 'UNRUN',
                          'apply': 'BLOCKED', 'blockers': plan['apply_blockers']}, indent=2))
        return 0
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        # Never echo connection output, raw data or inherited configuration.
        print('FAIL: initialization input or target admission rejected; no SQL applied', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
