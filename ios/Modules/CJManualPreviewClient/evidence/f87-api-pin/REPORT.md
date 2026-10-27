# CJ-017 fixed f87 compatibility in isolated module closure

Consumer base `e98f9cd31a8117dce16bb6d7373a65203b1cc393`; businessdb48855 unchanged.
Exact inputs explicitly delivered by Main:

- Shared `5075bcf604e959d5c4592071a1e9de39d8687395`, Git objects read only from
  <local>/Documents/Codex/2026-10-21/cj-009-memory-api-pin.
- Trip `a5cc42005c69811ccb05754793107141fb4a9f02`, Git objects read only from
  <local>/Documents/Codex/2026-10-21/cj-015-trip-client.
- Official SDK `f87a78a9d8984c59905e385483f17dddd8144d8a` from cj-005-foundation.
- AUTH: exact existing module tree from this consumer's e98f9cd baseline, not a
  moving/new owner version. No AUTH source edit or new identity authority.

Local isolated preparation/evidence commit:
`64a3a5174c1243e36f5eef0b8cd66d1651bfc0f9`. Exclude local prep from product delta.
The feature product changes only its Package.swift direct SDK path33→f87 plus evidence.
A module-local .gitignore keeps the authorized .build assembly outside tracked files.
No business Sources, Tests, Package.resolved, factory activation or permission changes.

## Exact isolated preparation

prepare_isolated.py reads ONLY the fixed Git objects above, rejecting non-regular Git
entries and refusing to overwrite an existing assembly root. Shared/Trip/AUTH are
exported beneath THIS feature's ignored `.build/f87-5075-a5cc/modules`; this feature's
candidate manifest, exact lock and unchanged Sources/Tests are copied into its sibling
module there. The single SDK export is placed only in the isolated shared owner's
fixed designated `.generated/f87.../CJFoundation` path. All16 SDK blobs match the
fixed shared manifest's SHA256 and exact official Git source bytes. No SDK is copied
into this feature's source or into a canonical sibling's tree.

isolated-inputs.json.xz records every prepared file's original Git source and SHA256;
its exact original hash/length is in isolated-inputs-archive.json. All recorded bytes
were rechecked unchanged after validation. No shared moving HEAD (including20aa)
was read or substituted. canonical tracked Message/Trip/Auth paths were checked with
git diff --exit-code HEAD and remain untouched. Earlier c5/9d/33 canonical ignored
exports each retain all16 exact original bytes; locks and all old FAIL evidence stay.

## Actual affected checks

PASS isolated actual single f87 graph: swift package with package-path
`ios/Modules/CJManualPreviewClient/.build/f87-5075-a5cc/modules/CJManualPreviewClient`,
scratch-path `/tmp/cj017-manual-preview-9d-build`, --skip-update,
--force-resolved-versions, show-dependencies --format json. Four references resolve
to ONE exact isolated f87 path, no conflicting identity warning. graph-check.json and
archived raw graph/diagnostics capture this result. Scratch name is historical;
actual source/package/SDK paths select f87.

PASS module compile and five relevant test functions / three suites: swift test
with the same isolated package/scratch, --disable-sandbox --skip-update
--force-resolved-versions and filter
'exactOptInRunsOfficialClientAndPreservesFrozenNFDRequest|IndependentPreparationTests|PreparationOwnershipTests'.
Actual generated getTrip produces the closed accepted source; generated preview
through actual shared capability checks frozen NFD/base bytes/version, can_savefalse
and original work validators. The exact independent prepare repro, first/last callback
ownership, single-use/newer work, discarded older caller and cancel/edit controls pass.
No direct network interceptor bypass or fake accepted handle is used.

PASS normal-import public API typecheck against built isolated f87: both public
constructors, original Trip/source/session parameters, prepare→Task.perform and the
Chinese SwiftUI component. Exact xcrun swiftc command/exit/hash in public-api-check.json;
no @testable import in PublicAPIConsumer.swift, and its functions are never invoked.

PASS preservation: consumer Sources/Tests/lock equal e98f9cd; one manifest replacement.
Twelve affected generated schema/Client/Operations blocks are literal unchanged from33.
Fixed shared Transport equals exact94 Host-guard bytes. preservation.json records
these checks, every isolated recorded file check and prior SDK byte retention.

No unrelated full suite or generic iOS build rerun. Existing business/Host/codec/iOS
results keep their original fixed-input scopes and are reused, not relabeled as new
f87 App/network/device acceptance. Deprecated skip-update and generated import warnings
are retained in the raw logs; no source was rewritten to remove them.

## Remaining graph and authority boundaries

No missing fixed dependency remains for THIS isolated module closure. The canonical
consumer working tree's sibling manifests/SDK paths were deliberately NOT repinned or
exported: standalone canonical closure and final CJ006 App closure still require Main/
original owners to consume exact shared5075 + Tripa5 inputs. This isolated result does
not prove the App graph and does not grant sibling writes. It is not a reason to wait
on an old33 tree or guess a new moving head.

Candidate independent Review/Testing is pending. App factory/product permissions,
new source/attempt integration, actual source/account/provider/API/network, product
cache/Keychain, SQL/device, rendered UI/VoiceOver, save/confirmation/lock/feasibility and
complete Issue I remain UNRUN. No factory was enabled, no actual saving or cache action
was added, and no new runtime abstraction/library/SDK identity was introduced.
No push/PR/merge/deploy/main update. Only compiler scratch and ignored local assembly
were written outside this module's tracked pin/evidence files. Canonical tracked siblings
remain byte-identical to their starting state. Logs are losslessly xz archived with
exact hash/length metadata; final commit leaves tracked/unignored worktree clean.
