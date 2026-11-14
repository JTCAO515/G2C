# Fixture preparation originals (#762)

This slice supplies preparation readers, not a completed definition/use publisher
or permission to start an experiment. No paid dispatch, new identity, database
migration, financial write, quota increase or consumer activation is added.

The host supplies `FixtureUseRegistry.preparation_guard`, which requalifies the
actual producer/observer source independently of the final definition.
`preparation_policy_source()` checks that qualification, the consumer, original
policy bytes and validity interval before returning the approved header. Missing
wiring fails closed. `reserve`, `read` and legacy `policy_source` still require
the final definition through `source_guard`; a header cannot reserve a use.

At preparation close, the controller freezes its declared MESSAGE selection with
`FrozenPreparationCost.freeze()`. The private 0700 directory and O_EXCL 0600
original survive restart and ambiguous ACK. Partial records are retained and
cannot be overwritten. This reader proves only the declared selection; the
controller must separately prove lifecycle completeness and retain its actual
before/after anchors and original charge/batch allocation.

`read()` rechecks current producer authority, exact session, selected native
MESSAGE inventories, all attempted financial and Meter originals, including
failed/missing/UNKNOWN attempts. Unrelated shared-ledger activity does not replace
the frozen parent anchors. Any selected original change withholds the old record
and requires explicit reconciliation of that original; it never silently
settles, retries, overwrites, charges again or releases a hold. Supplier paid
amount remains UNKNOWN.

`FixtureOriginalReferences` adds two separately versioned descriptor kinds:
`preparation_policy` (`G2C-fixture-preparation-policy-reference.1`) and
`preparation_cost` (`G2C-fixture-preparation-cost-reference.1`). Neither needs a
future definition/use hash. The cost reader must have the exact producer binding.
Descriptors contain hashes and source selectors, not payloads or credentials.
Resolution rereads these original sources under current producer and consumer
qualification and validates the retained hash. Existing registry/reservation/scan
descriptor versions and bytes are unchanged. No arbitrary metadata-body issue
API is introduced.

Validation: targeted tests cover bootstrap without a definition, original use
rejection, current revocation, source replacement, unchanged legacy refs,
restart, directory replacement, ambiguous ACK, selected UNKNOWN reconciliation
and unrelated financial activity. Signed private PostgreSQL controls exercise
actual AUTH/MESSAGE admission and original registered Meter/financial reads with
fixture HTTP. Hong Kong preparation, full definition/use publication, isolation
across a live probe and runtime experiment eligibility remain UNRUN.
