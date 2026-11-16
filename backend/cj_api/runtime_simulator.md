# Native simulator episode bridge (#936, Part 2a)

This source interface joins C's unchanged `choose(messages)` / `render_choice`
to native DUT admission. It is not an installed worker factory or a Hong Kong
qualification, and does not authorize any provider call.

For the current legacy baseline, `BaselineDutSpecification` selects actual
`LIO-message.2` with additive private claim `LIO-simulator-dut.2`. It pins that
wire version explicitly; a candidate label does not choose the protocol. The
original `DutSpecification` remains actual `.4` / private claim `.1`, with its
serialized bytes unchanged. Claims, native parsing, admission and readback all
use the same fixed specification. Legacy normalized storage is verified against
the durable outer claim and native stored outer hash; it is not presented as a
stored full `.2` outer byte column or proof of historical code equivalence.
Missing baseline profile/census/Memory/ending observations remain incomplete.

```text
fixed public opening -> native DUT MESSAGE/RUN
  -> actual current-M public observation
  -> independent native actor RUN / original registered model
  -> C's unchanged renderer
  -> private original binding -> next ordinary DUT MESSAGE
```

`DutSpecification` fixes the public opening, locale, at most five planned
`c936-<64 hex>` message IDs, and the actual code/image/model card. The namespace
is separate from G's `runtime-` recipes. `DutMessageClaims` reuses the original
MESSAGE scope lock, durable exclusive claim, and one-use capability. A prior
claim or uncertain admission is query-only; it cannot mint a replacement send.
The send captures the original session token. Inside the native scope-locked
admission transaction, it also checks the original owner and, for a continuation,
the previous MID/RUN/generation/sequence/raw input against the current active
head. An intervening ordinary message or changed owner rejects admission before
writing a new MESSAGE; its consumed claim remains query-only.
`LIO-simulator-dut.1` is a new private claim version, not a change to frozen
MESSAGE or timeline wire contracts. Native admission uses `LIO-message.4`.

`ActorDutSource.observe` holds the genuine current M projection through its
callback and final snapshot check. The actor's existing `use` interface still
requires its exact public history and retains the four-actor-turn bound. The
fifth DUT reply can be observed without enabling a fifth actor turn. Deleted
payloads, incomplete histories, noncompleted runs and changed projections are
still refused. No Memory holder or snapshot is reconstructed.

`SimulatorActorBridge` checks the original actor source against the latest DUT
MID and observation reference, calls C's supplied renderer, and writes a private
`LIO-simulator-link.1` sidecar. It binds the original actor input/choice hashes,
original DUT source, exact rendered-text hash and next planned MID. Existing
different bytes cannot be overwritten. The product input receives only the
ordinary rendered text and native conversation selectors; the hidden profile,
actor system, choice object and sidecar never become DUT input.

`SimulatorRunRequests` supplies the normal worker's per-RUN registration and
post-start refusal seams for this namespace. Only a native input whose capability
was actually consumed by the same in-process DUT host can select registrations.
The initial check compares the actual MID/RUN/CID/generation/sequence and genuine
outer Lio receipt; legacy normalized storage is not mistaken for those outer
bytes. Missing, restarted, stopped or changed originals have no C0 fallback.
Ordinary messages retain their exact original registry.

Every registered preparation/bind/send retains the original registration kind,
input, receipt and limits. The native source guard is surrounded by current
canonical-claim/AUTH/pin/window/deadline checks, without another M transaction or
an extra financial hold. A rejected original stays query-only. The consumed-input
record is in-process only: restarting cannot reconstruct execution authority from
the durable claim. This component alone is not an installed factory or RPC.

The composition must supply C's pinned renderer and error classes, separately
pinned actor/DUT authorities over the same original C identity and fee journal,
an original worker wait, and a qualified observer. A received invalid actor
choice remains an original paid attempt; operational UNKNOWN stops new sends.
Programming errors propagate. All originals are retained before dispatch for
read-only reconciliation and accounting, including failed or uncertain calls.

Still required before real use: the installed worker factory/RPC consuming these
guards; actual source/image/model/prompt/schema qualification; whole-lifecycle
DUT/actor/background fee inventory and ledger anchors; and a formal exclusive
window. Presentation labels, parsed model output or a declared MESSAGE list
cannot certify these missing qualifications.

For the existing legacy baseline, missing accepted-profile, injected-Memory or
complete question-census observations remain explicitly unavailable. No observed
native exploration ending at the evaluator's declared bound produces the existing
`evaluation_bound_before_observed_exploration_end` measurement UNKNOWN; it is not
permission to claim G2/G3 PASS or zero errors, nor a requirement to upgrade the
baseline to native4 first. This differs from source/AUTH/native-action/actor-contract
or accounting-coverage failures, which stop new work and retain original costs.
The fixed sixty slots and 840 factors remain unchanged.

`tests/runtime_simulator_dut_pg.py` exercises signed native admission, the actual
native4 worker and registered HTTP fixture provider, independent actor RUN,
unchanged C renderer, next native input, and separate original fee records. Its
observer deliberately reports incomplete profile/Memory/question/boundary
evidence. It also verifies restart and lost-ACK query-only behavior and changed
identity denial. These are private-PG/fixture results, not live-service evidence.
The existing `runtime_actor` PG group runs that native4 control, the original actor
control and `runtime_simulator_requests_pg.py`'s legacy2 registered-send control;
the latter also denies an unclaimed native c936 message with zero operations and
zero additional fixture provider calls. It does not certify a real baseline.

`runtime_simulator_cost.original_charges` reads the existing protected originals
without sending or settling anything. Each native operation remains a separate
attempt and must join its original settled Meter, logical-input digest, financial
ledger/RECEIVED receipt and protected output/wire artifacts. A registered local
visitor catalogue operation may have no financial attempt only when the original
artifact reader verifies its zero-cost local receipt. Unpriced received calls
retain their full conservative hold and an unknown estimate; invoices are not
inferred.

Actor raw evidence is captured while its original DUT frame is current. Later
`recheck_charge_metadata` checks the captured inventory/Meter/fee hashes under
original AUTH without reopening historical raw access. Deletion continues to
deny a new raw capture, and revocation denies metadata too. These per-operation
proofs do not certify whole-episode cost: the concrete host must separately close
the actual DUT/actor/background producers and reconcile the original journal.
