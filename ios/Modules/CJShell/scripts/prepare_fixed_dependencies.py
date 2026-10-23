"""Read immutable Git inputs into this module's ignored f87 combination only."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

SDK = "f87a78a9d8984c59905e385483f17dddd8144d8a"
SHARED = "5075bcf604e959d5c4592071a1e9de39d8687395"
SDK_MANIFEST_SHA256 = "d68753aebc748dd55d8f7730f3147d267b693410513b29af85afceec92243f27"
INPUTS = {
    "CJMessageClient": ("cj-009-memory-api-pin", SHARED),
    # Offline2772's explicit accepted Auth pin includes all pending/snapshot key
    # purposes. Its Sources tree is identical to published main b331's Auth.
    "CJAuth": ("cj-007-auth", "4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e"),
    "CJMemoryClient": ("cj-011-memory-client", "1734971c7606a346cfb73609eab6a06c16e8791a"),
    "CJTripClient": ("cj-015-trip-client", "a5cc42005c69811ccb05754793107141fb4a9f02"),
    "CJNeedsClient": ("cj-013-needs-client", "f8ce99b916f1fd15f06ad534e44d3d2ce55dc1a6"),
    "CJFeedbackClient": ("cj-023-feedback-client", "978df94db9c452fc0d24e50514ba1e4295e8a1ea"),
    "CJRunClient": ("cj-010-run-client", "a09fa5cdf229a21d5f51fa22d437a5164b57732e"),
    "CJUsageClient": ("cj-008-usage-client", "7a1d4783d434fe69c62e954db93157a54f6e4182"),
    "CJManualPreviewClient": ("cj-017-manual-preview-client", "46581fc954771ad9b388b0c600aee4dc74524730"),
    "CJOfflineTrip": ("cj-022-offline-trip", "2772d896db33344126eae2d025cd7d378dff1c8e"),
    "CJCleanupClient": ("cj-024-cleanup-client", "6d5e318e95ab5f2be25b21569f26b37df23546f9"),
}


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def prepare(checkouts):
    module = Path(__file__).resolve().parents[1]
    destination = module / ".deps" / SDK
    exports, inputs = {}, {}
    for name, (checkout, fixed) in INPUTS.items():
        repo, prefix = checkouts / checkout, f"ios/Modules/{name}/"
        paths = git(repo, "ls-tree", "-r", "--name-only", fixed, prefix).decode().splitlines()
        for path in paths:
            tail = path.removeprefix(prefix)
            if tail in ("Package.swift", "Package.resolved") or tail.startswith(("Sources/", "Tests/")):
                exports[path] = git(repo, "show", f"{fixed}:{path}")
        if prefix + "Package.swift" not in exports:
            raise ValueError(f"Missing fixed module manifest: {name}")
        inputs[name] = {"checkout": checkout, "fixed": fixed,
                        "tree": git(repo, "rev-parse", f"{fixed}:{prefix[:-1]}").decode().strip()}

    manifest_bytes = git(checkouts / "cj-009-memory-api-pin", "show",
                         f"{SHARED}:ios/Modules/CJMessageClient/evidence/generated-pin.json")
    if hashlib.sha256(manifest_bytes).hexdigest() != SDK_MANIFEST_SHA256:
        raise ValueError("Fixed SDK manifest hash mismatch")
    manifest = json.loads(manifest_bytes)
    if manifest["commit"] != SDK:
        raise ValueError("Unexpected SDK fixed input")
    for path, expected in manifest["sha256"].items():
        if not path.startswith("ios/") or ".." in Path(path).parts:
            raise ValueError("Invalid fixed export path")
        data = git(checkouts / "cj-005-foundation", "show", f"{SDK}:{path}")
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"SDK source hash mismatch: {path}")
        exports[f"ios/Modules/CJMessageClient/.generated/{SDK}/CJFoundation/" + path.removeprefix("ios/")] = data

    # Preflight every file before writing anything. Conflicting old preparations
    # are errors, not permission to overwrite files or reinterpret a moving head.
    for path, data in exports.items():
        dest = destination / path
        if any(p.is_symlink() for p in (dest, *dest.parents)):
            raise ValueError(f"Symlink export refused: {dest}")
        if dest.exists() and dest.read_bytes() != data:
            raise ValueError(f"Different existing export: {dest}")
    for path, data in exports.items():
        dest = destination / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(data)
    provenance = {"sdk": SDK, "sdk_manifest_sha256": SDK_MANIFEST_SHA256,
                  "inputs": inputs, "sdk_files": len(manifest["sha256"]),
                  "sha256": {p: hashlib.sha256(b).hexdigest() for p, b in sorted(exports.items())}}
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"PASS: {len(inputs)} fixed modules, {len(exports)} exact files, one SDK {SDK}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkouts", type=Path, help="Directory containing the existing CJ owner checkouts")
    prepare(parser.parse_args().checkouts)
