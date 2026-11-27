"""Verify the offline workbench recovery tool against its actual PostgreSQL roles."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import psycopg
import pytest

from jt.workbench.tests.test_postgres import ADMIN, NOW, PASSWORD, STAFF, account_auth, cluster, database, prepare


def test_restored_workbench_resets_credentials_and_recovers_only_the_approved_administrator(database):
    owner, _ = database
    store, _ = prepare(database)
    original = account_auth(store).login(ADMIN, PASSWORD)
    assert original
    with psycopg.connect(owner, autocommit=True) as db:
        db.execute("INSERT INTO jt_workbench.accounts (username, role, last_totp_step, enabled) "
                   "VALUES (%s, 'reviewer', -1, true)", (STAFF,))
        deployment = Path(__file__).with_name("recover_admin.py")
        spec = spec_from_file_location("recover_admin", deployment)
        restore = module_from_spec(spec)
        spec.loader.exec_module(restore)
        new_password = "a freshly chosen recovery password"
        with pytest.raises(ValueError, match="roster"):
            restore.recover(db, ADMIN, {ADMIN: "reviewer"}, new_password)
        with pytest.raises(ValueError, match="active|enabled"):
            restore.recover(db, ADMIN, {ADMIN: "admin", "not-in-backup": "operator"}, new_password)
        with pytest.raises(ValueError, match="12 to 128"):
            restore.recover(db, ADMIN, {ADMIN: "admin"}, "too short")
        assert db.execute("SELECT count(*) FROM jt_workbench.sessions").fetchone() == (1,)
        restore.recover(db, ADMIN, {ADMIN: "admin", STAFF: "reviewer"}, new_password)
        assert db.execute("SELECT enabled, password_digest IS NULL FROM jt_workbench.accounts WHERE username=%s",
                          (STAFF,)).fetchone() == (True, True)
        assert db.execute("SELECT count(*) FROM jt_workbench.sessions").fetchone() == (0,)
        assert db.execute("SELECT action, staff_target FROM jt_workbench.audit ORDER BY id DESC LIMIT 1").fetchone() == (
            "password_reset", ADMIN)
    auth = account_auth(store, NOW + 60)
    assert auth.login(ADMIN, PASSWORD) is None
    assert auth.login(STAFF, new_password) is None
    assert auth.login(ADMIN, new_password)
