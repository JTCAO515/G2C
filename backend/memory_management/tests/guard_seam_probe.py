"""Probe only public MEMORY entrypoints; no DB, private state or AUTH clone.

PASS means the missing lifecycle extension has been reproduced, not that guarded
CJ019 behavior is implemented. Original 14 real-PG checks are not re-run here.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent/'memory'), str(ROOT.parent/'auth')]
from cj_auth.interfaces import TrustedPrincipal
from cj_memory.domain import InvalidInput, Service as MemoryService
from cj_memory_management.domain import Action


class NoDatabase:
    scope = 'cj019-probe-only'

    def transaction(self):
        raise AssertionError('probe must never reach a database transaction')


def main():
    principal = TrustedPrincipal('synthetic-issuer', 'synthetic-subject',
                                 'synthetic-audience', 1, 1, 9999999999)
    def guard(stage):
        return principal, 'cj019-probe-only'
    service = MemoryService(NoDatabase())
    raw = json.dumps(dict(action_id='pause-probe', operation='pause',
                          item_id='probe-item', expected_version=1,
                          expected_source_version=1)).encode()
    assert Action.parse(raw).operation == 'pause'
    checked = []
    def inspect_public_context(ctx):
        for method in ('apply', 'pause', 'resume', 'query_action', 'apply_lifecycle',
                       'query_lifecycle'):
            assert not hasattr(ctx, method), 'producer seam changed; re-evaluate'
        for method in ('save', 'save_manual'):
            try:
                getattr(ctx, method)(raw)
            except InvalidInput:
                checked.append(method)
            else:
                raise AssertionError('lifecycle unexpectedly accepted as a save')
        return b'{"probe":"public-seam-gap"}'
    result = service.with_operation(guard, inspect_public_context)
    assert result == b'{"probe":"public-seam-gap"}'
    assert checked == ['save', 'save_manual']
    print('PASS probe: valid CJ019 action; original save/save_manual reject its shape before DB')
    print('PASS probe: public context exposes no lifecycle apply/query extension')
    print('PASS probe: original with_operation callback completes using existing TrustedPrincipal')
    print('BLOCKED seam: guarded lifecycle write/receipt reconciliation not exposed by producer')
    print('UNRUN guarded pause/resume/query, precommit/postcommit/close/final identity cases')
    print('No database, private context fields, new AUTH policy, install, network or PG rerun')


if __name__ == '__main__':
    main()
