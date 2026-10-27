"""Host worker for CJ_ENV=local: MESSAGE pending deliveries -> model -> RUN events (P2a).

  run_worker.py --conninfo-json conn.json [--once] [--real]

Without --real the deterministic FakeProvider answers (no network, no cost). With
--real, CJ_MODEL_API_BASE_URL and CJ_MODEL_ID must be set and the key is read from
CJ_MODEL_API_KEY or, if absent, the macOS Keychain item `g2c-dashscope`; the key is
never printed. A run interrupted mid-answer becomes `unknown` and is not resent.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

if os.environ.get('CJ_ENV') != 'local':
    raise SystemExit('CJ_ENV=local is required')

import psycopg
from cj_agent.provider import DashScopeConfig, DashScopeProvider, FakeProvider
from cj_agent.worker import RunWorker
from cj_api.local_app import LocalDatabase
from cj_message.domain import Service as MessageService
from cj_run.core import Service as RunService


def provider(real):
    if not real:
        return FakeProvider()
    environ = dict(os.environ)
    if not environ.get('CJ_MODEL_API_KEY') and sys.platform == 'darwin':
        result = subprocess.run(['security', 'find-generic-password', '-s', 'g2c-dashscope', '-w'],
                                capture_output=True, text=True)
        if result.returncode == 0:
            environ['CJ_MODEL_API_KEY'] = result.stdout.strip()
    return DashScopeProvider(DashScopeConfig.from_environment(environ))


def scopes(database):
    with psycopg.connect(**database.conninfo) as conn:
        return [row[0] for row in conn.execute(
            'SELECT DISTINCT scope FROM cj_message_delivery WHERE NOT acknowledged ORDER BY scope')]


def run_once(database, model):
    results = []
    for scope in scopes(database):
        messages = MessageService(database.message_repository(scope), new_run_id=lambda: None)
        runs = RunService(database.run_repository(scope),
                          valid=lambda binding, m=messages: m.query(binding.message_id) is not None)
        results += RunWorker(scope=scope, messages=messages, runs=runs, provider=model).process()
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--conninfo-json', type=Path, required=True)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--real', action='store_true')
    parser.add_argument('--interval', type=float, default=0.5)
    args = parser.parse_args()
    database, model = LocalDatabase(args.conninfo_json), provider(args.real)
    while True:
        for outcome in run_once(database, model):
            print(f'{outcome.status} message={outcome.message_id}', flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
