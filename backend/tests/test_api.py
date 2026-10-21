import json
from pathlib import Path
from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from cj_api.app import create_app
from cj_api.generated import ProbeResponse, ErrorResponse

@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("CJ_ENV", "local")
    return create_app()

def test_requires_explicit_local(monkeypatch):
    for value in (None, "", "production", "test"):
        monkeypatch.delenv("CJ_ENV", raising=False)
        if value is not None:
            monkeypatch.setenv("CJ_ENV", value)
        with pytest.raises(RuntimeError):
            create_app()

def test_success_and_safe_trace(app):
    with TestClient(app) as client:
        first = client.get("/v1/probe", headers={"X-Request-ID": "untrusted-private-value"})
        second = client.get("/v1/probe")
    body = ProbeResponse.model_validate(first.json())
    assert first.status_code == 200
    assert str(body.request_id.root) == first.headers["X-Request-ID"]
    UUID(first.headers["X-Request-ID"])
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]
    assert first.headers["Cache-Control"] == "no-store"

def test_failures_are_structured_and_redacted(app):
    @app.get("/test-only-fault")
    async def fault():
        raise RuntimeError("secret exception payload")
    with TestClient(app) as client:
        for path, status in (("/missing?secret=value",404),("/test-only-fault",500)):
            response = client.get(path)
            body = ErrorResponse.model_validate(response.json())
            assert response.status_code == status
            assert str(body.request_id.root) == response.headers["X-Request-ID"]
            assert "secret" not in response.text
            assert body.error.outcome == "failed"

def test_served_contract_is_canonical(app):
    root = Path(__file__).resolve().parents[2]
    assert app.openapi() == json.loads((root / "contracts/api/openapi.json").read_text())
