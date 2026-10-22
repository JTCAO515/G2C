# CJFeedbackClient

P2 follow-up to69d: [draft-reentry repair](evidence/draft-reentry/REPORT.md).
Accepted callback edits now retire frozen preparation before any dispatch. Original
69d evidence and its independent FAIL remain historical; independent re-review is pending.

Embeddable iOS 17 / macOS 14 Feedback domain client and English/Chinese SwiftUI
form for Issue15/CJ023. Public live **POST is disabled**. No shell integration,
second SDK, handwritten wire/date parser, key provider, service worker or customer
support workbench is introduced.

## Fixed inputs and isolated preparation

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

The public client constructor cannot enable POST. Its UI shows submission unavailable
and retains voluntary editing. Tests use an internal intercepted transport initializer
with synthetic binding and credentials; that seam is not a production authorization.
Original reads require explicit configured resources and existing encrypted pending.
CJ006 owns eventual Answer/Memory integration and coordinated single-SDK App pinning.
Do not combine this 201156 graph with an active d688/9dc graph in the same App.

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
