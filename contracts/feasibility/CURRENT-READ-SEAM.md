# Original current NEEDS read seam request (af52 history)

`CJ-FEASIBILITY-CURRENT-READ@0.1.0-candidate.1`. CJ-035 / Issue18, after
512e272bece2e9ee5f768f08d01a3a43700ca9d7. Consumer source:
`backend/feasibility/cj_feasibility/current_read.py`.

**Historical status at af52: full protected entry BLOCKED / NOT ENABLED.**

Follow-up: the accepted NEEDS4cc9 strict seam is now consumed by the separate
[PROTECTED-CURRENT](PROTECTED-CURRENT.md) candidate. Its author integration is
verified; own independent gates/root registration are still pending. Original
FAIL logs and the original request below remain preserved.

**Original af52 scope follows.** This candidate implements the
bounded real read/evaluation/projection within existing public lifetimes. It
cannot itself guarantee strict connection-close settlement or current trusted
host environment binding, which the fixed NEEDS boundary does not expose.
There is no token API, root route, registered factory or default resolver.
No caller-provided snapshots/owner/scope/configuration choose authorized data.

## Exact accepted inputs

- NEEDS c821b34d607016c6dbc1020c203621841f1a60e8: original public Boundary /
  callback Operation.metadata/detail/revision and Snapshot/Revision. All NEEDS
  source is unchanged at the accepted main snapshot captured in the manifest.
- AUTH 8b6abb236cf10c1865a9cc8c6155bd8ac732c07e: canonical AdmissionChecker and
  ProtectedReadBoundary / ProtectedReadContext principal/require_current/invalidate.
  Exact fixed sources were exported to a separate fresh temporary tree, never
  consumed from an unpinned moving owner checkout. Accepted main file bytes were
  compared against those exact sources, not just matching names/versions.
- Existing evaluate(snapshot,revisions) is reused byte-unchanged; no alternate
  history replay, SQL/repository, authorization algorithm or transaction wrapper.

## Implemented consumer projection

```python
from cj_feasibility.current_read import ReadLimits, project_current

# Only INSIDE canonical AUTH and NEEDS callbacks, for local consumer validation:
encoded = project_current(operation, protected_read_context, explicit_needs_id,
                          limits=ReadLimits(max_revisions, max_input_bytes, max_output_bytes))
# This return remains inside those lifetimes; it is NOT publication authority.
```

Exact canonical operation/context classes are required; inactive, wrong identity,
expired or unknown context cannot be replaced by a snapshot or fake allow callback.
NEEDS metadata principal must match the canonical read-context principal. Reads
use only operation.detail/revision; no private transaction/repository fields.

The consumer captures current Snapshot by needs_id, loads exact revisions 1..n
under explicit positive revision/aggregate-byte limits, and surrounds each read
with fresh canonical AUTH checks. Missing record/other scope gives the same safe
withholding category. Missing/wrong-version chain or invalid original input
withholds all output; no latest-source fallback or fabricated numeric/date values.

It then invokes existing evaluate. INVALID never becomes an authorized result;
only local CONFLICT/UNKNOWN is projected, overall always UNKNOWN. All checks,
evidence declarations, missing fields, both same-result languages and exact
source identity/hash are retained. Source original UTF8 is included **once per
revision** in sources; encode that string as UTF8 to recover original bytes.
No reconstructed command replaces the original source. Full private report bytes
are iteratively encoded under the explicit output cap, then frozen as exact bytes.

After encoding, it rechecks canonical context, re-reads the current record through
the same NEEDS operation, checks exact Snapshot equality/metadata/principal, then
checks canonical context again. This catches changes after history/projection,
not a claim of a global atomic latest timestamp across independent transactions.
No operation handles, mutable reports, generators, database cursor or lazy encoder
are returned. There are no domain writes during evaluation; fixture seeding is
separate and synthetic.

## Actual canonical gap and minimal request to original owner

The fixed NEEDS `Repository.transaction` calls guard('return') **before** its
finally/connection.close. Ordinary close exceptions are logged and swallowed.
Boundary.with_operation does a final serialized_return AUTH check, but its binding
check only captures callable/connect/scope identities. It does not revalidate the
trusted host resolver's *current environment-to-scope mapping*. AUTH8b correctly
settles current principal after the callback; it explicitly leaves storage cleanup
and environment binding to the domain/host, so it cannot fill either missing fact.

Two actual private-PG counterexamples in current-read-seam-fail.txt:

1. Test connection closes underlying PG successfully, then raises an ordinary
   close exception: all guards/outer AUTH still accept and bytes escape.
2. Same trusted resolver callable changes its host environment mapping from scope
   A to B on close, with unchanged current principal: original captured scope A
   is still read/projected and returned. No caller owner field was involved.

**Request Main route to canonical NEEDS owner, smallest semantic extension:**

- Provide an owner-confirmed strict **read** composition on the existing canonical
  Boundary/operation surface (or a narrow read-only equivalent), retaining current
  detail/revision semantics and the existing AUTH checker/context. No new auth,
  caller scope, claim/dispatch permission or generic callback framework.
- In that composition, any read transaction cleanup failure, including ordinary
  close exception, must withhold bytes. After all actual cleanup and full encoding,
  revalidate the original host-controlled resolver's current environment binding
  against the captured connect/scope, surrounding its callback with canonical fresh
  principal/identity checks. A changed callable, principal, environment, binding,
  missing config or unknown/failed cleanup must withhold the entire result.
- Keep operation/context invalidation on all exits; do not reinterpret a strict
  read failure as empty data or a business-write rollback/never-committed proof.
  Preserve existing write/UNKNOWN recovery semantics and unaffected old consumers.
- Publish exact supported interface/version + source head and targeted close/
  resolver negative evidence. This document proposes **behavior**, not an invented
  callable signature already available or permission to enable a route.

Consumer must wait for that fixed public seam before outer bytes can be exposed.
It will then attach this existing projector, without copying NEEDS SQL/AUTH or
adding a second resolver/permission check in the consumer. No consumer-side
connection wrapper, log interception, private-state inspection or permissive flag
will be used to assert missing cleanup success. Test connection wrappers below
are fault injection only, not runtime implementations.

## Evidence and outstanding gates

Actual new private Unix-only PostgreSQL, exact canonical Boundary/AdmissionChecker/
ProtectedReadBoundary, synthetic identity facts/manual content. Correct owner,
complete source history, explicit bounds, missing/other owner, expired/unknown,
read-time changes, post-close identity revocation, post-encoding revocation and
out-of-lifetime handles are exercised. Tests use an existing read-only Python
runtime with psycopg; no installation or source change to that owner environment.
The test process clears inherited PG variables and supplies every DSN field.
Postgres listen_addresses is empty, socket dir private; clusters are stopped and
preserved with STOPPED files. No old DB, account/key/secret/real provider used.

12 consumer checks PASS; two strict-entry seam probes **FAIL and preserved**.
These categories must not be averaged into full-entry PASS. No root token entry
or factory is enabled, including when default resolver/config is absent. Previous
solver20/route/NEEDS source and evidence are reused unchanged. Strict seam/full
read-entry acceptance pending Main/original owner; provider/UI/Issue I remain
UNRUN. Private projected data stays inside the read lifetime; no persistence or
cleanup/retention promise is introduced.
