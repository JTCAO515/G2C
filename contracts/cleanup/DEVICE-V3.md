# CLEANUP-DEVICE@3 — original ACK recovery and complete known journal scopes

Additive frozen interface for #27/#24. V1/V2 documents and original target sets
remain unchanged. This document freezes fields; implementation/native acceptance
requires its actual evidence. CLEANUP-API@1 account prepare/confirm/progress stays
at the existing /v1 routes and may reference an enrolled V3 binding.

## Original registration and call recovery

All POSTs are strict UTF8 JSON application/octet-stream, exact listed fields plus
`version:"CLEANUP-DEVICE@3"`. Duplicate/extra fields, unknown versions, owner/path
selectors and unexpected queries reject. Original action IDs/bytes/hash are
durable on the App **before** dispatch. IDs/digests retain API-V1 bounds.

| Method | Path | Credential | Fields/query |
|---|---|---|---|
| POST | /v3/cleanup-devices | Bearer current account | action_id, device_id, state_ref |
| GET | /v3/cleanup-device-registrations | Bearer current account | action_id, input_sha256 |
| POST | /v3/cleanup-device-calls | Device original binding | action_id, binding_id, reason |
| GET | /v3/cleanup-device-call-actions | Device original binding | action_id, input_sha256 |
| GET | /v3/cleanup-device-calls/{invocation_id} | Device original binding | no body/query |
| POST | /v3/cleanup-device-receipts | Cleanup original receipt capability | action_id, operation_id, invocation_id, binding_id, request_digest, outcome |

`input_sha256` is SHA256 of the **exact original POST UTF8**, including version,
whitespace and escapes. It is not request_digest (the server-issued call digest).

Registration POST returns the existing registration payload with version3:
binding_id, device_id, state_ref, scope_digest, device_token, server_time,
business_access:not_granted. Registration GET returns
`{version,action_id,input_sha256,registration:<that payload without request_id>|null}`.
It looks up only the current account's original action and exact input digest;
it neither inserts a binding nor permits a replacement registration. Keep ordinary
SDK access until original enrollment is known and its limited credential is safe.

Call POST and action GET return
`{version,action_id,input_sha256,invocation:<original call result>|null}`.
A successful POST has a non-null invocation. The call result is unchanged:
call, request_digest, state, receipt_digest, receipt_token. Its call carries
version3, original operation_id/invocation_id/binding_id/scope_digest/state_ref,
reason, exact targets and business_access:not_granted.

Creation binds the client action/digest and server invocation atomically before
ACK. Repeating the same action/bytes returns that original invocation; changed
bytes conflict. An account fence that appears later never retargets a prior action.
GET is read only and never creates, dispatches or expands an invocation. Null is
only absence observation, not permission to resend, mint an ID or erase files.
After an uncertain write, query the original action and hash until its result is
known. Read errors/expired credentials remain UNKNOWN/unavailable.

An active account operation at first call creation supplies the original account
ID and reason account_cleanup. Otherwise the server owns the stable device-only
invalidation operation. No App operation ID is minted. session_invalid requires
explicit identity refusal; 503/network/UNKNOWN do not authorize cleanup or renew
offline read. offline_expired targets only offline-trip, offline-write-residue and
offline-key-keychain, including the own anchor/known temporary ciphertext scope.

Reports use the original receipt capability and unchanged aggregate outcomes.
confirmed requires actual verification of every target in that exact request;
partial/uncertain work is unknown. Terminal failed/confirmed bytes cannot change.
The original invocation GET recovers a lost report ACK. Protocol, binding, subject,
operation, invocation and digest must all match; no business access is restored.

## V3 target additions and exact native scopes

V3 includes all13 V2 targets plus these6. Actual source is main b398a80c's App
roots, store implementations and key namespace; no future JT Agent/WIP store is
pre-registered. A owns native resolution and physical erasure.

| Added target | Exact provided scope |
|---|---|
| device-cache/memory-history-pending | M.history-v1 and M.history-v1.CJMemoryHistoryRejectionsV1 |
| device-cache/trip-scoped-pending | T.ScopedOriginals and T.ScopedReceipts, as one paired native operation |
| device-cache/needs-planning-pending | T.NeedsPlanningOriginals and T.NeedsPlanningReceipts, as one paired native operation |
| device-cache/trip-key-keychain | exact localTripPendingV1 key UUID, after base/manual/rejection/scoped/planning journals verify empty |
| device-cache/offline-key-keychain | exact localOfflineTripSnapshotV1 key UUID after snapshot/known temporary ciphertext verifies empty |
| device-cache/offline-write-residue | only the known writer's .write-UUID state inside the exact captured G2COfflineTrip/E/A directory; unsupported/unknown entries remain unknown |

M=G2CDevelopmentMemory/E/A and T=G2CDevelopmentTrip/E/A; E/A come from A's
verified namespace, not an input path. Existing targets include their accepted
store-owned exact descendants: Trip base plus CJTripManual/rejections; Memory
manual/lifecycle/typed own rejection and typed-management roots; Needs own
rejections; both independent Feedback Answer/General stores. offline-trip covers
the fixed snapshot and own protected Offline anchor. V3 explicitly lists them;
it never authorizes prefix/sibling wildcard deletion or reinterpretation of a
different store's AD/key. The App verifies recorded/current namespace, generation,
key UUID/state and directory identity before acting.

Shared keys clear only after **all** their listed journals are verified empty,
using exact expected UUID/service/slot/accessGroup. Unknown entries/replacements/
links/clear ACKs stay unconfirmed; key invalidation alone is not physical erasure.
Minimal restricted-progress credentials have their separate actual App lifecycle;
the pending #443 WIP storage is not an invented user-content target here.

## Examples and negatives

Registration: `{"version":"CLEANUP-DEVICE@3","action_id":"register-3","device_id":"device-a","state_ref":"0000000000000000000000000000000000000000000000000000000000000000"}`.
Before receiving a binding ID, GET the original action and SHA of those exact
bytes; the server returns its real original binding/capability or null.

Call: `{"version":"CLEANUP-DEVICE@3","action_id":"clear-3","binding_id":"server-binding","reason":"session_invalid"}`.
Its original action GET works without knowing operation/invocation IDs after a
lost first ACK. A later account fence does not change this original result.

Wrong digest for an existing action conflicts; other owner/binding never reads
that action. V1/V2 body/binding on V3 rejects, as do supplied targets/path/scope.
Unknown/failed lookups never become confirmed. Other devices/backups remain
explicit obligations; a current-device report is not server physical attestation.
