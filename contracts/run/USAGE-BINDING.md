# Immutable original RUN → USAGE association

Parent 448bcc4073642f4fc17410bf8b637923a9a64a1f is preserved with its known-gap
FAIL evidence. This increment fixes that bounded association gap; shared
claim/cancel/AUTH fencing and real executor integration remain HOLD.

## Confirmed source and new stored values

Consumes unchanged USAGE a6693615aa773ddcffff852a9860ec1703aa2681 Command:
attempt_id, operation_id, run_id, kind, input_digest, reserve, output_limit.
Main relayed USAGE owner's confirmation: all seven fields use exact equality;
three IDs nonempty <=200, kinds model/tool/memory, digest 64 lowercase hex,
positive integers reject bool. These validate format, not provenance/permission.

The existing RUN row gains two nullable BYTEA columns:
- usage_command_bytes: internal exact UTF-8 encoding of the seven canonical
  Command fields. Encoding is generated from the canonical frozen Command by the
  synthetic adapter; it is not another public wire schema or budget model.
- usage_input_bytes: original immutable outbound input bytes, supplied explicitly
  by trusted preparation. SHA256 must equal Command.input_digest. They are never
  trimmed, decoded/re-encoded or substituted with message text. The MESSAGE input
  digest and outbound input digest are different concepts and are not equated.

UsageBinding validates/decode-checks those bytes and preserves them byte-for-byte.
The codec imports no USAGE ledger. Stored command run_id must match the original
RUN Binding.run_id. operation_id, attempt_id, input_digest and every other field
are fixed by first trusted row creation and compared on every adapter entry and
replay; differing fields or bytes conflict. We do not claim operation_id can be
inferred from MESSAGE: it must be explicitly supplied by trusted composition.
Caller scope is never a new authority. PostgreSQL still checks the pre-scoped
repository against full Binding; real issuer/sub/environment resolution and
same-partition Meter composition are not implemented here.

## Commit, recovery and one-shot synthetic invocation

Service.accept_with_usage creates the row and the association in the same RUN
transaction. Any legacy unbound row refuses backfill, even queued; expired rows
remain occupied and cannot be replaced. Exact bound replay returns original
state, without changing stored bytes or expiry. SQL trigger rejects updates to
original identities or association (including NULL->bound and bound->NULL).
No upgrade/migration touches existing databases: candidate.sql targets new empty
private databases only.

SyntheticFirstStep.create_fixture requires a NEW row (`require_new=True`). Only
an acknowledged new create allows one subsequent synthetic execute invocation.
The in-memory boolean is a deliberately conservative test sequencing restriction,
NOT authorization or a durable dispatch capability. It is consumed before any
reserve call, never restored on exception, and cannot be re-armed on existing-row
acceptance. Therefore create/reserve/claim ACK uncertainty, a second invocation,
or a reconstructed instance cannot claim/execute again. Reads of reserved or
unknown do not grant execution. A newly created fixture after restart is query /
original-receipt reconciliation only, including when its USAGE fixture is empty.
This trades liveness for safe denial; no automatic worker recovery is claimed.

The full association is available in authenticated-composition-only original
snapshot/recover state. It is not a new public response field. Binding creation
failure/unknown propagates and performs no reserve; the caller reads the original
row. No second queue, ledger, compensation or dispatch authority was added.

Cancellation after claim keeps original quota unknown; late original trusted
receipts may settle through canonical Meter without reviving cancelled RUN.
RUN expiry can block this fixture's association read; it must not reset usage or
create a new attempt. Actual USAGE-ledger reconciliation remains its own domain.

## Private-data and remaining boundaries

Both command and outbound bytes are private RUN-owned data. This slice records
only synthetic inputs and logs no input bytes. Production input preparation,
secret separation, encryption/access policy, retention/physical cleanup and
backup invalidation need their accepted owners before real input is persisted.
No original output, credential, environment secret or real user data was read.

Remaining blockers are unchanged: current AUTH/context authority, same trusted
budget partition, shared claim/cancel/check-to-call fence, real receipt provenance,
real worker recovery, and external exit integration. Service.dispatch is still
unconditionally disabled. Arbitrary injected Python is trusted fixture code,
not a sandbox; no real executor may use this fixture class.

## Validation

- 29 unit tests PASS: original 14 state tests, 5 P2 groups, 6 transaction-failure
  tests, and 4 binding groups. Python 3.9.6; no broader compatibility promise.
- 16 composition tests PASS with pinned canonical USAGE core on Python 3.14.7,
  including reserve ACK loss and no claim on reconstruction.
- Original known-gap probe now PASS with zero replacement executor calls.
  Old `usage-known-gap.txt` FAIL remains unchanged; new result is
  `binding-gap-regression.txt`.
- PostgreSQL: 17 cases covered. Initial run: 16 PASS + one test exception-type
  expectation ERROR (expected ValueError, adapter correctly raised Conflict for
  foreign run_id). Corrected only that assertion, then targeted case PASS.
  No earlier failures were overwritten; see binding-pg-initial/targeted.txt.
- Clean PG restart plus fresh Python process PASS: original input/command bytes
  readable; original and replacement attempts cannot re-arm or reserve even with
  an empty USAGE test adapter. This is RUN persistence evidence, NOT real USAGE
  persistence or worker crash recovery.

Private cluster: backend/run/.local/binding/data and .../socket, new empty PG16.15,
listen_addresses='', psycopg3.3.4. Old .local/pgdata was not reused. New cluster
stopped after checks; original and new data/logs retained, no deletion.

Reproduction from root (explicit offline local USAGE Git source):

```sh
PYTHONPATH=backend/run python3 -B -m unittest discover -s backend/run/tests -v
uv run --offline --no-project --with psycopg==3.3.4 python -B backend/run/tests/usage_composition_checks.py --usage-repo /absolute/path/to/cj-008-usage -v
uv run --offline --no-project --with psycopg==3.3.4 python -B backend/run/tests/usage_boundary_probe.py --usage-repo /absolute/path/to/cj-008-usage
```

`pg_binding_checks.py` applies candidate SQL only to the explicit NEW private
binding socket cluster; do not rerun schema creation against retained data.
`--case test_original_row_bytes_and_rebuild_conflicts` was the one targeted retry
in a separate fixture scope. `pg_binding_restart.py` is the post-restart read-only
proof using the retained original row. Starting any server remains an explicit
operation, never a test-suite side effect.

Independent Review/Testing pending; no cloud, existing DB, provider, fees, real
AUTH/worker/device or deployment used. Issue 11 stays open.
