"""The runnable local entry always uses the signed Trip confirmation path (no database needed)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


def dev_auth(*args):
    subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/dev_auth.py'), *args], check=True, capture_output=True)


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setenv('CJ_ENV', 'local')
    auth = tmp_path / 'auth'
    dev_auth('init', str(auth), '--invite', 'alice')
    conninfo = tmp_path / 'conn.json'
    conninfo.write_text(json.dumps({'host': str(tmp_path / 'no-server'), 'dbname': 'unused'}))
    monkeypatch.setenv('CJ_LOCAL_AUTH_DIR', str(auth))
    monkeypatch.setenv('CJ_LOCAL_CONNINFO', str(conninfo))
    return auth


def test_init_creates_private_key_and_entry_enables_signed_preparation(local):
    from cj_api.local_app import app_from_environment
    key = local / 'trip-confirmation.key'
    assert key.stat().st_mode & 0o777 == 0o600 and len(key.read_bytes()) == 32
    with TestClient(app_from_environment()) as client:
        response = client.post('/v1/trip-confirmations', json={})
    # Signer configured: the route parses input (401 without a token) instead of 503 unavailable.
    assert response.status_code == 401


@pytest.mark.parametrize('damage', ['missing', 'public', 'short'])
def test_entry_refuses_to_start_without_a_private_full_length_key(local, damage):
    from cj_api.composition import CompositionUnavailable
    from cj_api.local_app import app_from_environment
    key = local / 'trip-confirmation.key'
    if damage == 'missing':
        key.unlink()
    elif damage == 'public':
        os.chmod(key, 0o644)
    else:
        key.write_bytes(b'x' * 16)
    with pytest.raises(CompositionUnavailable):
        app_from_environment()


def test_confirmation_key_command_never_overwrites(local):
    with pytest.raises(subprocess.CalledProcessError):
        dev_auth('confirmation-key', str(local))
