"""One reviewed config holds every authorization end (#1716); copies must agree."""
import ast
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import re

import pytest

from cj_api import supabase_test_database
from cj_usage import authorization_budget,authorization_deadlines as config
from deploy.hk import demo_accounts,readiness_monitor,secret_setup

ROOT=Path(__file__).resolve().parents[2]
SHANGHAI=timezone(timedelta(hours=8))
NEW_YEAR=datetime(2027,1,1,tzinfo=SHANGHAI)


def test_jt_approved_2027_new_year_for_every_extended_allowance():
    assert config.DEADLINES=={name:NEW_YEAR for name in ('oss_backup','supabase_test','mac_provider_acceptance','hk_demo')}
    assert config.utc_text('oss_backup')=='2026-12-31T16:00:00+00:00'
    assert config.approved_utc_texts('oss_backup')==('2026-11-30T16:00:00+00:00','2026-12-31T16:00:00+00:00')
    assert config.boundary('m4_original_period_end')==datetime(2026,12,1,tzinfo=SHANGHAI)


def test_runtime_constants_read_the_config():
    assert supabase_test_database.DEADLINE==config.deadline('supabase_test')
    assert supabase_test_database.DEMO_DEADLINE==demo_accounts.DEADLINE==authorization_budget.DEMO_DEADLINE==config.deadline('hk_demo')
    # The HK run context persists this split; it is a period boundary, not an expiry.
    assert authorization_budget.DEADLINE==secret_setup.DEADLINE==config.boundary('m4_original_period_end')


def test_copies_outside_python_imports_match_the_config():
    assert readiness_monitor.ENDS_AT==config.deadline('hk_demo')
    migration=(ROOT/'backend/migrations/0049_demo_invitation.sql').read_text()
    assert f"demo_invite_expires_at <= '{config.deadline('hk_demo').isoformat()}'::timestamptz" in migration
    assert '至 2026-12-31' in (ROOT/'deploy/supabase-test.md').read_text()


CALLERS=['backend/cj_api/supabase_test_database.py','backend/usage/cj_usage/authorization_budget.py',
    'deploy/hk/configuration.py','deploy/hk/demo_accounts.py','deploy/hk/secret_setup.py','deploy/hk/cloud_rehearsal.py',
    'deploy/hk/oss_quota.py','scripts/provider_m4.py','scripts/supabase_m4.py']


@pytest.mark.parametrize('path',CALLERS)
def test_no_scattered_authorization_dates_remain(path):
    text=(ROOT/path).read_text()
    assert re.search(r"datetime\(202[67],|'202[67]-[01][0-9]-[0-3][0-9](T|')",text) is None


@pytest.mark.parametrize('path',CALLERS)
def test_imported_deadline_readers_are_never_shadowed(path):
    tree=ast.parse((ROOT/path).read_text())
    imported={alias.asname or alias.name for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)
              and node.module in ('cj_usage.authorization_deadlines','.authorization_deadlines','authorization_deadlines')
              for alias in node.names}
    assert imported
    stored={node.id for node in ast.walk(tree) if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Store)}
    stored|={node.arg for node in ast.walk(tree) if isinstance(node,ast.arg)}
    assert not imported&stored


@pytest.mark.parametrize('mutate,error',[
    (lambda d:d['deadlines'].pop('oss_backup'),'authorization_deadline_config_invalid'),
    (lambda d:d['deadlines'].update(oss_backup='2026-12-31T16:00:00+00:00'),'explicit_Asia_Shanghai_deadline_required'),
    (lambda d:d['previous'].update(oss_backup=['2027-01-01T00:00:00+08:00']),'previous_deadlines_must_precede_current'),
    (lambda d:d['previous'].update(oss_backup=[]),'authorization_deadline_config_invalid'),
])
def test_config_shape_fails_closed(tmp_path,monkeypatch,mutate,error):
    data=json.loads(config.PATH.read_text());mutate(data)
    path=tmp_path/'deadlines.json';path.write_text(json.dumps(data));monkeypatch.setattr(config,'PATH',path)
    with pytest.raises(ValueError,match=error):config._load()


def test_duplicate_keys_fail_closed(tmp_path,monkeypatch):
    text=config.PATH.read_text().replace('"oss_backup": "2027','"oss_backup": "2027-01-01T00:00:00+08:00",\n    "oss_backup": "2027',1)
    path=tmp_path/'deadlines.json';path.write_text(text);monkeypatch.setattr(config,'PATH',path)
    with pytest.raises(ValueError,match='duplicate_authorization_deadline'):config._load()
