# CJFeedbackClient

P2 follow-up to69d: [draft-reentry repair](evidence/draft-reentry/REPORT.md).
Accepted callback edits now retire frozen preparation before any dispatch. Original
69d evidence and its independent FAIL remain historical; independent re-review is pending.

Embeddable iOS 17 / macOS 14 Feedback domain client and English/Chinese SwiftUI
form for Issue15/CJ023. Ordinary construction remains read-only. The explicit
`FeedbackClient(development:...)` factory supports FEEDBACK@1.0 only on a DEBUG
Simulator loopback endpoint, with the current canonical SDK session and encrypted
pending store. Release/remote activation is rejected. No second SDK or wire/date
parser is introduced.

## Current App composition (#430)

The account root opts in with `G2C_DEV_FEEDBACK_PROFILE=feedback-v1`. The real Run
entry captures its sealed accepted MESSAGE receipt and same session operation;
only the user's association toggle adds message/run refs. Memory uses general
`references=[]`. Both editors start empty and own distinct clients/presentations
and pending directories, with the canonical `localFeedbackPendingV1` device key.
Account/selection changes fence old work; a language change preserves the original.
Only a verified receipt for every durable pending action enables the explicit
“Describe another problem” action. UNKNOWN and null queries never unlock it.

The protected server-only locator is developer evidence, not a new diagnostic
input field. App receipts show the historical source observation; missing external
model/rule/tool details remain unavailable. Successful submission does not claim
repair or training. Account cleanup of feedback pending files is tracked in #27;
this connection does not claim the original cleanup operation/device bridge.

## Historical isolated inputs and preparation

- Clone base: `eeb9b9cdf11ff619494a7afd5cbef2833501df7d` from read-only cj-publish/Go2China.
- Shared SDK consumer: `514e0e3a80bd9a3e34248122915d52c86ee46230`, imported unchanged
  as `888a402` in `ios/Modules/CJMessageClient/**` (including its preceding NEEDS export).
- AUTH: `f2c01d7e9e3292b7d8bcc207b965bf6a36cec96c`, imported unchanged as
  `c755f9f8bb405e89ff458939ac4608fd52ceb1b8` in `ios/Modules/CJAuth/**`.
  Imported producer evidence is not new client evidence or a claim of platform testing.
- Product diff starts at **c755f9f8bb405e89ff458939ac4608fd52ceb1b8** and contains
  only this module. Other modules, root API and root/shared locks remain untouched.
- Sole generated API: `201156c9bf9850f9b8e87dc1f986452ce1ae789f`, exported by the
  shared module's existing prepare_generated.py; path
  `../CJMessageClient/.generated/201156c9bf9850f9b8e87dc1f986452ce1ae789f/CJFoundation`.
- FEEDBACK producer contract `cf48196e5eb5012630603172951d5c75a46adec4` and root
  wire evidence `81a2f245e03f795aa651e325e0d97a6c49e61628` were read at fixed heads.
  Independent producer/consumer gates remain separate; this module does not freeze them.

## Host integration

Use one `FeedbackPresentation(client:)` owner for each feedback surface lifetime,
then embed `FeedbackView(model:language:)` in either the Answer entry or Memory
entry. A language change must preserve the model. The initial problem/expectation
are empty; the view never imports a transcript. The trusted host supplies a
`FeedbackContext(messageID:runID:)` only for the actual current application context.
The user opts in to association. A general submission uses an empty references array.
Only message and optional run exist in this API. IDs retain exact UTF-8 spelling;
client-side references are not a claim of server-verified ownership.

The host supplies a `FeedbackBinding` (environment/account/generation/selection),
existing canonical `SessionLifecycle` and current `SessionOperation`, current
credential callback, configured `MessageEndpoint`, explicit `NoRedirectTransport`,
and `FeedbackPendingStore`. There are no default users, endpoints or credentials.
`FeedbackBinding` never becomes a server owner or wire field. On any host account,
environment, generation or source-selection transition, call `replace(binding:context:)`
synchronously **before** scheduling new work. A changed binding is not permission
to query a different account's original action.

Every UI event prepares opaque work synchronously, then creates its Task:

```swift
if let work = model.prepareReload() {
    Task { await model.perform(work) }
}
```

The view already follows this pattern for submit/query/reload. Public low-level
consumers likewise capture `client.begin(binding:)` before Task creation and pass
that original operation. Work is instance/lifetime/selection bound and one-use in
the presentation. Reentrant host callbacks are checked after returning; stale work
cannot select/query/clear the new UI state. Cancellation settles busy to unknown or
unavailable while retaining frozen text and recovery information.

