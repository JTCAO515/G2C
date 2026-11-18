"""Controls around the production release driver carried into the repository."""

import pytest

from deploy.hk.application_release_host import require_source_abi, selectors


def test_host_accepts_current_and_rollback_abi_and_rejects_mixed_files():
    paths = ("original-billing", "original-data")
    previous = dict.fromkeys(paths, "a" * 64)
    candidate = dict.fromkeys(paths, "b" * 64)
    policy = dict(
        version="G2C-B-app-release-policy.2",
        required_source_hashes=previous,
        accepted_source_hash_sets=[previous, candidate],
    )
    require_source_abi(candidate, policy)
    require_source_abi(previous, policy)
    with pytest.raises(ValueError, match="outside reviewed source ABI"):
        require_source_abi(dict(previous, **{paths[0]: candidate[paths[0]]}), policy)


def test_host_selectors_keep_operator_image_distinct_and_immutable():
    raw = b"CJ_BETA_IMAGE=g2c-beta:app\nCJ_BETA_OPERATOR_IMAGE=g2c-beta-operator:operator\n"
    assert selectors(raw) == {
        "CJ_BETA_IMAGE": "g2c-beta:app",
        "CJ_BETA_OPERATOR_IMAGE": "g2c-beta-operator:operator",
    }
    with pytest.raises(ValueError, match="single canonical selector"):
        selectors(raw + b"CJ_BETA_IMAGE=g2c-beta:other\n")


def test_ingress_recovery_keeps_the_current_original_worker_running():
    from deploy.hk.application_release_host import recover_original_ingress

    commands = []
    worker = dict(
        Image="old-image",
        State={"Running": True},
        Config={
            "Cmd": ["worker"],
            "Labels": {
                "org.opencontainers.image.revision": "old-source",
            },
        },
    )
    compose = ["docker", "compose"]
    assert recover_original_ingress(
        commands.append, lambda name: worker, compose, "old-image", "old-source"
    )
    assert commands == [["docker", "compose", "up", "-d", "--no-deps", "api"]]


def test_incident_candidate_cannot_omit_either_original_fix_approval():
    from deploy.hk.application_release_host import (
        DOUBLE_FIX_SOURCE,
        verify_cutover_evidence,
    )

    def unexpected_lookup(path):
        pytest.fail(f"incomplete required PR set should fail before a lookup: {path}")

    for primary in (1170, 1174):
        with pytest.raises(ValueError, match="both incident-fix PR approvals"):
            verify_cutover_evidence(
                unexpected_lookup, DOUBLE_FIX_SOURCE, {"pr_number": primary}
            )
