# CJ-017 P2 preparation reentry repair

Repair base: `79b4f53e82eeaf37ab883b4f7e60a3962757669f`.
Shared input remains f4c17b5 in separate prep287db1f. No newer shared input is imported.
Scope: only `ios/Modules/CJManualPreviewClient/**`; original036/79 evidence preserved.

Independent source:
`cj-testing/CJ-017-readonly-preview-client/REPORT.md`, its snapshot's
`IndependentPreparationTests.swift` and `independent-preparation-tests.log`.
The test is copied byte-for-byte into this module, not rewritten. `sha256.json`
records matching source hash plus the captured before/after outputs.

## Root cause and repair

The prior guard only captured draft revision. The original Trip binding callback
could synchronously prepare newer work with the SAME revision. After that callback,
the old outer preparation assigned active to its own new ID, displacing the callback's
valid newer work. Discarding the older returned work left newer work unable to send
and the editor stuck loading. The prepare method was unchanged since036.

The editor now reserves a separate preparation UUID BEFORE its first source callback.
Both original prepare checks compare that owner before and after callbacks, in
addition to existing revision/source/session checks. A nested newer prepare supersedes
this ID; the old outer throws retired before assigning active/started/status/result.
No cleanup/finally clears newer state. The old caller need not perform or cancel.
This is transient preparation ownership, not a business ID, lock, queue or authority.
The existing work/revision/ABA/cancellation/single-use guard remains in place.

## Actual narrow verification

1. Before source repair, exact independent test:
   `swift test --disable-sandbox --package-path ios/Modules/CJManualPreviewClient
   --scratch-path /tmp/cj017-manual-preview-build --filter IndependentPreparationTests`
   **FAIL**: one function, the exact two original assertions (zero requests and
   loading). `replay-before.txt`; Testing's original log also preserved unchanged.
2. After repair, exact test plus affected controls:
   same command with filter
   `'IndependentPreparationTests|PreparationOwnershipTests|LifetimeTests|ReadonlyCapabilityTests'`.
   **PASS**: 19 functions across four suites, including parameterized cases.
   `replay-after-controls.txt`.

New controls cover nested prepare at BOTH first and last original source callback,
explicit outer retired result, newer work running exactly once, ordinary same-revision
sequential preparation with the old caller unused, older perform withholding without
clearing newer success, and callback cancel/edit retirement. Existing affected controls
cover original source/session, edit ABA, cancellation/reentry, final callback ownership,
old error/new work, credential/body/await retirement and current opt-in guards.

No unrelated PreviewTests suite, producer/Trip/Auth suite, full iOS build, actual
network, service, account, Keychain, SQL, save, confirmation, deployment or publish
was run. Swift test compiles the changed module and target tests. Prior validation
and actual-device/UI/I boundaries remain separately attributed, not upgraded.
The shared f4 ordinary Host-routing P2 remains a separate dependency HOLD with its
original owner; this local preparation repair does not resolve or bypass it.

No shared/Shell/Trip source, Package, generated SDK or registry edit was made.
No debug instrumentation or new dependency was introduced. Independent re-review/
testing of this repair remains pending. No push/PR/merge was performed.
