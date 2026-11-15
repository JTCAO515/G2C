# Native fixture Trip observation

`FixtureTripObserver` is the B host's private current-source reader for the
foreign-owner fixture. It dispatches nothing and has no production caller yet.
The host provides an already selected original C binding, pins, native MESSAGE
and Lio Trip boundaries, original credential supplier and preparation MID.
These are internal composition values, never E request fields.

Each read requires the original current AUTH/session/ledger/producer through
`RuntimeAuthority.require`, and additionally compares actual current source pins
with the frozen pins. Historical queries permitting old pins cannot qualify a
current fixture. The exact token digest and both native owner scopes must match
the selected original binding; a new C session is not a fixture.1 bridge.

The MESSAGE history boundary reads the original Lio preparation. Its actual
receipt supplies the native RUN binding; `lio_plan_receipt` must prove the
accepted native planning action for that original. The reader then resolves the
current selected Trip through the existing protected source lineage. The latest
original revision must match the selected Trip's version/content digest; a
second current-head read must agree. The original MESSAGE is read again after
the Trip operation, followed by another current qualification/source check.
Native Trip callbacks return fully encoded bytes inside the existing response
fence. No private Trip content or credential leaves those callbacks.

The internal result contains only `producer_binding_sha256`, the preparation
MESSAGE/RUN IDs and input digest, and `baseline` with Trip ID digest, actual
current version and content digest. It does not contain an expected outcome,
`PASS`, a copied private Trip, or an authorization token. No fees are reserved,
settled, refunded or synthesized by observation.

## Verification and limits

The unit controls cover changed current source, session/owner, missing or
unaccepted preparation, changed native current head, changed original MESSAGE
and withdrawal before publication. The private PG group creates an actual
signed native Lio plan, edit and undo with FakeProvider, then observes actual
selected v3 against the accepted preparation. Repeated reads add zero model
calls. A valid foreign local identity cannot read the preparation; changed
pins/session and revoked invitation withhold the observation. Its financial
authority and source pins are explicitly local fixtures.

This is a point observation, **not isolation**. Each native read uses a short
transaction; keeping its operation context alive does not hold a Trip lock
across a probe. It does not implement no-ABA source/restore fences, exhaustive
consumer surfaces, disclosure scanning, final atomic qualification/publication,
metadata original-reference resolution, preparation cost provenance or the
complete fixture definition/use. Those remain required by X01–X12 before E may
consume a fixture or any experiment is enabled. Actual paid costs, source
compatibility and publisher qualification remain UNRUN.
