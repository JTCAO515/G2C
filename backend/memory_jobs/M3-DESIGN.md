# M3 C implementation design (#409–#413; #26/#27)

This design follows main d1d21ee5 and JT's 2026-11-02 decisions. It is not a
frozen wire version, a deployed queue, or a collection grant. #402 owns the shared
cleanup protocol/role and #403 owns the protected MESSAGE source/ending capability.
No new storage is introduced by the initial protected-read slice.

## ADR-0009 candidate mapping

The existing `cj_memory_item.status` values `candidate` and `active` express the
required lifecycle. No extra item status is needed for a staff proposal. Existing
`Service.save` always keeps inference candidate; `Transaction.effective` joins
current approved/confirmed/resolved/unexpired sources and selects active items
only. Management pause/resume cannot promote a candidate. These existing checks
remain in force for reads, drafts and planning.

The next source contract will reserve `staff_proposed` alongside explicit manual,
committed-message incremental and conversation-summary provenance. A provenance
label is not approval. M3 will reject staff-proposal submission; it implements no
staff producer, staff API, service chat or JT event store. Unprovided storage is
not registered. Old source IDs and frozen schemas retain their current meaning.

A future user confirmation must be a new versioned action with original action
bytes/receipt, expected item/source versions and an explicitly reviewed concrete
fact/experience/preference. It cannot be a generic resume or model-provided
`confirmed=true`. A candidate left alone or refused stays ineffective. The
confirmation implementation belongs to #410, not to the initial read slice.

## Authorization and source identity

History organization is off by default and is enabled by the user per conversation.
The C-owned authorization record will bind the trusted account/conversation and
the #403 generation/epoch plus enabled continuous sequence interval. Enable,
disable and re-enable advance its version; old enabled intervals are not renewed
by text, by a manual save, by opening another conversation, or by a travel change.
No unenabled conversation is scanned into extraction. A source selection is a
comparison value; MESSAGE ownership alone is not collection consent.

The protected read slice calls only `Boundary.with_history_context`, compares its
server-selected scope, reads one exact 1–100-message interval through
`HistoryReadContext.message_history`, and finishes the existing bounded codec
inside the callback before final admission. It returns immutable snapshot bytes.
It does not retain a context, take a cross-domain publication lock, or authorize
enqueue/dispatch/promotion. `production_queue()` continues to reject. #403 must
replace the missing source authority before the live queue can be enabled.

Queue identity will use the owned conversation/generation, source authorization
version, mode, exact interval and original message IDs/digests. Original task and
attempt IDs remain stable across process reconstruction. Incremental and ending
summary purposes have separate processing cursors, with one incomplete interval
per current source/purpose. Same-source replay returns the original task; another
task ID cannot bypass source deduplication. End processing also binds #403's
stable ending ID. It does not require a Trip. Original accepted/edited Trip
decisions will use their protected references, never generated itinerary text as
evidence of a long-term preference.

## PG queue, worker and Meter

After #402's protocol arrives, the queue migration and its registry object and
working cleanup hook ship in the same PR. Storage will retain original source
references/bytes, task/attempt state, derived candidate/summary and processed
cursor with forced owner isolation. All are private, user-deletion/account-cleanup
data; source expiry only limits use. Memory is retained until deletion or account
closure, not evicted by a queue capacity or age rule. `cj_m1_runtime` receives only
the required SELECT/INSERT/column UPDATE rights. It gets no DELETE/TRUNCATE.

The original attempt records dispatch intent before the external action. A lost
ACK remains UNKNOWN; neither process restart nor elapsed lease time mints a new
attempt or retries a provider request. Recovery queries the original operation;
absence does not establish noncommit. Result/cursor advancement is atomic and
replay never moves a cursor backwards. Commit/rollback uncertainty and cleanup
errors cannot be reported as successful persistence or as safe resend permission.

#413 connects the producer to the existing registered Meter, original `run_once`
and real worker. Step/tool/output/time ceilings are explicit configuration, with
fresh admission, cancellation and current source checks at the actual exit. No
model call is added to the read slice. Fee UNKNOWN is retained as UNKNOWN, never
zero. The cleanup role is unavailable to the organization producer.

Existing RUN→MESSAGE→TRAVEL→MEMORY→NEEDS→USAGE ordering is preserved. #403 must
provide the public source lease and its lock placement; C will not invent a
second MESSAGE authority or acquire its private cursor. Queue/source locks must
be placed consistently in that graph before dispatch/publication is wired.

## Deletion and C domain cleanup

#26 first persists a current source/item withdrawal fence under the existing
MEMORY scope lock. Then cleanup physically removes candidates, source references,
original save/action bytes and derived task/summary material within the confirmed
scope. Minimum noncontent withdrawal/replay evidence must remain sufficient to
reject old extraction, original-chat re-extraction, index rebuild and backup
replay. A new explicit save needs a new source. An old immutable receipt is an
observation, not renewed authority. Cleanup completion requires real hook receipts
and query/recovery of the same operation.

C supplies hooks for `memory-authoritative`, `memory-management-actions`,
`trip-authoritative` and draft data. #402 supplies their shared protocol and role;
C does not change B cleanup semantics or register a new object without its hook.
Account deletion and item deletion share that protocol, while item deletion does
not authorize deletion of unrelated account data. Cleanup failures remain visible.

M30 `cj_trip_scoped_result` has no item ID foreign key: the initial design uses
conservative **derived-result scope cleanup** for the affected owned Memory scope,
including result bytes containing copied Memory data. This deliberately removes
unrelated derived results in that same scope; it does not delete unrelated formal
Trips or another owner's rows. It must be disclosed in the operation's confirmed
scope and receipt. It is not called precise item cleanup. No claim of physical
cleanup is made until this path and its owner/FK dependencies pass real PG tests.

Publication and deletion must serialize through the current Memory lock/fence.
If deletion commits first, the late result is refused. If a publication committed
before deletion acquired the lock, it is historical output; subsequent contexts
exclude the withdrawn item. Already sent provider requests and displayed history
cannot be recalled. Retained original chats may not re-inject withdrawn content
through another model context path; #26 validates actual constructed requests as
well as stored rows, including prompt assembly from raw history.

## Validation boundaries

The initial reader's tests use actual AUTH/MESSAGE code with synthetic storage.
They establish protected snapshot behavior only. PG task recovery, signed API
collection, original worker/Meter integration, candidate confirmation, physical
cleanup, account hooks and App behavior remain separate open acceptance boxes.
The full `scripts/test.py` and `scripts/pg_suites.py` remain mandatory; new migration
checks include empty up/down/up, nonempty down refusal and cross-owner negatives.
Real model extraction quality is #32; no fixture proves it.
