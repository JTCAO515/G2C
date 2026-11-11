# Selected Lio intake evidence, version 1

#823, original business incident #822 / #702. This is diagnostics, not a claim
that the first real structured-intake failure is fixed. The original received
attempt, UNKNOWN RUN, fee and missing original output remain intact.

`G2C-lio-intake-evidence.1` is separate from frozen `G2C-tool-evidence.1`.
Its capture_kind is model; it names the actual model registration, source commit,
producer implementation hash, owner-scope hash, MESSAGE/RUN, operation/attempt,
original input hash, complete returned UTF-8 and SHA, original vendor receipt and
observation time. It does not duplicate the original input/Memory prompt bytes.
It cannot reconstruct an earlier output that was never captured.

There is no new public API, role, credential, database table, quota or financial
journal. Capture is default off and reuses the existing operator-selected private
synthetic-window selection. The frozen tool-only window.1 does not enable model
collection. Operators must explicitly use G2C-synthetic-evidence-window.2 with
kinds:["lio_intake"] (or also "tool"); absent/unknown/duplicate kinds fail closed.
Only a selected national-intake operation with a
complete original supplier receipt can produce it. It runs before the intake
parser and after the original provider exit, under the same worker execution and
Memory fence. Revocation/cancellation/erasure/expiry prevent publication, without
a new supplier attempt. Both the original tool and model contracts use the same
owned 0700 directory, 0600 O_EXCL/no-follow file and fsync path. Durable capture
failure remains UNKNOWN and never implies redispatch permission.

Operational rejection logs contain only a fixed allowlisted code, RUN ID, output
hash and byte count. Arbitrary model content or exception values are not logged;
unrecognized reasons remain invalid_model_intake. The private artifact is the
original evidence for an authorized synthetic diagnostic reader, not a fake
validation fixture or a new traveler memory.

The first C trajectory remains UNKNOWN and the sixteen-trajectory denominator
is unchanged. Before a later diagnostic, reconcile that original attempt and
register a distinct question and original ID/purpose. Do not resend the unknown
MESSAGE or reuse its attempt, substitute diagnostics into C's frozen sample,
claim financial settlement from a token estimate, or resume C automatically.
Any root-cause change still needs its own actual evidence and normal review/CI
and source-pinned deployment.
