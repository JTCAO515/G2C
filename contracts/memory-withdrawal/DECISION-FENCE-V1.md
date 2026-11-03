# MEMORY-DECISION-FENCE@1

Added C public helpers in `cj_memory_jobs.decision_fence`; no change to Data3,
Pub3, accepted Trip authority or old Memory consumption. No private C rows or
text-derived digest/permission are needed.

The existing actual source API is `cj_trip.decision_source.DecisionQuery(
trip_id, expected_version, content_sha256)` and
`cj_trip.decision_lease.DecisionAuthority(original_trip_boundary, token)`.
Reuse the host's canonical checker/principal/scope mapping, including current
account admission. Do not construct a different identity or alternate SQL reader.

```python
with authority.hold(expected_principal, original_query,
                    max_source_bytes=4_000_000) as lease:
    digest = digest_under_lease(memory_scope, lease)
    # Hold the original source through its effect; fresh checks still apply.
```

`digest_under_lease(memory_scope, lease) -> str` requires the live actual C
decision lease and `lease.scope == trip_scope_for(memory_scope)`. It calls the
same `decision_input.source_digest` implementation as Data3, preserving its
accepted action/proposal/candidate/content/version identity. A detached Trip DTO,
manual flag, different owner or expired lease cannot supply authority.

If an existing edit holder already locks Trip, do **not** nest a second Trip
transaction. Before that holder, the public materialized read is:

```python
raw_digest = read_original_digest(
    original_trip_boundary, token, expected_principal, memory_scope,
    original_query,
)  # exactly 64 ASCII bytes
```

It uses only `Boundary.with_operation`, original OperationMetadata and
`context.read_decision_source` with bounded source/result sizes. Same principal,
owner, expected Trip version and document hash are mandatory. The read ends its
lock; a later effect must reacquire the existing edit source holder for that
same original version/hash, and the current Memory Fence1 for every actual
message/decision context coordinate. The digest is comparison data, never a
future source, Memory, model, tool or publication grant.

Actual accepted-Trip tests compare both helpers' digests, refuse changed expected
version and expired lease, and preserve exact formal Trip content after item
cleanup. Real provider/model quality remains #32.
