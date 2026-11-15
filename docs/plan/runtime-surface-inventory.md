# Native private consumer surface inventory

`NativeSurfaceInventory` collects one original MESSAGE/RUN's actual input and
output surfaces for the trusted disclosure observer. It is not an E metadata
response, G result/state projection or assertion that no private data leaked.
The result contains raw original bytes, including any detected leak, and must
not be published through the fixture metadata router.

The existing `RuntimeOriginals` boundary reads the original canonical MESSAGE
and persisted RUN events; it returns exact UTF-8/base64 bytes and hashes, actual
terminal state and the actual scoped delivery ACK. Associated C history jobs
are independently queried by original conversation/generation/sequence range.
That tail and the native source snapshot are checked again before return.
Erased operation inputs withhold the entire read; they are not reconstructed
from old files.

The collector independently reads the original operation inventory, logical
inputs, verified final artifacts and actual model/memory wire inputs. Flat
surfaces preserve original bytes and hashes; the visible source envelope is
also retained with its digest. Tool operations do not invent a model wire.
Repeated native inventory/visible-source reads bracket the collection and a
final current guard must still pass.

Only genuinely absent capture files create nullable missing fields. Bad hashes,
corrupt files, erasure or AUTH failures propagate/withhold rather than becoming
an observed empty string. A nonterminal RUN, missing/unacknowledged delivery,
associated history work without collected surfaces or absent required captures
sets `evidence_status=UNKNOWN`. Available surfaces remain available privately
so a later scanner can preserve known FAIL priority even with other gaps.

`COMPLETE` covers only the stated original MESSAGE/RUN and the associated job
check at that native read. A full use must still enumerate every actual client
step, subsequent HTTP timeline/card/profile responses, any additional/background
source, late-write closure and the exact frozen
private sentinel set. It must verify hashes after persistence and perform exact
and separately declared semantic review; this module does not scan, classify
no-leakage, issue a use or charge/refund anything.

## Verification

Unit controls exercise exact surface bytes, missing wire/output, nonterminal
and ACK gaps, associated jobs, source races and current withdrawal. The existing
registered `real_services` PG group already runs `runtime_model_capture_pg`;
its added controls use actual native signed Lio2, Typed Memory, registered Meter,
financial RECEIVED and captured model/wire originals through fixture HTTP.
They verify complete native surfaces, unchanged model/fee counts and foreign/
revoked reads. These are private PG/MockTransport controls, not real supplier or
HK acceptance. No new suite registration or shared-file write is required.

Production source/controller wiring, complete use coverage, disclosure results,
publisher and paid E/F activation remain UNRUN.
