# Per-item pause/resume consumer — independent SDK20aa candidate

Base `1734971c7606a346cfb73609eab6a06c16e8791a` remains the fixed f87 candidate for
in-flight App integration. This follow-up changes only CJMemoryClient and does
not upgrade CJShell or another consumer. New SDK identity:
`20aa50ed5c8449e6026155a6151f22041dee7fd4`, exact shared input
`cc9e2c3ba1fb8fe7582e5e4664a924b1c6b93f71`. No shared tracked file was imported or
edited. Official export/old 26 paths and 93 schemas/unchanged SDK lock/date helper:
[evidence/management-sdk-input.json](evidence/management-sdk-input.json).

## Interface and host restrictions

The existing official reader has both `MemoryItem.version` and
`MemoryItem.command.source_version`, plus `command.source_id`; no missing expected
version field or fabricated default is needed. `managementSelection(itemID:binding:)`
can capture only a validated item already returned by this client's actual list or
detail operation. The public selection has no public initializer, decoder or
caller-supplied version path. It is tied to this client, original binding and exact
read stamp. A new accepted read retires the old stamp even if its version is equal.

`applyManagement(.pause/.resume, selection:binding:)` is explicit user intent; the
source/item revisions are taken from that sealed selection. A disabled label is
never permission to resume. Root's fixed CJ019/CJ011 lifecycle service verifies
source approval, prior pause provenance, expiry and conditions. The client sends
no source approval, owner, confirmation, text or new source data.

Public live composition remains **unavailable** for both new management operations,
before credential/journal/network access. `managementAvailable` is false for the
public initializer; adding a journal does not activate it. Only the existing
package-internal intercepted-test initializer can exercise the action flow. No
public enable flag, callback permission or new live transport factory is added.
The root `create_memory_management_app` factory is also CLOSED. Root/SDK independent
gates remain pending; this source does not change them.

The root wire explicitly has NOT established cohosting old MEMORY426 reads with
new MEMORY0045 lifecycle operations. The future host must resolve that fixed-pin
compatibility and get accepted root activation/composition before live use; mock
reads and this client cannot supply that proof. Never upgrade the ongoing f87 App
graph merely to consume this independent candidate.

## Original action and query-only recovery

The official generated MemoryManagementAction is encoded exactly once, with five
keys: action_id/operation/item_id/expected_version/expected_source_version. Original
UTF8, generated action UUID, exact item ID, source ID metadata and expected SHA256
are persisted before async credentials/dispatch. Request body sends those same
bytes; NFC/NFD IDs are not normalized. There is no resend or replacement-ID recovery
API. Any unresolved journal action blocks a new management action, including after
reopen and a null GET response. A consumed read stamp cannot generate another action.

Use a **separate private directory** for MemoryManagementPendingStore. It uses the
existing CJMessageKeys localMemoryPendingV1 namespace and expected key ID through
lookup only. AES-GCM AD is
`CJMemoryManagementPending|1|<environment>|<account>|local-memory-pending-v1|<keyID>`.
Same scope/key does not make save/lifecycle ciphertext interchangeable. No Message
ledger, plaintext fallback, key creation/clear/rotation, token key or new purpose.
The shared private file engine preserves manual-save AD `CJMemoryPending|1|...`,
filenames, old UUID reads and encoded MemoryPending layout; no migration occurs.
It retains exclusive immutable 0600 writes, directory/key callback fences, sync,
limits and fail-closed encrypted reopen. It is not arbitrary same-UID race or
anti-rollback proof; live writes stay closed.

Supply explicit request <=32768 and response <=65536 byte limits, positive journal
record/count limits, the trusted current binding/credential callbacks and original
expected key ID. Missing configuration or public live composition rejects. The
same binding/selection/request-generation/cancellation fences surround credentials,
transport awaits, durable-original rereads and settlement. Management responses
require no-store, matching body/header request_id, bounded strict JSON and no
redirect. Errors, malformed non-null unions and failed reads never become null.

`managementPending(binding:)` enumerates the original encrypted records after
reopen. `queryManagement(actionID:binding:)` accepts only an exact stored original
ID, using freshly obtained credentials in the original Memory scope. GET null is
not observed, never noncommit or permission to resend. Queries do not call the
save ledger or dispatch apply.

Receipts must match original action/item/hash, fixed provider's expected version+1
and requested pause→disabled/resume→active result. The fixed provider increments
version in the same CAS transaction. Return type is deliberately
`historicalReceipt`: no receipt overwrites list/detail state or advances current
eligibility. A delayed pause receipt remains historical after resume. Refresh the
current reader for current state; source/context eligibility still belongs to the
service. Text editing and promotion of candidate facts are out of scope.

## Embeddable UI

MemoryManagementControls provides bilingual explicit pause/resume confirmation and
same-action query; MemoryManagementRecoveryView displays a stored action after
reopen with only its original-ID query. They are keyed by read/action/binding
identity, check current binding before/after async work, and explain that source
conditions are verified by the service. Default product controls and queries show
unavailable, never success. Historical receipts say to refresh current state. No
Shell/container/account/language entry was changed. Host must retire selection
binding on row/account/session changes, clear old snapshots, and use these exact
client-created selections; UI state is not backend authority.

## Author evidence and remaining gates

Private fixed graph under this module's `.build/management-20aa-09facf21` uses exact
shared cc9e, canonical AUTH b24cc77 and official SDK20aa, plus candidate source
hashes. No manifest rewrite or sibling tracked edit. [All checked inputs and one
canonical SDK path](evidence/management-consumer-provenance.json).

- PASS: 41 related module test methods: prior 30 regressions plus new 11 management
  cases, necessary because the two journals share the accepted file engine.
  [Full related run](evidence/management-module-tests.txt).
- PASS: final 11 management methods after adding recovery UI; prior unchanged
  business results reused. [Final run](evidence/management-final-tests.txt).
- PASS: actual single-20aa consumer graph and unsigned iOS Simulator SDK module
  compile including the new views ([build](evidence/management-ios.txt)).

New cases cover exact five-key UTF8/hash/source-version capture (including source
version7), accepted-read/client/selection fences, durable originals before lost
reply, reopen/null/no resend, mismatched hash/non-null refusal, historical pause
receipt after resume, public unavailability before credential/journal access,
AES-domain separation, actual task cancellation after dispatch, selection change
at credential acquisition, displaced key-lookup directory/no dispatch, and server
resume refusal despite disabled state. Interceptors and synthetic temp files only;
these do not establish actual source eligibility, transaction or platform success.
Full local logs `/tmp/cj011-management-controls.log`, `/tmp/cj011-management-final.log`,
`/tmp/cj011-management-ios.log` retained. One preliminary command ran from the wrong
cwd and executed no tests; its error is retained at
`/tmp/cj011-management-tests-final.log`; corrected runs passed, no assertion weakened.

UNRUN: real HTTP/account/provider/Keychain/PG/device/visual/VoiceOver, actual source
approval/current context, old/new root cohosting, full App/next-answer/I acceptance.
New root/SDK independent gates and original Review/Testing/Publish are separate.
No push/merge/Issue closure, signing/permission/deployment or old-data change.
All earlier FAIL evidence and fixed f87 objects remain preserved.
