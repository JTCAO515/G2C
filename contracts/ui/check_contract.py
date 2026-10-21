"""Local presentation checks, not API or service acceptance."""
import json
from pathlib import Path
root = Path(__file__).resolve().parents[2]
base = json.loads((root / "contracts/api/openapi.json").read_text())
assert base["info"]["version"] == "1.0.0"
assert set(base["paths"]) == {"/v1/probe"}
assert set(base["paths"]["/v1/probe"]) == {"get"}
assert "never an idempotency or authorization token" in base["components"]["schemas"]["RequestId"]["description"]
examples = json.loads(Path(__file__).with_name("examples.json").read_text())
assert examples["contract"] == "UI@1.1" and examples["synthetic"] is True

def valid(item):
    return (set(item) == {"tab", "language", "state"}
            and item["tab"] in ["assistant", "trips", "plugins", "memory"]
            and item["language"] in ["en", "zh-Hans"]
            and item["state"] in ["notConnected", "empty", "loading", "failed", "offline", "unknown"]
            and (item["tab"] != "plugins" or item["state"] == "notConnected"))

assert all(map(valid, examples["positive"]))
assert not any(map(valid, examples["negative"]))
print("PASS: BASE boundary; 7 positive and 5 negative UI presentation samples")
