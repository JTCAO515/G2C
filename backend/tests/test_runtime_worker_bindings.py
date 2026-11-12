"""Worker startup isolation controls; controlled AUTH, no model/fee calls."""
from types import SimpleNamespace

import pytest

from cj_agent.provider import DashScopeConfig,M4_BASE,M4_MODEL,M4_REAL_OUTPUT_TOKENS
from cj_api.local_app import ISSUER,scope_for
from cj_api.runtime_text_slots import source_c0_national_v2
from cj_api.runtime_worker_bindings import RuntimeWorkerBindings
from cj_auth.interfaces import AdmissionStatus
from cj_run.core import Binding
from cj_usage.metered_exit import BudgetUnknown
from runtime_adapter.configuration import ROOT
from runtime_adapter.contract import encode


def test_expired_runtime_identity_closes_only_its_runtime_ids_not_ordinary_traffic(tmp_path,monkeypatch):
    subject='m4-synthetic-demo-0123456789ab';scope=scope_for(ISSUER,subject)
    token=tmp_path/'identity.jwt';token.write_text('fixture-only');token.chmod(0o600)
    def forbidden(*args,**kwargs):raise AssertionError('no budget/dispatch for denied original identity')
    budget=SimpleNamespace(ledger_id='original-ledger',producer='original-producer',connect=forbidden)
    provider=SimpleNamespace(config=DashScopeConfig(M4_BASE,M4_MODEL,'fixture-only',max_output_tokens=M4_REAL_OUTPUT_TOKENS),authorization=budget)
    checker=SimpleNamespace(check=lambda token:SimpleNamespace(status=AdmissionStatus.DENIED))
    monkeypatch.setattr('cj_api.runtime_worker_bindings.account_checker_for',lambda *args,**kwargs:checker)
    directory=tmp_path/'retained';directory.mkdir(mode=0o700);info=directory.stat()
    pinned=dict(path=str(directory),device=info.st_dev,inode=info.st_ino)
    manifest=tmp_path/'manifest.json'
    manifest.write_bytes(encode(dict(version='G2C-runtime-host.1',baseline='national.2',resource_root=str(ROOT),
        runtime_card=dict(code_sha='a'*40,image_digest='sha256:'+'b'*64,model=source_c0_national_v2()['model']),
        evidence_manifest=str(tmp_path/'evidence.json'),lines=[dict(line='E',subject=subject,token_file=str(token),
            canonical_directory=pinned,references_directory=pinned,mapping_directory=pinned)])))
    manifest.chmod(0o600)
    original={'original-registry':object()}
    tools=SimpleNamespace(registrations=original)
    runtime=SimpleNamespace(auth=tmp_path,database=lambda:object(),demo_subjects=frozenset({subject}))
    bindings=RuntimeWorkerBindings(manifest,runtime,SimpleNamespace(model=provider),tools,confirmation_signer=None)
    assert not bindings.by_scope and bindings.inactive_scopes=={scope:'ORIGINAL_AUTH_UNAVAILABLE'}
    denied=Binding(scope,'chat','generation','runtime-'+'a'*64,'run',1)
    assert bindings.registrations(denied)=={} and not bindings.selects(denied)
    with pytest.raises(BudgetUnknown):bindings.reflection(denied)
    ordinary=Binding(scope,'chat','generation','ordinary-id','run',1)
    assert bindings.registrations(ordinary) is original and bindings.reflection(ordinary) is None
    other=Binding(scope_for(ISSUER,'other-owner'),'chat','generation','runtime-'+'a'*64,'run',1)
    assert bindings.registrations(other) is original and bindings.reflection(other) is None
