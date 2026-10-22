# CJ-017 read-only manual preview client

Independent feature module for CJ006 composition. It starts only from CJ015's closed
`AcceptedTripDetailSnapshot` returned by the generated formal `getTrip` read. No
public constructor accepts arbitrary JSON, a claimed accepted version, or a proposal.
It owns an in-memory user-intent draft, not a patch engine or a persistent cache.

Fixed repository base: `33ea117c00f698a29814c60b75337374121f9973`.
Dependency preparation is separate from product changes:

- `36670fc`: exact owner bytes from shared `3090777b4e10a6135823e3342e5e8b6c34aa9e6b`
  and Trip accepted-source `2b2991871ce4e04bd1bfb5a92f3098e01512800a`.
- `e0f9f75`: exact owner Trip c5 pin `f931d5834d8a5162b223a8607b83d27d3639afe7`,
  explicitly delivered by Main. Trip source/tests/lock are unchanged from 2b299.
- Product delta starts after `e0f9f75`, only `ios/Modules/CJManualPreviewClient/**`.
  Do not publish these local dependency-preparation commits over owner integrations.

Only one generated CJFoundation identity exists in this graph:
`../CJMessageClient/.generated/c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a/CJFoundation`.
Recreate it with the fixed shared owner's `scripts/prepare_generated.py` and the
fixed CJ005 repository. No generated code is copied into this module. Root c5 is the
source, while `3485689` is later producer evidence and does not change the SDK pin.
The existing package's direct dependency versions are reused, without new libraries.

## Trusted host integration

Keep the original `TripClient`, accepted snapshot, `SessionLifecycle` and original
`SessionOperation` for this selection. Inject explicit `MessageEndpoint` limits,
trusted credential callback and existing `NoRedirectTransport`; there is no default
URL, credential, session creation/restoration or Keychain access. The host must
synchronously retire the editor and invalidate Trip snapshots at the original
account/environment/session/selection change, including ABA changes. Never re-label
an old snapshot with a fresh binding or a fresh session operation.

```swift
// At an original accepted-detail selection, after its guarded GET:
let editor = try PreviewEditor(trip: tripClient, source: acceptedSnapshot,
    endpoint: explicitEndpoint, session: originalSession, operation: originalOperation,
    credentials: trustedCredentials,
    previewRequestTimeout: explicitRequestTimeout,
    previewResourceTimeout: explicitResourceTimeout)
ManualPreviewView(editor: editor, language: .english) // or .chinese
```

`display()` checks the original Trip source and session and withholds retired
private data. The host still owns replacing the rendered component at lifecycle
changes. The component retires its editor on disappearance. Returned values are transient copies, not authentication/remote-freshness
proofs or permission to persist. Public component text explicitly says protection
unknown, local preview, not saved, and feasibility/confirmation unavailable.

Only title selection, item selection, title/text updates and full item order are
supported. A reorder must preserve every unselected item's original index. No day,
time, place, lock or presumed unlocked state exists. Changing scope resets ordering
and removes deselected edits explicitly. No local diff is manufactured.

For custom UI, call `selectTitle`, `selectItem`, `setTitle`, `setText`, `setOrder` at
synchronous input events. At the original preview button event, **before** Task:

```swift
let work = try editor.preparePreview()
Task { await editor.perform(work) }
```

A preparation owner is reserved before any source callback; nested newer preparation
supersedes an old caller even without an edit/revision change. The old caller throws
`retired` without altering newer work. See `evidence/preparation-reentry/REPORT.md`.

Work freezes the generated request and exact UTF8, original content base64/version,
source and draft revision; it is opaque, redacted, one-use and editor-owned. All
edits (including edit ABA), new preview preparation, cancellation and retirement
invalidate old work. Credential, request-body, transport, response-body and final
host callbacks recheck the original work/session/source after returning. Old
success/error cannot clear a newer draft or operation. Canceled work settles only
its original current work, through a UI-only task with the same captured source.
`cancelPreview()` stops result use immediately; the underlying cooperative network
operation may still finish. No server write is performed by preview.

