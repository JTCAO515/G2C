# Draft CAS PUT candidate — intercepted tests only

Parent 94bad80fdca10e68391022a7593f709c77ccefb4. This follows, but does not rewrite or
mix into, the separately committed opaque-cursor UTF8 P2 repair. Official generated pin
remains CJ005 2f8be7c3e2dd298457488412b3a5e3b2ca59ca93; its exact generated Query has
conversation_id/generation/expected_revision:Int64 and binary HTTPBody. Fixed proposal
at that same commit confirms postcommit projection/output failure is unknown and equal
readback content/revision cannot identify the original writer. No shared wire changes.

## Public candidate API

- MessageHTTPClient.saveDraft(conversationID:generation:expectedRevision:originalUTF8:
  limits:lease:) → DraftSaveConfirmation.
- validateDraftConfirmation(result, lease:) throws → Bool: true ONLY if the SAME
  current editor revision/content is still represented by that original PUT response.
  Host must call this after await and before marking its editor saved. The initial
  matchesCurrentEditor flag alone is not a lasting saved-state authority.
- reconcileDraft(conversationID:limits:lease:) performs ONLY generated GET of the stored
  original conversation/generation and returns the existing lease-bound read result.
- MessageRecovery.draftSave(conversationID:lease:) exposes the local original CAS record
  under current lease; localProjection includes references to such retained records.

All existing endpoint/credential/scope/lease/response/body bounds and original request-ID/
duplicate-key/canonical-base64 checks apply. PUT sends exact provided UTF8 plain draft
bytes as octet-stream, including zero bytes; it does not construct message JSON, an ID,
a message receipt, a run or model state. expectedRevision must be 0..<Int64.max.

## Before outflow and after unknown

beginDraftSave persists immutable conversation/generation/expectedRevision/original bytes
and captured editor revision BEFORE handing bytes to generated transport. A private
operation nonce/lease prevents duplicate result application and synchronous save reentry.
The stored record is query-required until an exact original successful response confirms
conversation/generation/revision==expected+1 and identical bytes. A previous unresolved
record blocks every replacement PUT for that conversation, even changed revision, body
or generation. Only an acknowledged prior success can precede a new explicit CAS at its
confirmed revision; no automatic retry is implemented.

Network/commit unknown, cancellation after response, malformed/oversized/postcommit output,
BASE rejection/conflict or identity loss leave the original pending record intact and
never infer server rollback. A GET null or even exactly matching bytes/revision does NOT
mark this PUT confirmed and does NOT authorize another PUT. The wire has no per-draft
idempotency receipt; identifying which writer committed remains unresolvable locally.
This candidate therefore exposes observation only and stays fail-closed pending a future
explicit reconciliation/user-resolution contract. No “force”, clear-pending, new-ID or
revision-substitution workaround exists.

Cancellation checked before starting and after generated response; local cancellation
never cancels a server commit or clears retained evidence. Scope/lease checks after each
await keep old callbacks from confirming a new identity. Confirmed output never writes
editor bytes: local saveDraft always creates a new editor revision, including same-byte
edits. Old output cannot mark that newer revision saved; host revalidation returns false.

## Persistence compatibility and limitations

Encrypted Snapshot version1 gains draftEdits and draftSaves fields, still inside existing
CJMKEY02/AES authenticated storage. Decode of historical snapshots without these fields
uses empty dictionaries because those versions had NO PUT feature; it does not migrate
headerless/keyless files. DraftSaveRecord metadata is validated on activation. Encryption
key, key-ID format and real-provider policy unchanged. Missing/corrupt/key failures stay
errors. Projection adds only conversation references for pending saves, not private bytes.

Old authentic snapshot rollback can still erase a pending CAS record; no independent
freshness authority exists. Consequently BOTH live writes remain disabled: liveReadTransport
composition rejects saveDraft before credentials/outflow, and NoRedirectTransport itself
rejects PUT as well as POST. Test interception is NOT a product authorization route. No
production activation, new external ledger, key rotation or data deletion is introduced.

## Executed tests

Swift6.4/macOS. Nine unique DraftPutTests PASS: exact raw/CAS path; edit during request;
unknown reopen/null and blocked replacement; wrong revision/bad postcommit response/409;
confirmation invalidated by later edits even returning to identical bytes; cancellation;
actual synthetic encrypted-file reopen with retained pending reference; empty successful
PUT and late identity; matching GET cannot settle unknown; live PUT blocked. Some test
methods combine related scenarios. Evidence draft-put-tests.txt covers initial seven
methods plus two affected existing snapshot/recovery checks; draft-put-additional.txt
covers two new methods, one affected rerun and existing minimal-projection regression.
Total 9 unique new +3 existing affected tests, not full old-suite/PG reruns.
A Swift throwing-boolean expression was corrected without weakening assertions.

All HTTP responses are in-process interceptors, keys/storage are synthetic. No real
network, account, Keychain, backend/PG or CJShell change. Independent review pending;
wire uncertainty/resolution gap is explicit, not masked by a passing fixture.

Same-lease storage reentry correction: evidence/PUT-REENTRY.md supersedes the initial
9+3-only confidence. Nested editor writes inherit original CAS, outer writes cannot
replace newer committed memory, nested durable readback is mandatory before success,
and confirm re-evaluates editor revision afterward. Unknown/inconsistent stores fail
closed; original failing tests and new targeted evidence are retained.
