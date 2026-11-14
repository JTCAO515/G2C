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

`PreparationLifecycle.begin()` retains the actual original financial start before
preparation. `close()` compares every new HK scoped financial attempt with the
selected native MESSAGE operations, including failed/unknown attempts, and
checks terminal delivery ACK and associated-history coverage. Missing operations,
borrowed pre-start attempts, unacknowledged tails or uncollected history jobs
remain UNKNOWN. The start cannot be replaced to reset the interval. Close ACK
uncertainty is query-only. Later independent activity does not rewrite a closed
interval; selected original changes still withhold it. The separate descriptor
`G2C-fixture-preparation-lifecycle-reference.1` reads only this retained source
under current producer/consumer qualification.

This coverage is explicitly the original scope financial interval plus declared
messages. It is not manual Trip-action coverage, a complete definition/use,
concurrency isolation or task PASS. The accepted definition publisher must also
bind its original manual actions, native Trip receipt and current source before
it can admit reuse. A legacy unscoped financial ID cannot prove this scope
coverage and remains outside-interval UNKNOWN.

Worker manifest `G2C-runtime-host.2` adds one explicit `fixture_preparation`
configuration; frozen host.1 accepts no extra field. Its exact
`G2C-fixture-preparation-host.1` record selects the already authenticated C and E
bindings, the approved purpose digest, at most three original MESSAGE IDs, an
original policy, pinned private directories, a frozen native source-state file
and the existing release control path. This is B deployment configuration, not
RPC/task input. The existing HK entrypoint injects its native checkpoint reader;
there is no new standalone deployment authority or implicit import dependency.

After evidence attachment, the factory connects preparation policy, frozen cost
and lifecycle original readers to E's existing collector. Each read requalifies
both bindings/current pins and the exact native source state. Changing the
retained state file, Trip baseline, source/session or qualification withholds
metadata. Inactive original credentials do not attach a fixture reader and keep
the existing ordinary-traffic startup isolation. The factory starts no
preparation, creates no financial attempts, and issues no metadata or reservation
at boot. A final definition publisher is still not connected; reserve fails
closed, E still lacks the full legal task set, F teacher stays disabled, and the
existing RPC/G versions and default worker configuration remain unchanged.

Lifecycle close retains an independent O_EXCL native end witness before writing
the derived report. It fixes the original financial row watermark and immutable
identity digest. Resolution enumerates that exact original database range again
and verifies the complete producer-scope attempt set; removing a saved unmapped
row and adjusting status cannot hide an original INTENT. New later rows remain
outside this closed interval. End-witness ACK uncertainty leaves the original
range intact and is query-only, without creating a replacement interval.
