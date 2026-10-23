# CJ-017 formal dc29 pin, fixed-input isolated consumer proof

Starting, preserved f87 successor: `a56105628f062e0a8b00db10f649b26751382d48`
(its business source is unchanged since db48855). The previous f87 and20aa fixed Git
objects, ignored assembly copies, failures and evidence remain intact; this candidate
does not relabel their validation as dc29/App acceptance.

Main-delivered exact inputs:
- shared `9b4852dfad418d124d60366ada8efb380a8ffc1d` (independent dual PASS).
- Trip `7bcab1b13bc683c205f3ff0fa4446657427a5225` (its fixed-candidate gate remains separate).
- official SDK `dc29bb3634e63d8f065c38d39a7a0059f76cfa53`.
- AUTH existing source/test/package from this consumer's a561 baseline; byte-identical
  to `4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e` for those paths. Historical
  AUTH documentation/evidence differences are not imported as runtime authority.

Local exact-input preparation commit: `bb6343cbd723163dcd77a1f98f9dfe791d996768`.
Exclude this local preparation/evidence from the product pin delta. The only formal
product manifest change is this module's Package.swift SDK path20aa→dc29. No Sources,
Tests, Package.resolved, new SDK library, alias, save/factory/permission or business
abstraction is authored. This is a necessary consumer dependency for the new host,
not new manual-edit behavior or authorization to activate the host.

## Preparation and preservation

prepare_isolated.py reads the three fixed Git object sets above. It rejects non-blob
entries and an existing output root. The assembly is under this module's ignored
`.build/dc29-9b48-7bca/modules`, separate from the retained old20aa/f87 assemblies.
It copies this feature's current manifest, exact original lock and unchanged source/
tests. The only active SDK is the one placed under the isolated shared package's
`.generated/dc29.../CJFoundation` path. All16 SDK files equal their official Git
blobs and the fixed shared export's SHA256. Nothing is written to canonical sibling,
new Shell, root API or previous SDK export paths; no moving HEAD was read.

isolated-inputs.json.xz records 343 prepared files with original source and SHA256.
All new input files and all retained20aa files were rechecked byte-for-byte after
validation. Consumer Sources/Tests/lock equal a561. Canonical Message/Trip/AUTH
tracked paths pass git diff --exit-code HEAD. Twelve affected getTrip/manual-preview
generated schema/Client/Operations blocks are literally unchanged from20aa.
The fixed shared Transport hash is recorded without rewriting its body. Detailed
hashes/checks are in preservation.json.

## Actual affected checks

**PASS single dc29 module graph.** `swift package --package-path
<module>/.build/dc29-9b48-7bca/modules/CJManualPreviewClient --scratch-path
/tmp/cj017-manual-preview-9d-build --skip-update --force-resolved-versions
show-dependencies --format json` resolved four references to ONE exact dc29 path;
no conflicting package identity warning. graph-check.json records the selected path.
The scratch directory name is historical; the graph's actual source and SDK are dc29.

**PASS module compile and 5 targeted test functions / 3 suites.** `swift test` with
the same isolated package/scratch, --disable-sandbox --skip-update
--force-resolved-versions, filter
'exactOptInRunsOfficialClientAndPreservesFrozenNFDRequest|IndependentPreparationTests|PreparationOwnershipTests'.
Actual generated getTrip creates the closed accepted source. The generated readonly
preview path preserves frozen original bytes/NFD/version, returns can_save=false, and
checks original work ownership. Exact independent prepare reentry, first/last
callback ownership, newer single use and old caller cancellation/edit controls pass.
Only in-process synthetic credentials/transport are used.

**PASS normal-import public API compile.** PublicAPIConsumer.swift typechecks against
the freshly compiled isolated dc29 module, covering original Trip/source/session
inputs, both public constructors, synchronous prepare→Task.perform and Chinese SwiftUI.
No @testable import or function invocation. Exact command/exit/hash are in
public-api-check.json. The public compiler run is not a rendered UI or device test.

Older broad business/Host/codec/iOS evidence is reused at its original fixed input,
not rerun or promoted to new product acceptance. Existing generated-import and
deprecated skip-update diagnostics remain in original logs. No unrelated full suite,
iOS build, service, real account/API network, product cache, Keychain, SQL, device,
model/provider or save/confirmation action was run.

## Remaining conditions

No fixed input is missing for THIS isolated module closure. The canonical App and
new host fca5 graph were not imported, repinned or tested in this scope. Main and
original owners still must consume shared9b/Trip7bc plus this formal dc29 pin in
the intended App graph, and clear the separate Trip/consumer candidate gates.
This isolated result does not prove an actual source/attempt authority, real TTL,
permission, account/credential, host factory activation, UI, save/confirmation,
lock/feasibility or complete Issue I. Those are UNRUN/UNKNOWN as appropriate.

No push/PR/merge/deploy/main write. All log bytes are losslessly xz-archived, with
original SHA256/length in log-archives.json. No prior FAIL or dirty user work was
removed. Final tracked/unignored worktree is clean after the candidate commit.
