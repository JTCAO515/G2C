"""Public resource relocation; no credentials, model, fees or live admission."""
import shutil

import pytest

from runtime_adapter.configuration import ROOT,source_c0,freeze_pins
from runtime_adapter.contract import Invalid


def bundle(tmp_path):
    source=source_c0();root=tmp_path/'public'
    for name in source['source_hashes']:
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
    return root


def test_default_explicit_repo_and_relocated_public_resources_are_identical(tmp_path):
    expected=source_c0();root=bundle(tmp_path)
    assert source_c0(resource_root=ROOT)==expected
    assert source_c0(resource_root=root)==expected
    observed=dict(code_sha='a'*40,image_digest='sha256:'+'b'*64,model=expected['model'])
    assert freeze_pins(observed,resource_root=root).raw==freeze_pins(observed).raw
    assert freeze_pins(observed,resource_root=root).c0()['runtime_eligible'] is False


def test_missing_public_dataset_never_falls_back_to_repo(tmp_path):
    root=bundle(tmp_path);(root/'eval/optimization/cases.v2.json').unlink()
    with pytest.raises(FileNotFoundError):source_c0(resource_root=root)


def test_policy_bundle_must_match_actual_imported_source(tmp_path):
    root=bundle(tmp_path);path=root/'backend/cj_api/real_services.py'
    path.write_bytes(path.read_bytes()+b'\n# another build\n')
    with pytest.raises(Invalid,match='PUBLIC_POLICY_BUNDLE_SOURCE_MISMATCH'):
        source_c0(resource_root=root)
