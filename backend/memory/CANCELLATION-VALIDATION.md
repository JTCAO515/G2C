# Review P2 repair and receipt hash — author delta evidence 2026-10-22

Parent 9b9696083baae2310c3f27547e2c727833de2f85 retains all manual producer and f410 binding work. Review HOLD evidence remains unchanged at cj-review/CJ011-f410193/review-summary.json and pg-results.json. Both reported failures were real: commit CancelledError escaped without original metadata; cancelled precommit guard was not sticky when caught. This increment fixes those boundaries, not AUTH policy.

PASS tests/cancellation_receipt_checks.py: six focused methods (0.094s), using new private real PostgreSQL transactions:

1. Exact Review commit-then-CancelledError fault, extended to KeyboardInterrupt, on reference AND manual: OperationWithheld with original operation_id/commit_possible=true/reconcile_original; independent query finds durable receipt with correct hash (4 variants).
2. Exact Review precommit CancelledError + callback catching CancelledError, on reference AND manual; additionally catch-all callback variant: no bytes returned, rollback confirmed, manual source absent, commit_possible=false (4 variants).
3. Projection cancelled after actual manual commit: original reconcile metadata retained and query succeeds.
4. Manual content-policy callback cancelled before commit attempt, projection catches it: sticky withheld, no original receipt.
5. Reference and manual save hash equals independent new-Service original query hash; query receives only operation_id. Hash matches original UTF8, manual derived Command hash explicitly differs, modified-byte same-ID save conflicts without changing original query hash; B cannot query A. Receipt shape exactly operation_id/item_id/version/status/input_sha256, no raw bytes.
6. Private-return guard cancelled after manual commit: original reconcile metadata and durable query preserved.

PASS existing three no-DB binding tests after code changes. Normal guard/keyset/manual scope tests retain their original fixed evidence; not rerun solely for this field. No claim that independent Review has accepted this new head yet.

New private PostgreSQL17 cluster backend/memory/.local/cancel/pg, role cj011_cancel, fresh postgres DB, UTF8, private socket /tmp/cj011-cancel-01a16218 (0700), port56115/listen_addresses empty. Explicit private empty pgpass0600, cleared ambient PG*, no inherited DSN. No prior instance started. New instance stopped successfully after tests and data retained. Tests create fresh schema/passfile and must not rerun against the retained cluster.

Receipt hash requires no DDL: compute from actual persisted original_input when decoding operation row. Insert reads that row back before successful commit return; query reuses same decoder. Required internal field is input_sha256, lowercase hex length64. Source/item-derived bytes are not used. Actual API/generator/App and real AUTH remain UNRUN; Issue12 stays open.