409 and unavailable/unknown leave the original draft intact. No refresh, rebase,
automatic retry or new business ID occurs. Explicit preview on unchanged draft
reuses identical generated request UTF8. The editor does not fetch a newer Trip or
supply a refresh/reconciliation workflow; host design must preserve/export the old
user intent before intentionally choosing another formal base.

## Consumer validation and limits

The official generated Client, Types and `.memory` codec are used. The transport
allows only the exact preview operation/path/POST and sends frozen generated bytes.
It enforces explicit body limits, rejects redirects, duplicate JSON keys, missing or
mismatched trace/header and missing `Cache-Control: no-store`. Generated models reject
unknown enum/schema fields. A success must also have **actual `can_save == false`**,
LOCAL status, UNKNOWN protection, exact original Trip/bytes/version, identical scope,
and a document matching returned content bytes. Typed item identities, unchanged
unselected objects/positions, requested title/text/order, pending changed text and
empty changed-text evidence are checked. Server diff entries must match their
before/after source values and cover the actual returned changes; original diff
bytes/order remain the display source. This is a minimal consumer consistency check,
not an independent canonical patch implementation or a signed proof of server state.
The source may change after the last observed check; no distributed freshness,
persistent-lock, business confirmation, feasibility or accepted-save claim is made.

## Explicit shared readonly capability

Current fixed combination: consumer `db48855` + shared Host-header repair `94c50ab6650e9defb0f7df6d7ccbb2bff250c947`, imported unchanged in prep `4c4d15a`.
See `evidence/host-fixed-combination/REPORT.md` for narrow combined validation.
The following f4 introduction and its evidence remain attributed to the earlier input.

Shared fixed `f4c17b59213828543cef042d127c56d8467963d8` (parent3090777) supplies
`NoRedirectTransport.readOnlyManualPreview`. It is imported unchanged in local prep
`287db1f`, independently from this module's product delta. It does not change the c5
SDK pin. Independent shared Review/Testing remains a separate gate.

The constructor above explicitly opts in to this capability with positive finite
request/resource timeouts. For **each original work**, the editor invokes the shared
factory with a mandatory validator capturing the actual original Trip source,
SessionOperation, editor lifetime, draft revision and work ownership. That same guard
runs at the shared pre-outflow, post-await and post-body boundaries. No blank host
callback, fresh binding, default URL, credential or save activation is supplied.

The existing `liveTransport: NoRedirectTransport` constructor is retained. If given
the generic default `NoRedirectTransport(requestTimeout:resourceTimeout:)`, preview
POST remains unavailable and the draft stays intact. The opt-in only permits the
exact generated readonly preview operation/path/POST; action/save/PUT or expanded
path/query remain refused. `036de8d` and its original REPORT retain the earlier gate
result. Current consumer evidence is `evidence/readonly-capability/REPORT.md`.

Actual App factory integration remains CJ006's scope and is UNRUN. Opt-in capability
success has only been checked with in-process interception, not actual networking.

There is no save/Proposal/action/confirmation endpoint, pending queue, disk cache,
provider, permissions change, real account, SQL or live network action in this work.
Issue #22 time/lock/save/confirmation/feasibility and real integration I remain open.

## Validation

See `evidence/readonly-capability/REPORT.md` and the preserved original `evidence/REPORT.md`. Reproduce only this module's affected tests:

```sh
swift test --disable-sandbox --package-path ios/Modules/CJManualPreviewClient \
  --scratch-path /tmp/cj017-manual-preview-build
# From this module directory:
xcodebuild -scheme CJManualPreviewClient -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /tmp/cj017-manual-preview-ios CODE_SIGNING_ALLOWED=NO build
```

Tests use generated Client/Types and the closed Trip public preparation/read/access
API to obtain handles. To keep them in-process with zero network, only tests use
Trip's existing internal transport initializer (`@testable import CJTripClient`)
and this module's internal interceptor initializer. No fake accepted handle or
parallel wire decoder is injected. Synthetic session persistence is memory-only.
Producer algorithm, Trip boundary and existing Auth tests are reused, not rerun.
