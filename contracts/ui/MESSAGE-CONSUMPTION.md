# CJ006 fixed CJMessageClient consumption / build prerequisite

Historical blocker: Main subsequently allocated exact generated-output/pin paths. Fixed preparation and implementation are documented in [MESSAGE-HOST.md](MESSAGE-HOST.md).

Fixed producer c79da94c94315dd3b63db0fcc001dda3afa7403b, read using git show from cj-009-message. Normal local intake merge 7342a39c7f1a909fee1721534d9ffadbfea2b19f preserves CJ006 34ebd46 and its pending acceptance lane. Producer source is unchanged. This document is a consumer readiness result, not an implemented message host or independent acceptance.

## Actual interfaces support the requested bounded host

- CJMessageClient `MessageRecovery(storage:)` uses `SecureMessageStorage`; `activate(StorageScope)` returns opaque `Lease`, and `validateScope(_:lease:)` checks its binding. `invalidate()` immediately drops local plaintext snapshot/operations, without claiming remote cancellation or deletion.
- `saveDraft(_:conversationID:lease:)` and `draft(conversationID:lease:)` operate on exact Data. `stage(messageID:originalUTF8:lease:)` retains the original body and ID. The UI must not create wire JSON from translated labels or substitute session token bytes as a storage key.
- `action(messageID:lease:) -> ActionRecord?` exposes messageID, originalUTF8, phase, optional opaque receipt and digest. Use the real `ActionPhase` cases staged/queryRequired/notObserved/accepted; no parallel canonical message model is needed. There is no listing API, so the composition root must supply the original current message/conversation IDs; this slice must not invent a history endpoint.
- `MessageHTTPClient.query(messageID:lease:)` returns `MessageHTTPOutcome.accepted`, `.notObserved` or `.rejected(status:error:)`, and updates the recovery record with the original Operation. Only actual JSON null becomes notObserved. Arbitrary fallback JSON is rejected. Query errors remain unknown, never an instruction to POST.
- `liveReadTransport` refuses submit before credential acquisition; only the explicitly interceptedTestTransport seam supports synthetic submit. This host must never add a POST activation switch, new-ID retry, or live transport via the test seam.

## Planned minimum host responsibilities after build readiness

One trusted composition root provides scope, recovery/client/lease, original IDs and ShellGeneration; view input cannot select account/environment/key. Validate scope/lease and generation before and after async query. Storage/key failure and identity/clear-failure events synchronously invalidate recovery/key binding and clear UI projection before any late callback; no plaintext fallback. AccountHost must invoke this message fence before its session clear, including when clear later fails. Language changes only labels and must retain draft bytes, original request bytes and message ID.

Default unconfigured host keeps send disabled and does not activate storage or obtain credentials. Known-record display distinguishes:

| Canonical fact / event | UI meaning |
| --- | --- |
| staged | Locally staged only; not proof of server acceptance. Send remains unavailable. |
| queryRequired | Only original-action query is allowed; receipt not established. |
| query error / persistenceUnknown | Outcome unknown; retain original identity/bytes, no new action/POST. Storage unknown requires original recovery reopening, not an in-memory success. |
| notObserved / actual null | Query did not observe a receipt; not proof the message was unsent or safe to resend. |
| accepted + opaque receipt | A verified transport receipt exists for the original action; not an assistant/model reply or a completed trip. |

Query-only versus latest unknown can use UI activity/error state while reading the canonical ActionRecord; do not add a competing message schema. Synthetic adapters/results must be visibly labelled and never appended as service answers. Core tests should use the actual public types, original bytes and ID through language changes, late callbacks after invalidation, and cleanup-failure blocking. No model stream or message-history API is part of this slice.

## Concrete blocker reproduced

The fixed Package.swift requires local packages:

1. `.generated/312a69caf0bd97ed65679cfd8ff049972c212cef/CJFoundation`
2. `.generated/CJMessageKeysInterface`

Both are absent after normal fixed-commit intake because they are ignored build exports. `swift package describe` can read the manifest, but **swift build --target CJMessageClient fails**, even for the core product, at the first missing local package. Log: ios/Modules/CJShell/evidence/message-consumption/build-blocker.txt. This is missing dependency preparation, not a claim that message source logic or upstream tests fail.

Producer `scripts/prepare_generated.py` writes both `.generated` and producer `evidence/generated-pin.json`; prepare_keys likewise belongs to the producer package. Current CJ006 lease permits only CJShell and contracts/ui, explicitly not CJMessageClient edits. Therefore these scripts were not run in the dependency tree; no types or manifests were copied, no absolute dependency on the producer's moving checkout, no shadow package or root-engineering workaround added. CJShell's existing package remains buildable and unchanged.

Minimum resolution through Main / original CJ009 owner: provide a reproducible fixed consumer dependency package/export, or explicitly allocate only the exact ignored generated-output preparation in this clone with hashes and without producer evidence/source mutation. The two fixed export inputs must be verified from their canonical commits; no new schema/key authority is required. This is a build-artifact/write-scope gap, not a missing real account/keychain environment. It does not require live POST, secrets, provider access or a new feature.

After that prerequisite, implement the bounded host above under the existing CJShell lease and run focused local tests. No current message UI implementation/test PASS is claimed. Prior 34ebd46 product changes and evidence are preserved for the existing review lane.
