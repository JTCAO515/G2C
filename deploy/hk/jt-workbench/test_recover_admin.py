"""Verify the offline workbench recovery tool against its actual PostgreSQL roles."""
import time
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import psycopg
import pytest

from jt.workbench.auth import Auth
from jt.workbench.security import totp_at_step
from jt.workbench.tests.test_postgres import (
    ADMIN, NOW, PASSWORD, SEED, STAFF, STAFF_SEED, account_auth, cluster, database, prepare, seed_text,
)


def test_restored_workbench_reenrolls_only_approved_staff(database):
    owner, _ = database
    store, _ = prepare(database)
    original = account_auth(store).login(ADMIN, PASSWORD, totp_at_step(SEED, NOW // 30))
    assert original
    with psycopg.connect(owner, autocommit=True) as db:
        db.execute("INSERT INTO jt_workbench.accounts (username, role, last_totp_step, enabled) "
                   "VALUES (%s, 'reviewer', -1, true)", (STAFF,))
        deployment = Path(__file__).with_name("recover_admin.py")
        spec = spec_from_file_location("recover_admin", deployment)
        restore = module_from_spec(spec)
        spec.loader.exec_module(restore)
        with pytest.raises(ValueError, match="roster"):
            restore.reissue(db, ADMIN, {ADMIN: "reviewer"})
        with pytest.raises(ValueError, match="active|enabled"):
            restore.reissue(db, ADMIN, {ADMIN: "admin", "not-in-backup": "operator"})
        setup = restore.reissue(db, ADMIN, {ADMIN: "admin"})
        assert db.execute("SELECT enabled FROM jt_workbench.accounts WHERE username=%s", (STAFF,)).fetchone() == (False,)
        assert db.execute("SELECT count(*) FROM jt_workbench.sessions").fetchone() == (0,)
        assert db.execute("SELECT action FROM jt_workbench.audit ORDER BY id DESC LIMIT 1").fetchone() == ("totp_rebind_authorized",)
    auth = Auth(store, clock=store.clock, monotonic=store.clock)
    code = totp_at_step(STAFF_SEED, int(time.time()) // 30)
    assert auth.bind_account(ADMIN, setup, PASSWORD, seed_text(STAFF_SEED), code)
    assert not auth.bind_account(ADMIN, setup, PASSWORD, seed_text(STAFF_SEED), code)
