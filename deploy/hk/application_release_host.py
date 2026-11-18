"""Production HK application cutover under the standing B release procedure."""

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import sys
import time
from urllib.request import Request, urlopen

if __package__:
    from .application_release import (
        REPOSITORY,
        require_release_window,
        verify_release_ci,
        verify_release_review,
    )
else:
    # The reviewed host bundle places the two files in the same private folder
    # and invokes the host driver with the existing script/gate interface.
    from application_release import (
        REPOSITORY,
        require_release_window,
        verify_release_ci,
        verify_release_review,
    )

ROOT = Path("/srv/g2c-beta")
GC_UNITS = Path("/etc/systemd/system")


def selectors(raw):
    if b"\r" in raw:
        raise ValueError("canonical LF selector required")
    result = {}
    for line in raw.decode().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch("(CJ_BETA_IMAGE|CJ_BETA_OPERATOR_IMAGE)=([^\\s]+)", line)
        if match is None or match[1] in result:
            raise ValueError("single canonical selector assignment required")
        result[match[1]] = match[2]
    if set(result) != {"CJ_BETA_IMAGE", "CJ_BETA_OPERATOR_IMAGE"}:
        raise ValueError("complete canonical selectors required")
    return result


def require_source_abi(actual, policy):
    if policy["version"] != "G2C-B-app-release-policy.2":
        raise ValueError("exact compatible ABI policy version required")
    accepted = policy["accepted_source_hash_sets"]
    baseline = policy["required_source_hashes"]
    if (
        type(accepted) is not list
        or len(accepted) != 2
        or accepted[0] != baseline
        or (accepted[0] == accepted[1])
        or any(
            (
                type(row) is not dict
                or set(row) != set(baseline)
                or any(
                    (
                        type(value) is not str
                        or re.fullmatch("[a-f0-9]{64}", value) is None
                        for value in row.values()
                    )
                )
                for row in accepted
            )
        )
    ):
        raise ValueError("exact complete reviewed source ABI sets required")
    if actual not in accepted:
        raise ValueError("image outside reviewed source ABI compatibility sets")


# Both fixes belong to the already-staged 7f8dbe96 incident recovery.
# Retire this fixed requirement with that candidate and its rollback window.
DOUBLE_FIX_SOURCE = "7f8dbe9617833a4af4900f21499a6db5616d5eb6"
DOUBLE_FIX_REVIEW_PRS = frozenset({1170, 1174})


def verify_cutover_evidence(github, source, gate):
    related_reviews = gate.get("related_reviews", [])
    if type(related_reviews) is not list:
        raise ValueError("explicit related review records required")
    pr_numbers = [gate["pr_number"], *(row["pr_number"] for row in related_reviews)]
    if len(set(pr_numbers)) != len(pr_numbers):
        raise ValueError("duplicate release PR approval")
    if source == DOUBLE_FIX_SOURCE and not DOUBLE_FIX_REVIEW_PRS <= set(pr_numbers):
        raise ValueError("both incident-fix PR approvals are required")
    verify_release_ci(github, source)
    verify_release_review(github, source, gate)
    for related in related_reviews:
        landed = related["source"]
        if re.fullmatch("[a-f0-9]{40}", landed) is None:
            raise ValueError("exact supporting PR merge source required")
        verify_release_review(github, landed, related)
        if github("compare/" + landed + "..." + source)["status"] not in (
            "identical",
            "ahead",
        ):
            raise ValueError("supporting R-reviewed change is absent from candidate")


def recover_original_ingress(
    command, inspect, compose, previous_image, previous_source
):
    worker = inspect("g2c-beta-worker-1")
    if not worker["State"]["Running"]:
        return False
    if (
        worker["Image"] != previous_image
        or worker["Config"]["Labels"]["org.opencontainers.image.revision"]
        != previous_source
        or worker["Config"]["Cmd"] != ["worker"]
    ):
        raise ValueError("original running worker changed during cutover")
    command([*compose, "up", "-d", "--no-deps", "api"])
    return True


