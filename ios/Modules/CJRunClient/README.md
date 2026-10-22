# CJ-010 original-run display client

Standalone read-only module for original MESSAGE recovery. This is the scoped client
slice of [Issue 11](https://github.com/JTCAO515/Go2China/issues/11), not its full
streaming/stopping/provider/App acceptance. `CJRunClient` is not connected to CJShell.

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