The ordinary public constructor cannot enable POST and retains voluntary editing.
The explicit development factory above uses the canonical no-redirect bounded
transport, permitting only the official feedback POST at its exact endpoint.
Internal intercepted transports remain non-network test seams. Original reads
require configured resources and existing encrypted pending. Current App builds
use the accepted canonical sibling API/SDK graph; the isolated 201156 inputs above
are historical and are not a second live SDK.

## Original action and recovery

`prepareSubmit` freezes a UUID action ID, official generated FeedbackAction encoding
and exact original bytes before queuing work. The client persists an immutable
encrypted record before any credentials/network call. It permits one attempt per
record. Repeated calls, lost ACK, cancellation, null, invalid responses, 409, absent
key and uncertain append never authorize a replacement ID or resend. Reopening
uses only `queryOriginal`, under the original trusted namespace and key ID.

Receipt validation checks original action ID plus persisted `input_sha256` against
the locally frozen bytes. `source.message_input_sha256` identifies the **message**
input and cannot substitute for the feedback hash. General feedback requires an
explicit null source; linked feedback requires the original exact message and any
supplied run. Generated non-null oneOf fallback values are rejected. Official
`Configuration.memory` handles UTC whole/fractional timestamps. No custom parser.

The source section is only the server's original read-time observation, retained on
original query. The client never reads RUN again to update it. Status/event progress
do not prove successful tools or imply model/rule version, usage, duration, failure
stage or ongoing source accessibility. The view explicitly says those fields were
not provided. Success says only “Feedback submitted.” / “反馈已提交。”

## Storage and privacy

Host creates/owns a canonical private directory (0700, no symlink) and supplies the
existing original key ID/provider with purpose `localFeedbackPendingV1`. The store
only looks up that key. It never creates, rotates or clears a key; missing/unknown
is unavailable. AUTH environment/account/purpose/key ID must match. AUTH's original
creation/clear reconciliation remains the host's existing responsibility.

AES-GCM authenticates environment/account/purpose/key ID. Original records use
exclusive 0600 creation, fsync(file/directory), no-follow reads and single-link files.
A retained directory descriptor is checked against the canonical path. After the
last key/binding resource callback, callback-free checks compare canonical directory
and exact original ciphertext before outflow or settlement. Full pending inventories
are fenced too. This handles the tested callback/await boundaries; it does not claim
protection against arbitrary concurrent same-UID filesystem tampering.

Original pending remains after acknowledgement/conflict. There is no deletion,
overwrite, automatic retry or cleanup API. Host-selected count/byte limits fail
closed; retention/cleanup/account deletion integration remains unconfigured. The
client stores original text once, plus action ID/hash, encrypted locally. The server
owns minimal diagnostic/source data. Voluntarily pasted text is not automatically
redacted; the form asks the user to omit secrets. No body, hash, URL, credential or
private exception logging is implemented. Generated transport errors are sanitized
before UI publication.

## Verification

See [evidence/REPORT.md](evidence/REPORT.md) for fixed sources, commands, failed runs,
passed targeted scenarios and explicit UNRUN gates. Do not treat local tests or
unsigned compilation as App/real-account/service/device acceptance.


## M3 local account-cleanup primitive (#439)

`clearLocalFiles()` retires the original store and physically erases only its
pending journal family. Memory's four public store types each own
their separately constructed root; callers must retain and invoke all provided
stores. Feedback Answer and General are separate roots and both require cleanup.
The method never queries/decrypts a record or accesses/creates/deletes a key.
Existing ciphertext, action IDs, raw UTF-8, receipt/query and unknown-write rules
are unchanged before explicit cleanup.

Known adjacent directories are captured with retained descriptors at construction,
or registered only when that store creates them. Renamed/replaced/missing captured
directories, independently appearing sidecars, unknown filenames, subdirectories,
symlinks and hardlinks refuse cleanup. Complete metadata preflight precedes the
first unlink; failure retains a retired store and retry uses the same original
targets. Regular account-owned ciphertext may be erased even when its content or
read protection is unusable, as in #421; this does not make it readable.
No recursive or sibling-prefix deletion exists. A successful retry verifies empty
original directories and fsyncs them; it never reports server/backup/device-wide
completion.

The host still must fence every old client/SessionLifecycle before cleanup,
prevent constructing replacement writers, then clear the exact key only after
all its provided stores are verified empty. Other independent instances are not
a global revocation mechanism. Original account operation/device-call/receipt,
Keychain clearing, signed API/PG/native composition and physical-device behavior
are separate #27 acceptance. In particular the history roots introduced by #437
require B's additive device target version; DEVICE@2's frozen targets are not
expanded by this local API. This primitive alone does not open an App factory or
mark #24's original-account-operation box complete.