def main(argv=None):
    if not __debug__:
        raise RuntimeError("optimized release entrypoint forbidden")
    args = sys.argv[1:] if argv is None else argv
    gate_raw = Path(args[0]).read_bytes()
    gate = json.loads(gate_raw)
    source = gate["source"]
    previous_source = gate["previous_source"]
    assert re.fullmatch("[a-f0-9]{40}", source) and re.fullmatch(
        "[a-f0-9]{40}", previous_source
    )
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(ROOT / "compose.env"),
        "-f",
        str(ROOT / "deploy/hk/compose.yaml"),
        "-f",
        str(ROOT / "deploy/hk/compose.local-pg.yaml"),
    ]

    def command(args):
        return subprocess.run(
            args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

    def inspect(name):
        return json.loads(command(["docker", "inspect", name]).stdout)[0]

    def proof():
        return json.loads(
            command(
                [
                    *compose,
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "--entrypoint",
                    "python",
                    "-v",
                    str(ROOT / "probes/836-platform-release-proof-plan.json")
                    + ":/plan.json:ro",
                    "-v",
                    str(ROOT / "probes/836-release-export.py") + ":/export.py:ro",
                    "-v",
                    str(ROOT / "budget") + ":/budget:ro",
                    "-v",
                    str(ROOT / "836-platform-release-evidence") + ":/evidence:ro",
                    "migrate",
                    "-B",
                    "/export.py",
                ]
            ).stdout
        )

    def instant(value):
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f+00:00").replace(
            tzinfo=timezone.utc
        )

    def empty(p):
        return (
            p["global_pending"] == p["global_active"] == 0
            and (
                not any(
                    (
                        p["background_states"].get(k, 0)
                        for k in ("queued", "running", "publishing")
                    )
                )
            )
            and (
                not any((p["memory_states"].get(k, 0) for k in ("pending", "inflight")))
            )
        )

    lock = (ROOT / "probes/application-deploy.lock").open("a")
    os.chmod(lock.name, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def window():
        require_release_window(
            gate["starts_at"], gate["ends_at"], datetime.now(timezone.utc)
        )

    now = datetime.now(timezone.utc)
    if any((k in os.environ for k in ("CJ_BETA_IMAGE", "CJ_BETA_OPERATOR_IMAGE"))):
        raise ValueError("ambient selectors forbidden")
    selection = selectors((ROOT / "compose.env").read_bytes())
    assert selection["CJ_BETA_IMAGE"] == "g2c-beta:" + previous_source
    assert re.fullmatch("[a-f0-9]{40}", gate["review_approved_head"])
    assert gate["source_bytes_equal"] and gate["imported_source_bytes_equal"]

    def github(path):
        with urlopen(
            Request(
                "https://api.github.com/repos/" + REPOSITORY + "/" + path,
                headers={"Accept": "application/vnd.github+json"},
            ),
            timeout=20,
        ) as r:
            return json.load(r)

    verify_cutover_evidence(github, source, gate)
    require_release_window(gate["starts_at"], gate["ends_at"], now)
    new = inspect("g2c-beta:" + source)
    assert new["Id"] == gate["image_id"] and new["Architecture"] == "amd64"
    assert new["Config"]["Labels"]["org.opencontainers.image.revision"] == source
    policy = json.loads(
        (ROOT / "quota-self-service-20261112/app-release-policy.json").read_bytes()
    )
    assert (
        json.loads((ROOT / "control/budget/adoption.json").read_bytes())["state"]
        == "ADOPTED_SUBLIMITS_1"
    )
    program = (
        "from pathlib import Path;import hashlib,json;names="
        + repr(list(policy["required_source_hashes"]))
        + ";print(json.dumps({n:hashlib.sha256((Path('/app')/n).read_bytes()).hexdigest() for n in names}))"
    )
    actual = json.loads(
        command(
            [
                "docker",
                "run",
                "--rm",
                "--network=none",
                "--entrypoint",
                "python",
                "g2c-beta:" + source,
                "-B",
                "-c",
                program,
            ]
        ).stdout
    )
    require_source_abi(actual, policy)
    previous_tag = inspect("g2c-beta:" + previous_source)
    assert (
        previous_tag["Id"] == gate["previous_image_id"]
        and previous_tag["Config"]["Labels"]["org.opencontainers.image.revision"]
        == previous_source
    )
    previous = json.loads(
        command(
            [
                "docker",
                "run",
                "--rm",
                "--network=none",
                "--entrypoint",
                "python",
                gate["previous_image_id"],
                "-B",
                "-c",
                program,
            ]
        ).stdout
    )
    require_source_abi(previous, policy)

    def configuration(image, role):
        program = (
            "import json;from deploy.hk.configuration import Runtime,load_secret_environment;load_secret_environment("
            + repr(role)
            + ");r=Runtime.load('/tmp/release-config',worker="
            + repr(role == "worker")
            + ");print(json.dumps(dict(status='CONFIGURATION_VALID',role="
            + repr(role)
            + ",demo_subjects=len(r.demo_subjects))));r.close()"
        )
        reply = json.loads(
            command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network=none",
                    "--read-only",
                    "--tmpfs",
                    "/tmp",
                    "--user",
                    "10001:10001",
                    "--env-file",
                    str(ROOT / "common.env"),
                    "-v",
                    str(ROOT / (role + ".env")) + ":/run/secrets/" + role + ".env:ro",
                    "--entrypoint",
                    "python",
                    image,
                    "-B",
                    "-c",
                    program,
                ]
            ).stdout
        )
        if (
            type(reply) is not dict
            or set(reply) != {"status", "role", "demo_subjects"}
            or reply["status"] != "CONFIGURATION_VALID"
            or (reply["role"] != role)
            or (type(reply["demo_subjects"]) is not int)
            or (not 1 <= reply["demo_subjects"] <= 206)
        ):
            raise ValueError("actual role configuration qualification required")

    for image in (gate["image_id"], gate["previous_image_id"]):
        for role in ("api", "worker"):
            configuration(image, role)

    def archive(worker, *, require_raw=False):
        mounts = {m["Destination"]: m for m in worker["Mounts"]}
        if "/run/tool-evidence/window.json" in mounts or "/tool-evidence" in mounts:
            raise ValueError("default worker must preserve no evidence mount state")
        raw = mounts.get("/rejected-intakes")
        if raw is not None and (
            raw.get("Source") != str(ROOT / "rejected-intakes") or raw["RW"] is not True
        ):
            raise ValueError("exact private rejection mount required")
        if require_raw and raw is None:
            raise ValueError("private rejection mount absent")

    archive(inspect("g2c-beta-worker-1"))
    raw = ROOT / "rejected-intakes"
    info = raw.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != 10001
        or info.st_gid != 10001
        or (stat.S_IMODE(info.st_mode) != 0o700)
    ):
        raise ValueError("qualified private rejection directory required")
    gc_image = "sha256:1f9e5d2ef4434fb5e3cc3ff17dc8f2a496df48b3f6ba1ff80244f7a23405301c"
    environment = ROOT / "rejected-intake-gc.env"
    meta = environment.lstat()
    if (
        not stat.S_ISREG(meta.st_mode)
        or meta.st_uid != 0
        or stat.S_IMODE(meta.st_mode) != 0o600
    ):
        raise ValueError("private immutable GC environment required")
    if environment.read_bytes() != ("REJECTION_GC_IMAGE=" + gc_image + "\n").encode():
        raise ValueError("independent immutable GC pin required")
    for name, digest in {
        "g2c-rejected-intakes-prune.service": "a7f7d19053706dd162c3fba6bdb801bfdf30158801bf3b82db38f88796e8eb2e",
        "g2c-rejected-intakes-prune.timer": "306542356f117b77d2c3f478afaf5d2933b5cde47ca2eed7adf099d07ce7f018",
    }.items():
        path = GC_UNITS / name
        unit = path.lstat()
        if (
            not stat.S_ISREG(unit.st_mode)
            or unit.st_uid != 0
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise ValueError("reviewed independent GC unit required")
    if (
        command(
            ["systemctl", "is-active", "g2c-rejected-intakes-prune.timer"]
        ).stdout.strip()
        != b"active"
    ):
        raise ValueError("independent seven-day GC unavailable")
    if inspect(gc_image)["Id"] != gc_image:
        raise ValueError("independent GC image unavailable")
    if actual == policy["accepted_source_hash_sets"][1]:
        command(
            [
                "docker",
                "run",
                "--rm",
                "--pull=never",
                "--network=none",
                "--read-only",
                "--tmpfs",
                "/tmp",
                "--user",
                "10001:10001",
                "-v",
                str(raw) + ":/rejected-intakes:ro",
                "--entrypoint",
                "python",
                gate["image_id"],
                "-B",
                "-c",
                "from cj_api.rejected_intake_capture import RejectedIntakeSink;RejectedIntakeSink('/rejected-intakes')",
            ]
        )
    control_before = (ROOT / "control/budget/adoption.json").read_bytes()
    for name in ("api", "worker"):
        current = inspect("g2c-beta-" + name + "-1")
        assert (
            current["Image"] == gate["previous_image_id"]
            and current["State"]["Running"]
        )
        assert (
            current["Config"]["Labels"]["org.opencontainers.image.revision"]
            == previous_source
        )
        assert current["Config"]["Cmd"] == [name]
        if name == "api" and any(
            (m["Destination"] == "/rejected-intakes" for m in current["Mounts"])
        ):
            raise ValueError("private rejection directory must remain worker-only")
    before = proof()
    assert empty(before)
    print(
        json.dumps(
            dict(
                stage="PREFLIGHT_PASS",
                source=source,
                image=gate["image_id"],
                ledger=before["ledger"],
                pending=0,
                active=0,
                background_states=before["background_states"],
                memory_states=before["memory_states"],
            )
        ),
        flush=True,
    )
    if "--apply" not in args:
        return 0
    window()
    p = ROOT / "compose.env"
    raw = p.read_text()
    metadata = p.stat()
    pattern = "(?m)^CJ_BETA_IMAGE=g2c-beta:" + previous_source + "$"
    assert len(re.findall(pattern, raw)) == 1
    backup = (
        ROOT
        / "probes"
        / (
            "compose.before-app-"
            + source
            + "-"
            + hashlib.sha256(gate_raw).hexdigest()
            + ".env"
        )
    )
    with backup.open("x") as f:
        f.write(raw)
    backup.chmod(0o600)
    updated = re.sub(pattern, "CJ_BETA_IMAGE=g2c-beta:" + source, raw)
    temporary = ROOT / "compose.app.pending.env"
    with temporary.open("x") as f:
        f.write(updated)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(temporary, metadata.st_mode & 0o777)
    os.chown(temporary, metadata.st_uid, metadata.st_gid)
    worker_stopped = False
    changed = False
    post_started = False
    try:
        window()
        command([*compose, "stop", "-t", "20", "api"])
        window()
        drained = proof()
        assert (
            empty(drained) and drained["ledger"] == before["ledger"]
        ), "original arrived during ingress close; restore old API and reconcile"
        assert datetime.now(timezone.utc) < instant(gate["ends_at"])
        window()
        command([*compose, "stop", "-t", "20", "worker"])
        worker_stopped = True
        window()
        window()
        temporary.replace(p)
        changed = True
        window()
        window()
        command([*compose, "up", "-d", "--no-deps", "api", "worker"])
        window()
        deadline = time.monotonic() + 100
        while True:
            window()
            api = inspect("g2c-beta-api-1")
            worker = inspect("g2c-beta-worker-1")
            assert api["Image"] == worker["Image"] == gate["image_id"]
            assert (
                api["Config"]["Labels"]["org.opencontainers.image.revision"]
                == worker["Config"]["Labels"]["org.opencontainers.image.revision"]
                == source
            )
            assert worker["Config"]["Cmd"] == ["worker"]
            archive(worker, require_raw=True)
            if any((m["Destination"] == "/rejected-intakes" for m in api["Mounts"])):
                raise ValueError("private rejection directory must remain worker-only")
            if (
                api["State"].get("Health", {}).get("Status") == "healthy"
                and worker["State"]["Running"]
            ):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("application readiness deadline exceeded")
            time.sleep(3)
        post_started = True
        window()
        post = proof()
        window()
        assert (
            empty(post)
            and post["ledger"] == before["ledger"]
            and ((ROOT / "control/budget/adoption.json").read_bytes() == control_before)
        )
        window()
        print(
            json.dumps(
                dict(
                    stage="CUTOVER_PASS",
                    source=source,
                    image=gate["image_id"],
                    api_health="healthy",
                    worker_running=True,
                    collector="disabled; previous window closed",
                    ledger_before=before["ledger"],
                    ledger_after=post["ledger"],
                    ledger_unchanged=before["ledger"] == post["ledger"],
                    pending=post["global_pending"],
                    active=post["global_active"],
                    background_states=post["background_states"],
                    memory_states=post["memory_states"],
                    rollback_source=previous_source,
                )
            ),
            flush=True,
        )
    except BaseException:
        if (
            not changed
            and not worker_stopped
            and recover_original_ingress(
                command, inspect, compose, gate["previous_image_id"], previous_source
            )
        ):
            # The original worker may already be processing the newly arrived
            # request. Keep its execution in flight and retain this unused
            # selector beside the immutable per-gate backup.
            temporary.rename(backup.with_suffix(".pending.env"))
            raise
        command([*compose, "stop", "-t", "20", "api", "worker"])
        if (
            post_started
            or (ROOT / "control/budget/adoption.json").read_bytes() != control_before
        ):
            raise
        try:
            prior = inspect("g2c-beta:" + previous_source)
            if (
                prior["Id"] != gate["previous_image_id"]
                or prior["Config"]["Labels"]["org.opencontainers.image.revision"]
                != previous_source
            ):
                raise RuntimeError(
                    "original compatible rollback image changed; ingress closed"
                )
            if changed:
                rollback = p.with_name("compose.app.rollback.env")
                with rollback.open("x") as f:
                    f.write(raw)
                    f.flush()
                    os.fsync(f.fileno())
                os.chmod(rollback, metadata.st_mode & 0o777)
                os.chown(rollback, metadata.st_uid, metadata.st_gid)
                rollback.replace(p)
            command([*compose, "up", "-d", "--no-deps", "api", "worker"])
            recovered_api = inspect("g2c-beta-api-1")
            recovered_worker = inspect("g2c-beta-worker-1")
            if not (
                recovered_api["Image"]
                == recovered_worker["Image"]
                == gate["previous_image_id"]
                and recovered_api["State"]["Running"]
                and recovered_worker["State"]["Running"]
                and (
                    recovered_api["Config"]["Labels"][
                        "org.opencontainers.image.revision"
                    ]
                    == recovered_worker["Config"]["Labels"][
                        "org.opencontainers.image.revision"
                    ]
                    == previous_source
                )
                and (recovered_worker["Config"]["Cmd"] == ["worker"])
            ):
                raise RuntimeError(
                    "compatible rollback readback unknown; ingress closed"
                )
            archive(recovered_worker, require_raw=True)
            if any(
                (
                    m["Destination"] == "/rejected-intakes"
                    for m in recovered_api["Mounts"]
                )
            ):
                raise ValueError("private rejection directory must remain worker-only")
        except BaseException:
            command([*compose, "stop", "-t", "20", "api", "worker"])
            raise
        raise


if __name__ == "__main__":
    raise SystemExit(main())
