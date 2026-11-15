# Native simulator episode bridge (#936, Part 2a)

This source interface joins C's unchanged `choose(messages)` / `render_choice`
to native DUT admission. It is not an installed worker factory or a Hong Kong
qualification, and does not authorize any provider call.

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

The composition must supply C's pinned renderer and error classes, separately
pinned actor/DUT authorities over the same original C identity and fee journal,
an original worker wait, and a qualified observer. A received invalid actor
choice remains an original paid attempt; operational UNKNOWN stops new sends.
Programming errors propagate. All originals are retained before dispatch for
read-only reconciliation and accounting, including failed or uncertain calls.

Still required before real use: the installed worker factory and per-operation
window/pin checks for this namespace; actual source/image/model/prompt/schema
qualification; current accepted-context and injected-Memory observations; an
independent full factor-question census; original exploration-ending evidence;
whole-lifecycle DUT/actor/background fee inventory and ledger anchors; and a
formal exclusive window. Presentation labels, parsed model output or a declared
MESSAGE list cannot certify these missing observations. They stay UNKNOWN.

`tests/runtime_simulator_dut_pg.py` exercises signed native admission, the actual
native4 worker and registered HTTP fixture provider, independent actor RUN,
unchanged C renderer, next native input, and separate original fee records. Its
observer deliberately reports incomplete profile/Memory/question/boundary
evidence. It also verifies restart and lost-ACK query-only behavior and changed
identity denial. These are private-PG/fixture results, not live-service evidence.
