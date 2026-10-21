# UI@1.0 candidate — CJ006 / Issue #7

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
swift test --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-swift-build
```

Breaking UI changes need a new version and consumer impact review. Additions require old-consumer checks. No downstream consumer has confirmed UI@1.0 yet; Main routes the fixed candidate to CJ007 and Review/Testing. No secrets, account data, analytics or logs are stored by this module. Host identity-change cleanup is mandatory before future domain integration; this candidate does not implement auth or claim cleanup guarantees.
