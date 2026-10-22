# FEEDBACK private data / cleanup registration candidate

CJ023 owns this inventory; CJ005 owns integration into the canonical registry and
CJ024 owns account cleanup composition. No deletion migration or cleanup endpoint
is executed by this candidate.

| Store | Fields | Sensitivity / purpose | Cleanup responsibility |
|---|---|---|---|
| `cj_feedback_action` | trusted `scope`, fixed `operation`, `action_id`, exact `original_input`, `input_sha256`, `submitted_at`, nullable `source_reference` | Private account-linked voluntary problem/expectation, minimal requested references; exact replay receipt | Remove all records for retired scope only through accepted account cleanup; include backups/restore and exported artifacts |

`original_input` is the sole stored copy of feedback; there is no duplicate decoded
text, transcript snapshot, memory export, token, exception, generated diagnostic
text, or secondary queue. Linked writes retain only the owner-verified message/run binding, message input
digest and read-time status/highwater. Source payloads stay with their canonical
owners; a saved observation is not a second authoritative execution ledger.

Retention duration, tombstone/restore generation, cleanup transaction fence and
backup policy are **unconfigured/UNRUN**. Before real deployment, retirement must
prevent old requests/workers from recreating a cleaned scope, invalidate in-flight
publication, and cover backups. Deleting a row alone is not verified cleanup.
Do not recycle a retired scope or claim permanent deduplication after deletion.
The local cluster data/logs below are fixture-only private test artifacts and are
preserved stopped; no old/shared database was touched.

No database grants to browser/authenticated/public clients exist. Candidate SQL
revokes PUBLIC access; the test runner grants only SELECT/INSERT to its new private
runtime role for FEEDBACK. Canonical MESSAGE/RUN fixture provisioning has
separate test-only SELECT/INSERT/UPDATE/sequence grants for those candidate tables. Production runtime role/RLS integration remains CJ005-owned and
UNRUN, rather than a new policy based on caller input or fabricated JWT claims.
