# Accepted Trip decision source (internal V1)

This is a C-owned read-only source for #411 preparation, with no new storage,
permission, HTTP route or alternative Trip/Memory authority. Existing Trip
operation/admission/repository rules remain unchanged.

Inside the actual Trip Boundary.with_operation, call:

```python
context.read_decision_source(
    DecisionQuery(trip_id, expected_version, content_sha256), project,
    max_source_bytes=explicit_source_bound,
    max_result_bytes=explicit_response_bound,
)
```

The boundary captures the existing canonical principal and owner scope. A current
business host uses ACCOUNT-ADMISSION@2. The repository holds its actual scope lock,
checks the current formal record's version/hash, and reuses accepted_origin to
verify the unique committed accept receipt and accepted original Proposal bytes.
Original action/proposal/candidate identity must agree with that formal version.
Generated text and pending/rejected proposals cannot stand in for this decision.

project receives AcceptedDecision data: trip_id, version, content_sha256,
action_id, proposal_id, candidate_hash and exact current content bytes. It returns
bounded fully materialized bytes before commit/final admission checks. It receives
no cursor, connection or mutable authority. Confirmation references are omitted.
Nothing from this detached result authorizes future reads, Trip edits, history
organization, model dispatch or Memory promotion.

The history collector must separately verify its explicitly enabled original
conversation and the actual original typed Trip reference. Each later model or
publication phase rechecks the original decision version/hash. It must not call a
consumer that reacquires an already-held Trip transaction, or hold this callback
over network/provider work. Accepted plans do not prove a visit or permanent
preference; inferred experience/preferences remain candidates for user review.

Real signed accept/initialization/manual-save paths on restricted PG establish
the source fixtures. Tests cover unchanged read/replay, current accepted version,
old version/wrong hash, another owner, a pending-only Proposal, bounded/deferred
output, a subsequent real accepted update, and invitation loss inside projection.
Full ending/model/Meter integration and actual Trip decision intake remain #411;
this reader alone does not close it. Real model quality stays #32 UNRUN.
