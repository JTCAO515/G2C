# TRIP-source-initialize.1 — explicit protected legacy initialization

This additive C local host fixes the protected-legacy INITIALIZE refusal reported
in #354 without changing frozen INITIALIZE-V1 / MANUAL-ORIGIN-V1 semantics. The
old unbound initializer/editor still refuses explicit NEEDS and protected origins.
The new operation consumes the genuine original message/RUN/NEEDS producer;
neither the wrapper, basis label nor a hash is permission.

`create_local_needs_app` already requires the actual registered run context,
canonical AUTH and original ConfirmationSigner. Its new routes are:

| Route | Input / result |
|---|---|
| POST `/v1/trip-source-initializations` | octet-stream TRIP-source-initialize.1 / preparation |
| GET `/v1/trip-source-initializations?request_id=...` | original bounded preparation or null |
| POST `/v1/trip-source-initialization-saves` | octet-stream TRIP-source-initialize-save.1 / receipt |
| GET `/v1/trip-source-initialization-receipts?action_id=...` | original receipt or null |

Canonical request <=1,000,000 bytes, exactly `version`, `needs_reference` and
`initialization`. Version is TRIP-source-initialize.1. The reference is exactly
`id`, `expected_version` (1..128). The nested initialization is the unchanged
TRIP-initialize.1 grammar (original ID/version/hash and all original item schedule/
fixed observations). It preserves seconds precision; it does not upgrade minute
observations or infer a date/timezone/fixed value. No text/title/order/source edits.

Only an actual accepted current legacy Trip version1 with its original run- root
is eligible. Existing receipt/action/digest/content proofs and original RUN effect
are reused from ManualOrigin. The original signed message must itself contain the
same NEEDS reference; a current source cannot be attached retroactively to an
unbound/unknown root. No new Trip or replacement source is fabricated.

The operation first reads immutable data and releases the Trip lock. It then holds
the original RUN -> M/TRAVEL -> NEEDS leases, captures the full canonical source
history and rechecks the same original Trip inside the original Trip transaction.
The original pure initializer and FEAS time check prepare structured.1; the sole
`_publish_in_tx` records a pending Proposal and immutable basis together. Explicit
save reenters the same original source leases, rebuilds the exact candidate and
uses original ConfirmationSigner/_act_in_tx and final confirmation eligibility.
Only that existing Trip advances1->2. No automatic plan adoption or NEEDS mutation.

The old legacy producer retained no trustworthy Trip-item-to-NEEDS-item mapping.
The new response explicitly reports `item_source_association.status=UNKNOWN` with
both languages. It does not manufacture that mapping, proposed participant/booking
metadata or a TRIP-NEEDS-SOURCE planning basis. Overall feasibility remains unknown;
initialization is an explicit user declaration, not a model replan or verification.
The old unbound editor cannot adopt this new basis. Further assistant edits still
need the normal current NEEDS/Memory/source checks and original scoped publisher.

The save request is canonical <=32768 bytes, exactly version/action_id/proposal_id/
candidate_hash, version TRIP-source-initialize-save.1. Same original action bytes
reconcile before source checks. A concurrent successful original action may be
reconciled read-only; physical ACK UNKNOWN remains UNKNOWN and requires original
receipt lookup, never new IDs or automatic write retries. Rollback/expiry preserves
the pending original and original formal Trip. Current source correction, foreign
owner, retargeting or changed Trip refuses new effects and stale preview output.

Responses are TRIP-source-initialize-result.1, bounded and encoded inside the
canonical protected Operation lifetime. They contain preparation/receipt shapes
of the existing C NEEDS host plus the explicit bilingual UNKNOWN association.
Retained source/request bytes never enter the response. Original receipts remain
queryable after rebuild/source changes; stale preparation can be withheld.

No migration/grant/role is added. Existing immutable cj_trip_manual_basis/intent
store the new versioned canonical source envelope and original action; original
RLS/SELECT+INSERT permissions apply. No raw SQL seeds a Trip, no protection is
disabled, and no B/iOS/frozen contract/applied migration is changed. Real services,
models, fees, cloud, production and device acceptance remain UNRUN.
