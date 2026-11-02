# MEMORY-CANDIDATE-JOBS@1

Additive protected App discovery for #23. Existing candidate and publication
versions remain unchanged. No new storage or source/dispatch authority.

`GET /v5/memory-candidate-jobs?conversation_id=chat&after_job_id=` requires both
query keys exactly once. The initial after_job_id is the empty string; subsequent
pages use next_after_job_id verbatim. Conversation ID follows the existing UTF8
256-byte bound. A nonempty after_job_id follows the original 256-character job
identity grammar. Unknown, duplicate or oversized fields are rejected.

The service first verifies the owned conversation through the public protected
MESSAGE context. Under the current canonical Memory/account lock it selects only
actual origin rows whose current item is still candidate and whose exact original
conversation association matches. It returns the real first-producer job/attempt,
ordered by job_id, at most 50 per page. A reused summary candidate still points to
the original producer. Confirmed/rejected/paused/withdrawn items are not candidates
for this discovery. This is a projection of canonical state and origin records,
not a new index, fabricated task ID or a fresh history grant.

Response is `{version:"MEMORY-CANDIDATE-JOBS@1",request_id,result}`, with result
`{conversation_id,jobs:[{job_id,attempt_id}],next_after_job_id:null|string}`.
The final page has null. Query each returned first-producer reference through the
existing V3 memory-candidates read and use that same reference for review. This
path works for both existing supplied-output and typed-publication producers;
it does not require a failed V4 receipt read or parse fallback. Current candidate
metadata remains distinct from historical receipts. MEMORY-CANDIDATE@1 still rechecks current
item/Memory version, source and genuine Travel scope before confirmation.

Discovery is current-account read only, can show a previously produced candidate
after history organization is disabled, and never re-enables processing. Account
retirement/schema/query uncertainty fails closed. The C-owned origin deletion hook
removes the same projection; no second cleanup store or organizer privilege exists.
