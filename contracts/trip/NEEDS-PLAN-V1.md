# TRIP-NEEDS-SOURCE@1 / TRIP-model-plan.1 / structured.2 — frozen

Owner C (#204/#285), local runtime only. Append-only; old structured.1, legacy,
provenance.1, MESSAGE and NEEDS wire stay unchanged. No real model/cloud/fee/key.

Before draft model IO, canonical B MessageContextAuthority yields the actual
original MESSAGE-send.2 under RUN/MESSAGE/TRAVEL/MEMORY ordering. Its explicit
needs_reference selects the original record/version. Canonical B protected_reader
reads same-principal/same-derived-scope snapshot + bounded full immutable history,
encodes NEEDS@1.0 inside its lifetime and verifies original version/source chain.
The captured source is private immutable data, not authorization. The model sees
the original fields; no lease spans model IO. Changed source is never rebound to
latest silently. Max128 revisions/4m source bytes, absence/invalid/overbound refuse.

TRIP-model-plan.1 is exactly version/title/items/proposed_subjects (1m bytes). Items use structured.2
shape: original structured.1 observation/source rules, with explicitly supplied
HH:MM or HH:MM:SS accepted and retained verbatim. No seconds/timezone inferred.
No free-text dates parsed. The model cannot upload sources, verified/evidence or
UTC offset observations, change any original fixed intention, remove original IDs
or change locked/unknown/unselected source items. Known-unlocked original IDs and
new proposed IDs are the trusted whole-trip planning scope; retained order remains
protected. New activities require an explicit proposed_subjects map for exactly their IDs; no default party/self is inserted. They remain unconfirmed intent with unknown booking and proposed participants
and unknown source, not new user declarations or supplier facts.

Original NEEDS field map is retained; proposed item fields map into an uncommitted
Candidate, never a manufactured Snapshot/Revision. FEASIBILITY-PROPOSED@1 calls
the accepted protect then the very same evaluator implementation. Original source
evidence stays in protection; new declarations have no committed action/revision.
CONFLICT/INVALID or no PROTECTED_SCOPE_UNCHANGED/PASS rejects the entire plan, with
no Proposal/basis/formal Trip/RUN effect. UNKNOWN remains visible, no overall PASS.

At final publication the actual B RevisionLease is entered once and held through
original Proposal transaction **and** RUN effect commit. A C opaque, factory-issued
active lease is checked against its original captured object and same thread;
DTO/hash/constructor/callback cannot release publication. Reuse the original B
MESSAGE/NEEDS authority; no new NEEDS connection under an already-held lease.
The coordinator worker structured.2 branch is opt-in. Legacy/provenance branches
retain their previous exact behavior. Final original deadline is last after all
scope/source SQL checks. Late result, wrong owner, revoked context/source or changed
original version cannot commit a valid new effect; no automatic retry/new IDs.

The existing sole Trip _publish_in_tx writes structured.2 Proposal and immutable
cj_trip_needs_basis in one Trip transaction. Basis retains original RUN/message
scope, full source bytes/hash, NEEDS record/revision and proposed original field
map. Append local migration0024 uses same-owner namespace checks, immutable
message-receipt and NEEDS-revision FKs (not a second connection lock on mutable RUN
row), FORCE RLS and existing role SELECT/INSERT only. No UPDATE/DELETE/TRUNCATE/
new role/BYPASSRLS/SECURITY DEFINER. Empty up/down/up; retained basis blocks down.

Actual source-bound publish does not auto-accept a formal Trip; user confirmation
and existing act are still necessary. Old HTTP/client readers reject structured.2
rather than strip minute precision/source/fixed fields. Needs-bound manual accept,
source refresh and subsequent planner reading of local fixed intentions are #285.
No DTO/candidate equality grants those operations. Consumption uses actual B
CJ-LOCAL-NEEDS@1 and immutable original MESSAGE needs_reference.

Executable positives/negatives: tests/test_structured_v2.py, test_proposed.py and
backend/draft/tests/needs_runtime_pg.py; actual signed API/runtime PG/worker/Fake,
source before model, protected/conflicting zero effects and both real writer vs
Proposal/RUN publication orders. All provider/source data is explicit synthetic.
