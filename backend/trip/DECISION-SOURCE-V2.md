# Accepted decision lease V2 (C composition)

Additive source preparation for #411; the existing bounded bytes-only
read_decision_source method and its V1 output remain unchanged. No store, model,
permission, cleanup role or automatic Trip/Memory writer is added.

DecisionAuthority(boundary,token).hold(expected_principal,query,
max_source_bytes=...) issues a genuine DecisionLease only while the original
canonical Trip repository transaction/scope lock is held. Boundary/token and
expected principal are supplied by trusted host composition, never wire owner
fields. Query is the existing validated DecisionQuery (Trip ID/version/content
digest); source is the actual current accepted record and immutable accepted
Proposal/action association. Pending/generated/rejected text is insufficient.

The holder checks the same canonical admission/binding before and after bounded
local work. The lease is confined to the current thread/context and becomes
unusable at exit; a real admission failure also invalidates it even if membership
later returns. Nested acquisition is denied before injected binding callbacks.
Its properties expose private comparison/data only, not a future authorization.
Do not hold it across model/provider/network waits or serialize the lease.

The existing runtime role and Trip lock are reused. A future Memory publication
consumer must order MESSAGE/Travel -> Trip -> Memory, bind the genuine expected
principal, use current source filtering and the actual final Meter callback before
Memory commit. A captured value alone cannot stand in for that new phase.

Accepted itinerary content proves a user-accepted plan, not that the user visited
its places or has a permanent preference. Derived conclusions remain candidates
until explicit user confirmation; source text remains data, never instructions.

Actual private-PG tests reuse signed initialization/manual acceptance and cover
current accepted data, wrong hash/version, pending source, two owners, byte bound,
thread/context escape, nested holder, later edit and sticky admission loss.
These primitives alone do not complete Trip-to-summary/model/Meter intake.
