# Publisher2 result runtime (#360)

The additive ABI and wire contract are contracts/message/EDIT-RESULT-V1.md. Only
actual explicit EditResultConfiguration(memory,publisher) enables the new local
message-edit-result.1 profile. Old EditConfiguration/publisher1 remains exact.
C's existing factory pattern (build publisher with a database, then install the
explicit configuration on that same database) is supported; no environment or
module-loader discovery upgrades a producer.

After registered M2/travel/edit activation and resolved old work, the local
operator calls cj_api.edit_result_profile.activate(conninfo,subject,context,
configuration,namespace). A current independent owned travel Selection is required.
New local migration0029 adds a SELECT-only compatibility profile and restrictive
LOCAL ABI gates, plus an appended RUN event and deferred atomic-completion check.
No C result-body table or permissions/roles are invented. Applied0001–0028 stay
byte-identical; down refuses retained profiles or results.

The actual programmatic run_once uses the new driver only for this negotiated
profile. Non-READY PreparedClarification calls no model and creates no operation,
reserve or claim. It pins the original registered quota-period association and
captures an original bounded clock before RUN start/source work. A crash cannot
reset the clock on a running RUN; it becomes original UNKNOWN, never a retry.
READY PreparedEdit retains the original registered model/Meter and budget/provider
semantics. C alone validates preview/explanation and returns its stored result.

C uses the existing live publication leases: RUN/MESSAGE/TRAVEL → Memory → NEEDS
→ same-cursor Trip lock. before_write stays last. C stores its body on that cursor,
then B record_result appends result_committed plus completed before the one commit.
The deferred constraint refuses a lone/inconsistent result event. The independent
scoped_result effect cannot authorize phase=accept or become a trip_proposal.
Rollback removes the C write and both RUN facts. Physical commit ACK UNKNOWN reads
the original state; no new ID or model dispatch is produced.

New read routes are enabled only with the explicit configuration. They encode
under canonical MESSAGE admission, derive RUN bindings from original receipts,
compare first/final RUN snapshots and keep the original reference/receipt/bytes.
Older status/display readers withhold unsupported result outcomes. Historical
receipt/history versions keep their original raw/reference semantics. No B route
returns a copy of C's body; C's body reader must enforce current Memory/NEEDS/source
fences separately. A historical result pointer grants no current permission.

The B scoped_result_pg suite composes actual signed APIs, restricted private PG,
unpatched run_once, FakeProvider, C memory/source leases, scope resolver and pure
explain helper. Its b360_result_probe table/publisher adapter is **test-only**,
not C336 production table/API/publisher delivery. It proves zero/one model calls,
original bytes and additive reads, common rollback/physical ACK loss/restart,
Trip/ABA/account/Memory/NEEDS/deadline/cancel/UNKNOWN fences and original budget
outcomes. Real models/API, fees, cloud/production and App/device remain UNRUN.
