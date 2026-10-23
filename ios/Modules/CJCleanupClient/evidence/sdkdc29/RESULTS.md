# Formal Cleanup SDKdc29 consumer migration

2026-10-23 Asia/Shanghai. Delta base:
`d749fdc3ca4a25c78e5f9cc0eba3f55113255798`.
Only `ios/Modules/CJCleanupClient/**`; formal Package.swift now uses dc29 in both
normal sibling mode and isolated fixed-input mode. No temporary manifest
substitution. Runtime Sources, Tests, Package.resolved unchanged; no type alias,
second SDK, new functionality or factory change. Old f87/20aa exports, commits,
evidence and FAILs preserved. No peer/Shell/shared/lock modification.

## Exact inputs / first write

First tracked write: this module's Package.swift + scripts/prepare_dependencies.py.

- shared `9b4852dfad418d124d60366ada8efb380a8ffc1d`.
- Official SDK `dc29bb3634e63d8f065c38d39a7a0059f76cfa53`.
- Fixed Auth `4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e` directly from Auth owner Git.
- Main's Trip graph input `7bcab1b13bc683c205f3ff0fa4446657427a5225` has formal dc29
  Package verified read-only. Cleanup has no Trip dependency; its candidate gate
  and complete host graph combination remain separate. No artificial dependency.
- Shared official SDK pin manifest SHA256:
  `27622b44f0d8ac91ae2154d1cc9db35a7b86ca332f2564e09777fba89efb8e61`.

Prepare reads immutable Git blobs, verifies SDK hashes before exporting all 71
files, refuses conflicting/symlink exports and uses own ignored `.deps/<dc29>/**`.
Auth is explicitly sourced from its fixed owner commit, not stale shared Auth.
`dependency-pin.json` records every exported file hash and all three source pins.

## PASS — direct incremental verification

- `compatibility.json`: cleanup GET operation and its six referenced schemas
  (CleanupProgressStep/CurrentAccountCleanupProgress/Response/ErrorInfo/
  ErrorResponse/RequestId) unchanged from 20aa. Official helper, root manifest/lock
  and Transport94 bytes unchanged. Own Sources/Tests/lock unchanged from base.
- `prepare.txt`: immutable-input export/hash preflight PASS, 71 exact files.
- `selected-tests.txt.gz`: 6 existing functions PASS on dc29 + Auth4eac:
  original GET once/blocked projection; unknown/in-progress/failed/scoped complete;
  401/403/404/503/redirect; old result cannot clear newer loaded generation;
  credentials callback logout/switch stops request; loaded projection clears on
  logout without another request. In-process intercepted fixtures only.
- `ios-compile.txt.gz`: generic iOS Simulator BUILD SUCCEEDED, code signing disabled,
  package automatic resolution/updates disabled for this compile. Unmodified
  client/SwiftUI compile against the official dc29 generated API and fixed Auth.
- `package-graph.json` + `single-sdk.txt`: exactly one dc29 CJFoundation,
  one shared9b485 CJMessageClient and one fixed Auth4eac; zero f87/20aa paths in
  selected graph. `graph-stderr.txt` retains SwiftPM skip-update deprecation warning.
- Source and staged whitespace checks PASS. Delta file hashes in file-manifest.json.

Reuse original 19-function behavior evidence and prior 20aa codec/consumer checks;
no broad suite, PG, Keychain or device rerun. No business behavior changes.

## Input discrepancy preserved and handled

Initial read-only assertion comparing requested Auth4eac SessionLifecycle to the
old sharedcc9 Auth copy failed before any writes. Exact delta inspected and kept
in `auth-input-delta.diff.gz`; `preflight-note.txt` retains that stop. Auth4eac adds
public ownership/clear-settlement behavior; existing isCurrent remains the read
fence. Export the specified canonical Auth directly and include the two existing
logout/clear consumer tests above. Do not claim all Auth source bytes unchanged.
No new compile or consumer-test failure in this increment.

## Pending / UNRUN

Fixed candidate goes to existing independent Review/Testing gates. Main's accepted
shared gate does not admit this new consumer automatically. Full App still requires
all formal peer Package pins, exact Auth/Trip inputs and host combination gate to
converge on dc29 before shared publication. Single-module PASS is not that gate.

Factory remains closed; no trusted original operation source connected. Unavailable
remains required without provenance/current ALLOWED binding. No real account/API
network, cache, Keychain, saving, deletion/cleanup, provider/fees, TTL assumption or
permission recovery. No simulator boot, App UI interaction or physical device.
Postlogout query and whole Issue #27 acceptance remain UNRUN/open. No push/merge,
release or Issue-close operation was performed.
