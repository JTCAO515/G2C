"""Host worker for CJ_ENV=local: MESSAGE pending deliveries -> model -> RUN events (P2a).

  run_worker.py --conninfo-json conn.json [--once] [--real]

Without --real the deterministic FakeProvider answers (no network, no cost). With
--real, CJ_MODEL_API_BASE_URL and CJ_MODEL_ID must be set and the key is read from
CJ_MODEL_API_KEY or, if absent, the macOS Keychain item `g2c-dashscope`; the key is
never printed. A run interrupted mid-answer becomes `unknown` and is not resent.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

if os.environ.get('CJ_ENV') != 'local':
    raise SystemExit('CJ_ENV=local is required')

from cj_agent.draft import DraftPublisher
from cj_agent.provider import DashScopeConfig, DashScopeProvider, FakeProvider, ProviderFailed
from cj_agent.worker import RunWorker, original_context_valid
from cj_api.local_app import LocalDatabase, ISSUER, scope_for
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import LocalBudgetRouter, checker_for, needs_lease_for
from cj_auth.interfaces import AdmissionStatus
from cj_needs.revision_lease import LeaseUnavailable
import dev_auth
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


def invited_subjects(auth_dir):
    subjects = json.loads((Path(auth_dir) / 'invited.json').read_text())
    if type(subjects) is not list or any(type(s) is not str or not s.strip() for s in subjects):
        raise ValueError('explicit local invitation list required')
    return set(subjects)


def scopes(database, auth_dir):
    # Enumerate only the operator-owned invitation source, never all tenants via
    # an initialization/superuser connection. Each query has its own scoped role.
    result = []
    for subject in sorted(invited_subjects(auth_dir)):
        scope = scope_for(ISSUER, subject)
        with database.connect(scope) as conn:
            if conn.execute('SELECT 1 FROM cj_message_delivery WHERE NOT acknowledged LIMIT 1').fetchone():
                result.append(scope)
    return result


class InvitedProvider:
    def __init__(self, model, auth_dir, subject):
        self.model, self.auth_dir, self.subject = model, auth_dir, subject

    def stream(self, *args, **kwargs):
        # Repeat at each model outflow, including structured-draft generation.
        # A failed/unknown invitation read raises before calling the provider.
        if self.subject not in invited_subjects(self.auth_dir):
            raise ProviderFailed('local invitation denied before dispatch')
        yield from self.model.stream(*args, **kwargs)


def run_once(database, model, auth_dir):
    if database.run_context is not None and not isinstance(model,FakeProvider):
        raise ProviderFailed('configured local context permits only FakeProvider')
    checker=checker_for(Path(auth_dir)) if database.run_context is not None else None
    results = []
    for scope in scopes(database, auth_dir):
        messages = MessageService(database.message_repository(scope), new_run_id=lambda: None)
        subject = scope.removeprefix('local:' + ISSUER + ':')
        def token(subject=subject): return dev_auth.token(Path(auth_dir),subject,5)
        def valid(binding, messages=messages, subject=subject, token=token):
            if checker is None:
                return original_context_valid(binding,messages,lambda:subject in invited_subjects(auth_dir))
            credential=token()
            first=checker.check(credential)
            if first.status is AdmissionStatus.UNKNOWN: raise LeaseUnavailable('worker admission unknown')
            if first.status is not AdmissionStatus.ALLOWED: return False
            if scope_for(first.principal.issuer,first.principal.subject)!=binding.scope: return False
            original=original_context_valid(binding,messages,lambda:True)
            last=checker.check(credential)
            if last.status is AdmissionStatus.UNKNOWN: raise LeaseUnavailable('worker admission unknown')
            return original is True and last.status is AdmissionStatus.ALLOWED and last.principal==first.principal
        runs = RunService(database.run_repository(scope),valid=valid)
        drafts = DraftPublisher(database.trip_repository(scope))
        guarded_model = InvitedProvider(model, auth_dir, subject) if checker is None else model
        results += RunWorker(scope=scope, messages=messages, runs=runs, provider=guarded_model, drafts=drafts,
            needs_lease=needs_lease_for(database,checker,token) if checker is not None else None,
            budget_exit=LocalBudgetRouter(database) if checker is not None else None).process()
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--conninfo-json', type=Path, required=True)
    parser.add_argument('--auth-dir', type=Path, default=os.environ.get('CJ_LOCAL_AUTH_DIR'))
    parser.add_argument('--run-context', type=Path, default=os.environ.get('CJ_LOCAL_RUN_CONTEXT'))
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--real', action='store_true')
    parser.add_argument('--interval', type=float, default=0.5)
    args = parser.parse_args()
    if args.auth_dir is None:
        parser.error('--auth-dir or CJ_LOCAL_AUTH_DIR is required for local invitations')
    if args.run_context is not None and args.real:
        parser.error('local run context permits FakeProvider only; --real is unavailable')
    context=load_run_context(args.run_context) if args.run_context is not None else None
    database, model = LocalDatabase(args.conninfo_json,run_context=context), provider(args.real)
    while True:
        for outcome in run_once(database, model, args.auth_dir):
            print(f'{outcome.status} message={outcome.message_id}'
                  + (f' proposal={outcome.proposal_id}' if outcome.proposal_id else ''), flush=True)
        if args.once:
            if context is not None: print(f'local_provider_calls={model.calls}',flush=True)
            return
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
