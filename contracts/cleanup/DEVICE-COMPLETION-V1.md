# CLEANUP-DEVICE-COMPLETION@1

Added bounded read-only representation of an original DEVICE@3 invalidation
call for #27/#24. DEVICE@1/2/3 bodies, target lists, credentials and existing
routes are unchanged. A remote device need not possess the initiating device's
account progress token. This is still only its own binding's call/query; it is
not a generic account-operation progress interface.

`GET /v1/cleanup-device-completions/{original_invocation_id}?request_digest=<original_call_sha256>`
uses `Authorization: Device <original_device_token>`. No other query, operation,
owner, scope or binding selector is accepted. The server resolves the immutable
call from that credential's subject/binding and verifies its exact original
descriptor/hash, protocol, invocation and authenticated original receipt. An
arbitrary operation ID or another binding's call is never visible. Progress,
receipt and ordinary Bearer credentials do not authenticate this route.

Response (JSON <=4096 bytes, no-store) has exactly:

- `version: CLEANUP-DEVICE-COMPLETION@1`, generated `request_id`.
- Original `operation_id`, `binding_id`, `invocation_id`, `request_digest`.
- `reason: account_cleanup | session_invalid | offline_expired`.
- `device_state: pending | unknown | failed | confirmed` and
  `receipt_digest: null | original_receipt_sha256`.
- `content_status: not_applicable | in_progress | unknown | failed | blocked | complete`.
- `registry_digest: null | original_frozen_registry_sha256`.
- `control_record_protocol: null | CLEANUP-CONTROL-RECORDS@1`.
- `complete_scope: frozen_online_domains_only | original_device_action_only`.
- `business_access: not_granted`.

For account_cleanup, content status comes from the exact linked original
retirement operation. Complete requires its actual confirmed online target
receipts and atomic original domain results, no unresolved account gate, the
same original/current registry and independent inventory, and the active
retirement fence. The initiating account binding may differ from this remote
device's binding; no other device's state, user content, scope or credentials
are returned. control_record_protocol is nonnull only when that original
operation explicitly froze the complete registered control-record profile.

For standalone invalidation/expiry, content_status is not_applicable and both
registry/control protocol fields are null. A later account fence does not
redirect the old call or change its original reason/operation. Device confirmed
alone never implies account content complete.

The read uses a single repeatable-read, read-only private-PG snapshot. It does
not audit/latch state, create/retry/resume hooks, change receipts, mint a token,
rotate membership or invoke a provider. Registry drift during projection,
unavailable/corrupt evidence or expired credentials withhold the result. A
valid result is only an observation; finalization requires the additional
native ownership/record checks in CONTROL-RECORDS-V1.md.

Positive: remote V3 binding receives an original account-cleanup call after
retirement, reports its actual native outcome and reads the same call's online
completion evidence without a progress token. A verifies the returned receipt
digest against its own acknowledged confirmed request before finalization.

Negative: confirmed device + pending/UNKNOWN/failed/blocked account content, or
a null control policy, never proves control-record finalization readiness.
Wrong binding/hash/purpose/key, expiry/tampering, a different original call,
corrupt receipts/results or a changed registry cannot produce complete evidence.
No result claims backup, provider retention, all-device erasure or native control
record removal; those remain their original independent evidence layers.
