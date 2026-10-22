"""Read-only exact producer check; no database/server/import of a moving tree."""
import json
from pathlib import Path
import subprocess
import sys
import types

PIN = "c821b34d607016c6dbc1020c203621841f1a60e8"
source = subprocess.check_output([
    "git", "-C", sys.argv[1], "show", PIN + ":backend/needs/cj_needs/domain.py"
])
module = types.ModuleType("fixed_needs_domain")
sys.modules[module.__name__] = module
exec(compile(source, "fixed-domain.py", "exec"), module.__dict__)
raw = Path(__file__).with_name("generated-command.json").read_bytes()
command = module.Command(raw)
module.validate_fields(command.data["changes"], complete=True)
assert command.data["changes"]["budget_total"]["value"] == "1234.5600"
assert "arrival" not in command.data["changes"]
print(json.dumps({"producer": PIN, "status": "PASS", "network": False, "database": False}))
