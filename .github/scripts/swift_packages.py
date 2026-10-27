"""Compare the explicit CI inventory against every tracked iOS Swift manifest."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
packages = json.loads((ROOT / ".github/swift-packages.json").read_text())
tracked = subprocess.check_output(
    ["git", "ls-files", "-z", "--", "ios"], cwd=ROOT
).decode().split("\0")
actual = {str(Path(name).parent) for name in tracked if Path(name).name == "Package.swift"}
if not isinstance(packages, list) or any(not isinstance(p, str) for p in packages):
    raise SystemExit("Swift inventory must be a list of package paths")
if len(packages) != len(set(packages)) or set(packages) != actual:
    raise SystemExit(f"Swift inventory mismatch: missing={sorted(actual - set(packages))}, "
                     f"stale={sorted(set(packages) - actual)}; duplicates are forbidden")
print("packages=" + json.dumps(packages, separators=(",", ":")))
