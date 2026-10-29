# CJ-010 original-run display and bounded cancellation client

Read-only by default for original MESSAGE recovery, composed by CJShell's existing
RunContainerHost. This is a scoped [Issue 11](https://github.com/JTCAO515/G2C/issues/11)
slice, not full message-send, provider, login or device acceptance.

## #167 DEBUG Simulator cancellation

The App may supply `RunCancellationTransport.development` for the explicit loopback
session. This is a separate capability for `POST /v1/run-cancellations`; it does not
open the shared MESSAGE transport or any PUT/other write. Release and physical
devices cannot construct the live capability. Existing callers default to reads only. Unbound transport sends are rejected; the
model carries its original-source/selection validator through the last outflow
check. Every source selection must observe its original RUN before cancellation
becomes available, including reselection after an unknown outcome.

`prepareCancellation()` captures one original source and retires old stream work.
`performCancellation()` validates the original cancellation receipt and then reads
its protected snapshot before publishing a terminal. Existing terminal states stay
truthful; unknown exchange retains partial text and requires an original read, while
access/integrity failures withhold it. The operation does not undo prior effects or
claim physical abortion of an already-started provider call.

The development App opts into following a newly accepted original message. Before
any stream progress, an initial 503 can receive at most three GET attempts under
the same source/session. This only bridges worker RUN-row startup; other errors,
existing stream interruption and source changes are not automatically retried. Normal
read-only hosts keep explicit selection/read behavior. Native validation uses the
formal local API and real worker with controlled FakeProvider; real budget exhaustion
remains pending B-line #170 and cannot be replaced by a display-byte-limit test.

## P2c: explicit SSE read and resume

`prepareStream()` captures the same one-use original source/session work as
`prepareRead()`. `perform(work)` uses the existing no-redirect transport to GET
`/v1/run-events`, with the original message ID and received UTF-8 byte offset in
`Last-Event-ID`. The read path introduces no message POST, model call or automatic reconnect.
Server cancellation is only the separate #167 capability above. The App's default unconfigured host stays unavailable.

Frames are bounded by the endpoint response-byte limit; text has its own byte bound.
Split Unicode, CRLF, duplicate fields, bad offsets, invalid status, extra JSON keys
and truncated events are handled explicitly. A disconnected/nonterminal stream is
unknown; valid received text remains visibly partial until an explicit continuation.
Source/account/session invalidation removes that text and rejects late chunks.

SSE does not contain a RUN event highwater or a complete original receipt binding.
After terminal EOF, the existing protected snapshot GET must match the streamed text
and status before the model displays a final canonical snapshot. No synthetic
highwater, optimistic completion or new formal state is created.

Current dependencies are the `ios/` root package and sibling modules (ADR-0004).
The fixed-export instructions below are historical; they are not the current entry.

```sh
DEVELOPER_DIR="$DEVELOPER_DIR" swift test --package-path ios/Modules/CJRunClient
```

Real local HTTP/API/PG verification (set `DEVELOPER_DIR`, `CJ_PG_BINDIR`, and an
external `CJ_SWIFT_SCRATCH` directory first):

```sh
uv run --locked python -B scripts/check_run_stream.py --scratch-path "$CJ_SWIFT_SCRATCH"
```

The harness creates and tears down a private PostgreSQL cluster and a loopback-only
API, uses disposable development identities and FakeProvider, then runs the Swift
client's real GET path for Chinese/English and foreign-user refusal. It never reads
Keychain or calls a cloud/model service. `liveLoopback` is explicitly skipped in the
ordinary unit-test run; CI runs the RUN unit suites, not this opt-in PG harness.

## Fixed inputs and preparation

- Base: `000b6d4dd089594a61b32028aa2f60ff2ff3460d`.
- Dependency-only prep: `c4e59dc` imports exactly three CJ009-owned files from
  `540da02a335e96e98917ffd3d94a395f8ca2d892`: CJMessageClient Package.swift,
  scripts/prepare_generated.py, evidence/generated-pin.json. Their bytes are unchanged.
- Official root source: `c02cf08e52a0d8ffc2fefac99226654a7e01539c`.
  Only official shared export at
  `../CJMessageClient/.generated/c02cf08e52a0d8ffc2fefac99226654a7e01539c/CJFoundation`
  is consumed. Prepare it with the imported CJ009 script and the fixed root repository:
  `python3 ../CJMessageClient/scripts/prepare_generated.py /path/to/cj-005-foundation`.
- RUN producer: `414e5c19d8470ac2fbdc645ddfaedeee8dd6039f`; contract evidence is
  root `backend/cj_api/RUN-DISPLAY-WIRE.md` and RUN `contracts/run/DISPLAY-SNAPSHOT.md`.
- Existing SessionLifecycle/SessionOperation and MessageEndpoint/NoRedirectTransport
  remain their owners' public boundaries. No new JWT, principal/scope mapping,
  permission provider, token key, persistent queue, pending store or Keychain purpose.

Only this module's files are product changes. Other client/host manifests remain
untouched; full App same-pin composition belongs to Main/CJ006 after review.

## Host consumption

Import CJRunClient, CJAPI, CJSession and CJMessageHTTP. Construct `RunDisplayModel`
with an approved `MessageEndpoint`, explicit positive message-ID/text byte bounds,
existing `NoRedirectTransport`, and an async credential callback taking the captured
`SessionOperation`. Obtain current credentials through the existing accepted session
bridge; do not derive an identity from a bearer or create another auth provider.

`RunDisplaySource(receipt:session:operation:isCurrent:)` takes the canonical public
`Components.Schemas.MessageReceipt` obtained from accepted MESSAGE receipt recovery
or already accepted host context. Do not construct it from user text, an arbitrary
message ID, a local unconfirmed action or a RUN-created assumption. The constructor
checks structure, not provenance or authorization. The trusted host is responsible
for providing the original receipt and current source ownership.

The synchronous `isCurrent` callback must check the captured source/receipt ownership,
current admission, host generation, exact selected original message, and foreground
lifecycle. A new selection, account/auth change, source retirement or background must
synchronously call `model.invalidate()` before later work can run. Reappearance must
bind a newly checked source with `model.select(source)`; it does not auto-read.
Session ownership is independently checked before and after host callbacks/awaits.
Callbacks may reenter selection/preparation; an old operation cannot clear a new one.

Always capture work in the synchronous action, before enqueueing a Task:

```swift
let work = model.prepareRead()
Task { await model.perform(work) }
```

`RunDisplayView(model:language:)` embeds the existing model, offers an explicit
read-original button and uses this exact pattern. No new navigation or Tab. It also
invalidates on disappear/non-active scene phase. Host lifecycle invalidation remains
required even when the view is absent. `state` checks source ownership on access.
This component renders text verbatim, including Unicode/Markdown-looking text;
rich rendering belongs to later host composition.

## Read semantics

The only operation is official generated `getRunDisplaySnapshot`:
GET `/v1/run-display?message_id=...`, no body, exactly one original UTF8 query value.
Response uses official generated models, bounded body collection, generic duplicate
JSON-key rejection, single UUID X-Request-ID matching body bytes, and no-store.
The local generic JSON guard is adapted from CJMessageHTTP's private syntax checker;
it contains no second wire schema. Transport/decoder errors are sanitized because
generated ClientError may retain the Authorization-bearing request.

All original conversation/generation/message/run/sequence references are checked
byte-exactly where textual. Event highwater is independent of message sequence and
is not a model version. Only completed is complete; all other six statuses are
partial. Queued with actual empty text shows waiting. Seven statuses are rendered
in English and Chinese. Snapshots replace one body, never append a second answer.
Duplicate snapshots are idempotent. Lower highwater, same-highwater contradictions,
non-prefix text or revival of an observed terminal state are unavailable. Those
checks follow the fixed producer's append-only/terminal invariants; they are not a
claim that the network result is the latest state or atomic distributed revocation.

Missing records/snapshots, bad headers/format, 401/413/503/429, cancellation, local
bounds and uncertain exchange are unavailable/unknown. No fabricated empty queued
record, fallback answer or successful completion. Prior bytes remain only in this
session's private comparison state; a failed read does not publish them as current.
Explicit subsequent reads query the same source only; there is no automatic retry,
new message/RUN/dispatch, SSE/cursor/polling, worker/provider, server cancellation or
EOF-as-completion. Snapshot/receipt/text are not logged, encoded for persistence or
included in debug descriptions by the module.

## Verification

From this directory:

```sh
swift test --skip-update
xcodebuild -scheme CJRunClient -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/ios CODE_SIGNING_ALLOWED=NO build
```

See [evidence/REPORT.md](evidence/REPORT.md). Synthetic interceptor/session evidence,
unsigned module compilation, real service, App and physical device claims are separate.

## #212 original-message draft result

The development App opts into `readsDraftStatus`; existing consumers default to
false. After a validated original RUN snapshot (including confirmed stop), one
bounded `GET /v1/run-draft-status` reads `RUN-draft-status.1` with the same receipt,
credentials and source/session epoch. Its six outcomes appear separately from
answer text and canonical RUN state. The read's own RUN status remains visible.
No unknown result automatically retries or enables a write. Non-200, offline,
unknown enum, mismatched original references, invalid trace/cache/JSON or stale
source fail closed. Server 401/403 also retire the private answer. v2 generation
alone does not activate a v2 consumer; an unsupported v1 outcome remains unknown.

On iOS, the draft-result sentence uses a multiline UILabel with the full SwiftUI
Dynamic Type mapping and measured available width. A retained iOS17.5 typography
diagnostic found clipping reports at accessibility5 for the same SwiftUI Text,
while the UILabel comparison avoided them; this is a bounded observation, not a
general framework diagnosis. The native suite checks the combined accessible
heading, result and RUN state and preserves every audit failure.

## #167 budget read preparation

`draftStatusVersion: .v2` explicitly selects the frozen v2 original-message GET;
there is no fallback to v1 or automatic read retry. The default remains v1 and
the App composition still uses that default until the formal B-line host route
is delivered. Generated v2 types and synthetic client tests do not activate it.

V2 shows only the persisted `budget_exhausted_stage` (answer/draft); none, generic
failed and unknown do not imply budget exhaustion. Original RUN state and text
remain independent, including cancellation/unknown after a historical reason.
All source/session and receipt/header/body checks are shared with v1. No write,
quota setup, ledger access or new model request is introduced. Actual budget L1
remains UNRUN until #170 formal host integration is available.
