# CLEANUP-DEVICE@2 — existing Memory and Needs device stores

Additive frozen version for #27/#24. `CLEANUP-DEVICE@1` and `CLEANUP-API@1`
retain their original fields and semantics. This document freezes the interface;
implementation/native consumption are accepted only with their actual evidence.

## HTTP and credentials

The four device routes are versioned separately:

| Method | Route | Credential | Exact request fields, besides version |
|---|---|---|---|
| POST | `/v2/cleanup-devices` | Bearer, current ordinary account | action_id, device_id, state_ref |
| POST | `/v2/cleanup-device-calls` | Device, original registered binding | binding_id, reason |
| GET | `/v2/cleanup-device-calls/{invocation_id}` | Device, original registered binding | no body/query |
| POST | `/v2/cleanup-device-receipts` | Cleanup, original receipt capability | action_id, operation_id, invocation_id, binding_id, request_digest, outcome |

Every POST has `version:"CLEANUP-DEVICE@2"`, strict UTF8 JSON with no extra or
duplicate fields, using `application/octet-stream`. Input bounds, ID/digest
encoding, credential purposes, error/UNKNOWN semantics and response envelope are
those in `API-V1.md`. Registration response `version` and persisted `call.version`
are V2. Other response fields are unchanged. V1 routes reject V2 bodies/bindings,
and V2 routes reject V1 bodies/bindings; version is never inferred or upgraded.

Use a fresh explicit registration action to enroll the same device/state in V2.
The old binding and its original call bytes remain V1. Exact same action/bytes
replays the original registration; changed bytes conflict. A device/state may have
both version bindings. One original confirmed report covers only the targets in
that persisted call, for that device ID and exact state_ref. It cannot confirm a
target absent from the call. A V2 report can cover the same device/state's older
binding without issuing another physical deletion; other device/state groups
remain pending. This remains an authenticated device report, not server physical
attestation or proof about unregistered devices.

Account creation/confirmation/restricted progress continue using CLEANUP-API@1
at their V1 routes. A V2 binding_id can be used in the original account preparation.
Retirement links device calls to that active **original** operation. Progress
credentials still cannot regain business access, dispatch a model or retry erase.

`session_invalid` requires an explicit identity refusal. HTTP503, network error,
timeout, uncertain membership and UNKNOWN never authorize cleanup or renew offline
read. `offline_expired` still targets only `device-cache/offline-trip`.

## Exact target set

Account cleanup and session invalidation include the seven V1 targets plus:

| Target | Existing main storage; A owns exact native resolution |
|---|---|
| device-cache/memory-manual-pending | G2CDevelopmentMemory/<environment>/<account>, MemoryPendingStore |
| device-cache/memory-lifecycle-pending | sibling `<account>.lifecycle`, MemoryManagementPendingStore |
| device-cache/memory-typed-pending | sibling `<account>.typed-v2`, TypedMemoryPendingStore |
| device-cache/memory-key-keychain | canonical localMemoryPendingV1 key shared by the three journals |
| device-cache/needs-pending | G2CDevelopmentNeeds/<environment>/<account>, NeedsPendingStore |
| device-cache/needs-key-keychain | canonical localNeedsPendingV1 key |

These are existing stores in accepted `DevelopmentTripHost.swift` and canonical
`MessageKeyInterfaces.swift`. They are not new filesystem paths supplied by the
server. Environment/account/generation/key-state must come from A's captured
trusted namespace; opaque IDs/digests are comparison values. Resolve only known
targets. No parent/root wildcard deletion, sibling account selection or key
recreation after missing/unknown state. A closes writers first, verifies exact
own file/key erasure, then persists/reports the original result. A new actual
journal requires owner registration and a new device version before activation.

The aggregate `confirmed` report means every target in this exact invocation was
actually verified by A's native primitives. Partial/uncertain erasure reports
`unknown`; it cannot confirm an unattempted target. Original request digest binds
the full version/operation/invocation/binding/scope/state/reason/target bytes.

## Positive and negative examples

Positive registration:
`{"version":"CLEANUP-DEVICE@2","action_id":"register-v2","device_id":"device-a","state_ref":"0000000000000000000000000000000000000000000000000000000000000000"}`

Positive invalidation request, with the returned own Device credential:
`{"version":"CLEANUP-DEVICE@2","binding_id":"original-binding-id","reason":"session_invalid"}`.
The result is persisted before native action. If an account operation is active,
the returned reason is account_cleanup and IDs refer to that original operation.

Negative: V2 body on a V1 route →400; V1 binding on a V2 route →403; extra
`targets`/`scope`/`path` →400; wrong owner/state-bound credential →403; changed
request_digest →403; changed bytes after a confirmed/failed report →409. No
negative case is evidence of physical erasure. No failure creates a replacement
operation/invocation or starts a new model call.
