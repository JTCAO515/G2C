# MEMORY-ERASURE-EVIDENCE@1

Added C version; MEMORY-ERASURE-ASSOCIATION@1 is unchanged. This is an immutable
comparison artifact, never a cleanup intent, model permission or fee receipt.
It solves a specific boundary: B's original envelope hash is not C's original
enqueue hash. C does not claim to have stored a pending job's prepared-input SHA.

`AssociationReader(store, memory_scope).read_evidence(request) -> bytes` reads
the original M44 manifest under the same exact original CLEANUP@1.1
`require_intent`/principal/selection/scope checks as read_original. No current-row
reconstruction, absent-payload grant or account-purpose downgrade. The additional
proof/checksum is frozen in the stop transaction, immutable, max 8,000,000 bytes,
and physically removed with that manifest by both item and account hooks.

Root fields are exactly version, operation_id, subject_digest,
memory_scope_digest, selection, association_sha256, jobs. Identity and stopped
selection must equal Association@1; association_sha256 hashes its original bytes.
`erasure_evidence.parse_original(raw, association, association_sha256)` validates
this data boundary. Obtain raw from the reader before using this parser.

Each job retains Association@1's job_id/attempt_id/original_input_sha256/state
and adds:

| Field | Original frozen meaning |
| --- | --- |
| original_utf8 | Exact original C enqueue UTF8, including whitespace; hash must equal original_input_sha256 |
| source_comparison | MEMORY-SOURCE-COMPARISON@1 below |
| publication_utf8 / publication_sha256 | Exact original C Pub1/2/3 bytes/hash when present; null for pending/unpublished or the explicit old direct Collection completion |
| model_output_sha256 | Original C checkpoint output hash, or null when no C output checkpoint exists |

For state `erased`, all added fields are null. Earlier physical erasure does not
permit reconstructing deleted private bytes. B can confirm only from its own
previous exact C-hash redaction marker/original confirmed evidence. Missing B
proof stays UNKNOWN and authorizes no new erasure. Job and attempt identities
are permanent minimum hash barriers, not recyclable after payload deletion.

Source comparison has exactly version, purpose, end_ref, source_fingerprint,
messages, decision. purpose/end_ref are the original incremental/end comparison.
source_fingerprint is SHA256 of the original canonical SourceV2/message batch
encoded with `codec.encode_v2(source, messages, mode)`, not a B envelope hash.
messages preserves original source order; each entry has opaque ref,
text_sha256 (exact UTF8 text), and original (the full five MESSAGE coordinates).
No historical text is copied into this proof.

decision is null for Data2; Data3 has source_sha256 (the actual accepted-decision
digest), document_sha256 (the original accepted document), and refs (opaque
decision ref + original opaque anchor_ref, in source order). Data3's input
fingerprint is SHA256 of canonical JSON `[source_fingerprint, visible_decision_refs]`.

`erasure_evidence.compare_prepared(parsed_job, original_B_prepared_bytes)`
compares the actual B-owned original Data2/3 envelope to this frozen source:
purpose/end, source fingerprint, exact ordered permitted opaque references,
original text hashes, omitted count, and accepted-document/digest/anchor hashes.
It rejects changed text, document, references, fingerprint, purpose or format.
It returns the **computed SHA of the supplied B bytes**, after that comparison;
this is expressly not an invented C-stored prepared SHA. It grants no authority.

B must first verify its own original envelope, IDs/attempt, prepared bytes and
stored hashes. Parse original_utf8 with the explicit original C command version
and compare its exact source selection/accepted Trip query with B's original
reader; an end reader retains its existing explicit incremental-reader mapping.
If publication_utf8 exists, compare its hash with B's original receipt hash and
its enqueue/prepared/output fields against the originals. UNKNOWN output/ACK/
fees stay UNKNOWN; never manufacture zero cost or automatically resend. A source
comparison permits removing related copied payload only under the original
intent; it never permits deleting original chat or unrelated records.

Positive/negative coverage: signed original-intent API Data2 proof and changed
text refusal; actual accepted/modified Trip2, Data3/Pub3, different chat, genuine
end and inflight tail proof with changed document refusal; original account
cleanup removes the new persisted proof. B's real memory-purpose hook consumer
is separate acceptance; C's observation-only UNKNOWN does not prove it.
