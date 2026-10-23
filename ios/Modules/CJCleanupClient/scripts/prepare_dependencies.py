"""Exact read-only fixed-source exports inside this module; no SDK generation/rewrites."""
from pathlib import Path
import hashlib, json, subprocess, sys
SHARED = "cc9e2c3ba1fb8fe7582e5e4664a924b1c6b93f71"
ROOT = "20aa50ed5c8449e6026155a6151f22041dee7fd4"
PIN_HASH = "71fec98555a93dc2fc1c9ad3ddcaf9cd209b5b885df50739505d2f9e633b78f7"
module = Path(__file__).resolve().parents[1]
shared, producer = map(Path, sys.argv[1:])
def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])
def blob(repo, commit, path):
    return git(repo, "show", f"{commit}:{path}")
def files(repo, commit, path):
    return git(repo, "ls-tree", "-r", "--name-only", commit, path).decode().splitlines()
# Read immutable git blobs, never moving source worktree contents.
pin_bytes = blob(shared, SHARED, "ios/Modules/CJMessageClient/evidence/generated-pin.json")
assert hashlib.sha256(pin_bytes).hexdigest() == PIN_HASH, "untrusted SDK pin manifest"
pin = json.loads(pin_bytes)
assert pin["commit"] == ROOT
(module / "evidence/sdk20aa").mkdir(parents=True, exist_ok=True)
exports = {}
for name in ("CJMessageClient", "CJAuth"):
    prefix = f"ios/Modules/{name}/"
    for path in files(shared, SHARED, prefix):
        tail = path.removeprefix(prefix)
        # Keep original manifests, lockfiles, source, and referenced test paths.
        if tail in ("Package.swift", "Package.resolved") or tail.startswith(("Sources/", "Tests/")):
            exports[path] = blob(shared, SHARED, path)
assert ROOT.encode() in exports["ios/Modules/CJMessageClient/Package.swift"]
for path, expected in pin["sha256"].items():
    data = blob(producer, ROOT, path)
    assert hashlib.sha256(data).hexdigest() == expected, f"SDK source hash mismatch: {path}"
    exports[f"ios/Modules/CJMessageClient/.generated/{ROOT}/CJFoundation/" + path.removeprefix("ios/")] = data
# Preflight ALL files before creating exports. Never overwrite a different existing file.
for path, data in exports.items():
    dest = module / ".deps" / ROOT / path
    assert not any(parent.is_symlink() for parent in (dest, *dest.parents)), "symlink export refused"
    assert not dest.exists() or dest.read_bytes() == data, f"different export: {dest}"
for path, data in exports.items():
    dest = module / ".deps" / ROOT / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists(): dest.write_bytes(data)
(module / "evidence/sdk20aa/dependency-pin.json").write_text(json.dumps({
    "shared": SHARED, "root": ROOT, "sdk_pin_sha256": PIN_HASH,
    "sha256": {path: hashlib.sha256(data).hexdigest() for path, data in sorted(exports.items())}
}, indent=2) + "\n")
print(f"PASS fixed source/hash exports: {len(exports)} files; one official SDK {ROOT}")
