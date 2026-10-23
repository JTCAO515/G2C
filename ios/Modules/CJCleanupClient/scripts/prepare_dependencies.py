"""Exact read-only fixed-source exports inside this module; no SDK generation/rewrites."""
from pathlib import Path
import hashlib, json, subprocess, sys
SHARED = "9b4852dfad418d124d60366ada8efb380a8ffc1d"
ROOT = "dc29bb3634e63d8f065c38d39a7a0059f76cfa53"
PIN_HASH = "27622b44f0d8ac91ae2154d1cc9db35a7b86ca332f2564e09777fba89efb8e61"
AUTH = "4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e"
module = Path(__file__).resolve().parents[1]
shared, producer, auth = map(Path, sys.argv[1:])
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
(module / "evidence/sdkdc29").mkdir(parents=True, exist_ok=True)
exports = {}
for name in ("CJMessageClient", "CJAuth"):
    prefix = f"ios/Modules/{name}/"
    source, commit = (auth, AUTH) if name == "CJAuth" else (shared, SHARED)
    for path in files(source, commit, prefix):
        tail = path.removeprefix(prefix)
        # Keep original manifests, lockfiles, source, and referenced test paths.
        if tail in ("Package.swift", "Package.resolved") or tail.startswith(("Sources/", "Tests/")):
            exports[path] = blob(source, commit, path)
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
(module / "evidence/sdkdc29/dependency-pin.json").write_text(json.dumps({
    "shared": SHARED, "root": ROOT, "auth": AUTH, "sdk_pin_sha256": PIN_HASH,
    "sha256": {path: hashlib.sha256(data).hexdigest() for path, data in sorted(exports.items())}
}, indent=2) + "\n")
print(f"PASS fixed source/hash exports: {len(exports)} files; one official SDK {ROOT}")
