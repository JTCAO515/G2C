# Exact frozen-marker disclosure scan

`NativeExactDisclosureScan` takes the actual native surface collector and a
currently qualified producer source boundary. Its expected source frame and
private sentinel-set bytes/digest are trusted B-controlled frozen inputs, not E
candidate fields. The sentinel envelope version is
`G2C-fixture-private-sentinels.1`, with exact `source_state_sha256` and a nonempty
unique list of strings. Its actual bytes/hash must match the independent frozen
source. The module does not create or approve that source policy.

E surfaces are collected before C holders are acquired. During a short current-C
projection, every frozen marker must actually occur in the accepted private
source content; a declared but absent marker withholds the scan. Each native
surface's original base64 bytes and hash are verified before matching. Raw UTF-8,
JSON string values and the exact JSON Unicode string encoding are covered. The
surface collector's native-order joined text captures markers spanning stream
chunks. This does not claim detection of arbitrary encoding, paraphrase or
unknown semantic disclosure.

Reports use `G2C-fixture-exact-disclosure.1` and contain source/inventory/marker-set
digests, covered source IDs and hit marker digests, never marker values or raw
consumer bytes. A known hit yields FAIL even when another surface is missing.
No hit with incomplete declared evidence yields UNKNOWN. PASS is limited to the
declared exact markers and that native inventory's explicit coverage; semantic
review remains UNRUN. Native surfaces are read again after the C projection;
changed original evidence withholds the earlier report.

## Evidence and activation limits

Unit controls cover raw/Unicode/JSON encodings, known FAIL priority, missing data,
wrong frozen source/hash, absent actual marker, withdrawal and post-scan changes.
The existing native composite PG group adds actual C-source custody checks with
controlled E bytes; this does not represent complete native E provider coverage.
Existing source locks, consent-ABA, retirement and zero-added-model controls run
unchanged. The independent native surface-capture group's evidence is separate.

This module is a scanner, not a per-use journal. The final host must invoke it
only for an admitted original use, retain the immutable original scan report and
reconcile that original on re-query without rescanning. It does not issue a use,
classify the entire cross-owner task, perform semantic review, add costs, publish
metadata or grant source access. Full X01–X12/controller/router/publication and
paid E/F remain UNRUN until those protections and independent sources are wired.
