"""Run against an explicitly started loopback API, using the built generated Swift client."""
import json
import os
from pathlib import Path
import subprocess
from uuid import UUID

base = os.environ["CJ_API_BASE_URL"]
assert os.environ.get("CJ_ENV") == "local"
assert base.startswith("http://127.0.0.1:") and base.count("/") == 2
binary = Path("ios/.build/debug/CJProbe").resolve()
for suffix, expected_status in (("", 0), ("/missing", 1)):
    env = dict(os.environ, CJ_API_BASE_URL=base + suffix)
    result = subprocess.run([str(binary)], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == expected_status, result.stdout
    lines = result.stdout.strip().splitlines()
    body = json.loads(lines[-1])
    UUID(body["request_id"])
    if suffix:
        assert lines[0] == "HTTP 404"
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["outcome"] == "failed"
    else:
        assert body["status"] == "ok" and body["contract_version"] == "1.0.0"
    print(f"PASS Swift→HTTP→Python {suffix or '/v1/probe'} exit={result.returncode}: {json.dumps(body)}")
for env in ({}, {"CJ_ENV": "local", "CJ_API_BASE_URL": "https://example.com"}):
    result = subprocess.run([str(binary)], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 1 and "configuration" in result.stdout
    print("PASS Swift missing/external configuration fails before network")
