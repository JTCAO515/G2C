"""A schema step must move the daily-backup pin with the operator (2026-11-28 incident, #1715).

deploy/release-tools/step-release-program.py runs on the Hong Kong host only, so this checks its
structure: the preflight refuses a new operator that does not know exactly the target schema and a
running daily backup, and the cutover rewrites backup.image in the same phase as the selectors,
before api/worker start, keeping the previous pin for rollback.
"""
from pathlib import Path

PROGRAM = (Path(__file__).resolve().parents[2] / 'deploy/release-tools/step-release-program.py').read_text()


def test_preflight_requires_the_new_operator_to_know_the_target_schema_and_an_idle_backup():
    preflight = PROGRAM[:PROGRAM.index("STEP%d_PREFLIGHT_PASS")]
    assert "len(checkpoint.versions())" in preflight and "pinned_versions!=TARGET" in preflight
    assert "backup_idle()" in preflight and "'g2c-beta-backup.service'" in preflight


def test_cutover_moves_the_backup_pin_with_the_selectors_before_the_service_starts():
    selectors = PROGRAM.index("temporary.replace(p)")
    pin = PROGRAM.index("pending.replace(backup_pin)")
    start = PROGRAM.index("command(base+['up','-d','--no-deps','api','worker'])")
    assert selectors < pin < start
    assert "'backup.image.before'" in PROGRAM and "os.O_EXCL" in PROGRAM[selectors:pin]
    assert "'g2c-beta-operator:'+SOURCE+' '+gate['operator_image_id']" in PROGRAM
    assert "daily_backup_image.py" in PROGRAM[pin:start]
    # The selector reads a relative path: the readback must run from ROOT and refuse an empty selection.
    assert "cwd=str(ROOT)" in PROGRAM[pin:start] and "if not selected or" in PROGRAM[pin:start]


def test_backup_idle_refuses_any_state_but_a_known_idle_one():
    assert "if state not in ('inactive','failed')" in PROGRAM
