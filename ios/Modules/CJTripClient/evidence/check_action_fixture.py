"""Read-only check against fixed public producer. Python >= 3.10; no DB/network."""
from pathlib import Path
import base64
import json
import subprocess
import sys
import types

PIN = "5fd115fc97e542bc8776a445d8245fd272000e56"
root = Path(__file__).resolve().parents[1]
fixture = json.loads((root / "Tests/CJTripClientTests/Fixtures/action.json").read_text())
source = subprocess.check_output([
    "git", "-C", sys.argv[1], "show", f"{PIN}:backend/trip/cj_trip/domain.py"
])
module = types.ModuleType("fixed_trip_domain")
sys.modules[module.__name__] = module
exec(compile(source, f"{PIN}:domain.py", "exec"), module.__dict__)
p = fixture["proposal"]
proposal = module.Proposal(p["proposal_id"], p["trip_id"], p["expected_version"],
                          p["basis_version"], p["expires_at"], base64.b64decode(p["content_utf8_base64"]))
assert fixture["producer"] == PIN
assert json.loads(proposal.content) == p["document"]
assert proposal.digest("synthetic-server-held-scope") == p["candidate_hash"]
for kind in ("accept", "reject"):
    raw = module.Action(f"{kind}1", kind, proposal.proposal_id, p["candidate_hash"],
                        f"server-held-{kind}-proof").raw()
    assert raw == fixture[f"{kind}_raw"].encode("utf-8")
print("PASS: fixed public Proposal and Action.raw accept/reject exact fixture bytes")
