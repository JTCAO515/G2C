# NEEDS-PREVIEW@1 — unconfirmed extraction

New local synthetic version for #14/#305. It does not change NEEDS@1.0's manual
source/history grammar or turn a model result into a confirmed record.

`NEEDS-extraction.1` is bounded model JSON with exactly version, fields, unresolved,
long_term_requests. Fields use the existing strict NEEDS field validators, including
local companion references, explicit budget/paid/basis/coverage, unknown/missing
states and local date/time/timezone strings. No owner, source authority, action ID,
permission or Memory writer is accepted from the model.

At most eight unresolved declarations have exactly field/reason/original_text.
Each fragment must occur in the original accepted user text. Code-owned reasons
produce the following bilingual questions only: missing budget basis, mismatched
paid currency, unclear temporary/long-term lifetime, or missing fixed-item subject.
A known budget basis cannot be questioned as missing. A complete questionnaire is
not inferred from absent dates or unrelated missing fields. Long-term requests
are at most eight original fragments, separately deferred for explicit Memory
confirmation, never automatically saved as current conditions or Memory.

The host emits one JSONL `NEEDS-preview.1` object with data_origin=synthetic,
confirmation=unconfirmed, source_kind=unconfirmed_extraction; source contains the
original message_id/run_id plus exact decoded user-text UTF8 base64 and SHA256.
This is the **text**, not a new hash of the complete MESSAGE command. Fields,
unresolved declarations, code-owned bilingual questions, deferred_memory_requests
and bilingual status text follow. The output is <=131072 bytes. Associations,
hashes and source labels grant no owner/currentness/write/Trip permission.

`synthetic-needs-v1` is an explicit FakeProvider worker profile. A limited local
model processes explicit Chinese/English fixture statements: party size, date
unknown, one currency/budget basis, paid amount/coverage, explicit arrival/departure
wall time/IANA zone, explicit fixed hotel/appointment/transport subject/intent,
current-trip companion conditions, and separately stated long-term requests.
This is synthetic L1 protocol/flow evidence, not a real-model extraction-quality
claim. Conflicting/unhandled natural language must be corrected by the user;
there is no supplier/order verification, monetary conversion or inferred lifetime.

The actual registered operation is model.needs_preview.0 with registration
model.needs_preview, kind=model. It reuses the existing model input adapter,
OperationStore and one Meter; input bytes/IDs/attempt/period are fixed before IO.
Canonical AUTH/RUN/freshness/limit/cancel/unknown behavior stays in that Core.
No second accounting algorithm, automatic retry or blind original replacement.
`--real` remains closed; @1 run contexts cannot activate this profile.

Preview generation does not modify NEEDS, Memory, proposals or formal Trip.
The user separately sends an explicit manual command with expected_version and
original action bytes to save/correct a record. Replaying a stale preview with an
old expected version conflicts; the server does not regenerate the command or
silently select the latest record. Explicit consider_trip requests still use the
original guarded draft/TripProposal path and its separate confirmation semantics.
The App consumer belongs to A; JSONL/API/worker evidence does not claim native UI
or real model/service/device acceptance.
