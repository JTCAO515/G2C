# UI@1.1 candidate — CJ006 / Issue #7

Owner: CJ006 execution chat 01a15e71-9e73-7a02-85f5-de1081673c6d.
Base: 00769d7f793566887a8e192a6ca7b35d8c5fb46a. Candidate, not independent acceptance or production release.

## Consumer confirmation: BASE@1.0

Read `contracts/api/openapi.json` and its probe, failure, conflict and unknown examples at the fixed base. Only GET /v1/probe and error/request_id are stable. request_id is per HTTP attempt, never identity/idempotency. A successful probe does not authorize UI actions or prove readiness. This shell makes no HTTP calls and does not duplicate API types. AUTH/MESSAGE/RUN/MEMORY/TRIP remain unconsumed. CJ004/CJ005 integration and device acceptance remain required.

## Native interface

`ios/Modules/CJShell/Sources/CJShell/ShellState.swift` is the source of the typed presentation contract; `ShellView(state:)` renders it. Host retains one ShellState per window/session and never keys it by language. Minimum iOS 17/macOS 14 are local package experiment targets only.

- Stable ordered tabs: assistant, trips, plugins, memory. Account is never a fifth tab.
- MemoryRoute: group(facts/experiences/preferences), account, language, help, privacy, support. Account/settings remain accessible regardless of memory state.
- ShellPageState: notConnected, empty, loading, failed, offline, unknown. Presentation states cannot establish authentication, receipt, synchronization or domain completion. `empty` requires a domain-confirmed empty result; default is `notConnected`.
- ShellContext retains optional opaque conversation/trip references supplied by domain owners. UI never creates, translates, persists or authorizes with these references. Language switching only changes labels, never the selected tab, path, draft or context.
- Only `cj.ui.language.v1` persists (en / zh-Hans) using injected UserDefaults. Unknown stored values surface a warning, use English for display and remain untouched until explicit selection. Draft/context/path live in memory only; restart restoration is not claimed. Preferences are local UI settings, not long-term user memory.
- `hasDraft` chooses voice/send presentation. `canSend` remains false until a versioned MESSAGE/RUN integration; draft is never cleared by placeholder actions. No fake saved/logged-in state, retries, network requests or permissions.
- Future memory records/detail/actions and auth rendering require domain-owned adapters and consumer confirmation, not inferred fields. Groups currently lead to honest unavailable containers. Source/time/edit/delete/enable receipts remain domain responsibility; no fabricated records are presented.

## Positive / negative samples and checks

`examples.json` contains presentation-only fixtures, explicitly not API payloads. `check_contract.py` checks fixed BASE shape plus sample validity and negative rejection. Swift tests exercise persistence, navigation/draft/reference retention, unsupported values and unavailable send. No fixture performs formal writes.

From repo root:

```sh
python3 contracts/ui/check_contract.py
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache \
  swift test --disable-sandbox --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-swift-build
```

Breaking UI changes need a new version and consumer impact review. Additions require old-consumer checks. No downstream consumer has confirmed UI@1.1 yet; Main routes the fixed candidate to CJ007 and Review/Testing. No secrets, account data, analytics or logs are stored by this module. Host identity-change invalidation is mandatory before future domain integration; the local reset boundary is defined below. This candidate does not implement auth or remote cleanup guarantees.

`ShellPresentation.assistantBody` accepts optional plain native text. It is retained inside ShellState and rendered only after a generation-checked apply. It does not parse messages, stream events, generate business IDs or persist content. The demo labels synthetic long text explicitly.

## UI@1.1 migration from e722bef / UI@1.0

The old candidate remains reproducible at e722bef. This is a source-breaking candidate revision, not an in-place compatibility claim. CJ007 64f48cf confirmed only the old entry/language/presentation semantics; renewed consumer confirmation is PENDING.

- Replace direct context/page writes and `ShellView(state:assistantBody:)` with `state.apply(ShellPresentation(...), for: capturedGeneration)` and `ShellView(state:)`. The package Demo is the only implementation consumer in this clone and has migrated; no root host integration exists.
- `generation` is an opaque UI-local token created per ShellState instance/reset; not a principal, backend session/revision, request_id, authorization or durable identifier.
- The future host adapter is the sole identity lifecycle owner. Before logout/account switch/session invalidation, synchronously call `invalidateIdentity()` on MainActor before new verification/work. This rotates the local generation first, clears draft/context/private routes/body/all page states atomically, preserves language and selected tab, and closes the shell history sheet/input focus on observation.
- Host captures `state.generation` BEFORE starting domain work, retains that exact token across every await, verifies its real AUTH binding independently, and then calls `apply`. False means discard the stale projection; do not fetch a fresh token to relabel the old result. Cross-instance tokens also fail.
- Domain projection is read-only from outside ShellState. Draft and navigation bindings remain synchronous local UI edits, not late network delivery APIs. Future hosts must not route async private updates through those bindings or retain a second external body renderer.
- `invalidateIdentity()` does not authenticate, invalidate credentials, cancel remote execution, delete records or clear external host caches. The host must separately fence/cancel those owners. Unknown/offline presentation alone MUST NOT trigger identity invalidation.
- Direct Swift negative test covers all private fields, late A after reset, late A after B is visible, token from another instance, and language not changing generation. This is local state proof only; real AUTH mapping/adapter remains UNRUN.
