# CJ006 manual-preview host candidate

Started from clean e82703a6dbdfd35ab6e3ff769c6878982c8af0f5 on cj/006-session-bridge-host. Kept all old fixed/FAIL evidence. Repository origin is the local Publish checkout, which has no branch named main; initial fetch origin main failed without changing source. Its cached origin/main was old PR42 and was NOT valid live-main proof. Corrected the initial commentary: official GitHub branches/main read e828f1e385b384963ba3aa2e455abd836e3a1f67; that commit's CJShell Sources tree equals e827's64749caeeac9ee280f12c5a7ae0949935d728013 exactly. Exact commit ancestry is not asserted. No whole-main merge/reset or shared checkout mutation was performed.

## Fixed owner inputs, imported separately

| Input | Original fixed | Local preparation |
| --- | --- | --- |
| Manual client initial product | e080fb7 (full product) +036de8de060ea8d84dc976862907ec5fe9c978c7 | a0d9a53 +27b2968 |
| Trip accepted bytes hook | 2b2991871ce4e04bd1bfb5a92f3098e01512800a | 6078ebc |
| Trip c5 pin | f931d5834d8a5162b223a8607b83d27d3639afe7 | c1cb444 |
| Shared c5 export | 3090777b4e10a6135823e3342e5e8b6c34aa9e6b | 41df7b8 |
| Shared exact readonly preview transport | f4c17b59213828543cef042d127c56d8467963d8 | 8404734 |
| Manual client per-work transport consumption | 79b4f53e82eeaf37ab883b4f7e60a3962757669f | 1658324 |
| Memory c5 pin | ba9ed1a81dc4ac035980b62f7cb95fb48ede07a4 | 5f5d8ec |
| NEEDS c5 pin | ab7d82c504f6816b2a1224f3747f41df7d651429 | 1ffdb2f |
| Feedback c5 pin | 9b677b057a164595be673199a9a34dff12c588ba | 96b17cc |
| RUN c5 pin | e066043b3bf643b3711ad8e53e5cf03e0b56f550 | e13d4dc |

No prep ancestry wholesale, other owner edits, USAGE5d/9d source/export or temporary second SDK. Actual current Trip/Manual/Message and four consumer subtrees equal their final fixed heads; AUTH is unchangedf2c. Exact shared script exported only c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a16-file package; c02 and five previous export versions remain intact/hash-matched. Source309 and later producer evidence348 are not confused as SDK identities.

PASS: actual CJShell graph lists CJShell/CJAuth/CJMessageClient/CJMemoryClient/CJTripClient/CJNeedsClient/CJFeedbackClient/CJRunClient/CJManualPreviewClient and **one unique CJFoundation c5 path**, through16 transitive references. Fixed trees/graph/export/lock/resource hashes are in provenance.json. Direct Shell dependency/path is its own necessary hunk only. Existing package libraries/versions and locks unchanged.

## Product source and tested behavior

Trip detail now opens a local-draft sheet after an explicitly prepared canonical formal getTrip yields a closed accepted snapshot. No public accepted handle is fabricated from TripRecord/proposal/version. Missing resources or actual null getTrip never creates an editor. The public host factory uses79b's actual explicit preview timeouts; original credential callback and SessionOperation are supplied unchanged. Root endpoint/resources remain explicit and absent by default.

ManualPreviewView is reused for scope/title/text/order, prepare-before-Task, local status and server diff. No local patch/diff engine, save/confirmation/lock/feasibility permission or business action ID. Source-read work is captured, single-use, cancellable and fenced after callbacks/await. Selection including ABA invalidates canonical snapshots; account/background/editor retirement is synchronous. An old close entry cannot retire a newer editor. Closing a draft requires explicit discard confirmation;409/unknown retain the original source version and draft and never auto-rebase. Leaving detail cancels pending manual-source reads so a late completion cannot open an editor from an obsolete route.

The public Trip prepareTrip API now invokes host callbacks while retiring snapshots. The shell's existing reserve method therefore rechecks its original action after preparation before claiming a new epoch; this is needed compatibility with2b299 and remains inside the host lease.

PASS: **25 test functions in2 affected suites** (`tests.txt`):11 ManualPreviewHost functions plus14 existing TripContainerHost controls. Covers actual closed source GET/received raw bytes, server title diff/can_save=false/UNKNOWN,409/503 draft and exact retry bytes, legacy generic transport refusal, public-factory retirement before transport creation, null source, selectionABA/old close, background cancellation and healthy newer work, final session callback withholding candidate/settling busy, queued revisionABA, and last shared validator changing foreground or editor revision before dispatch. Existing Trip origin/query/unknown/callback controls remain PASS. Old other-domain suites/I were not rerun or relabeled.

Positive preview tests use an internal host factory with the REAL PreviewEditor, REAL public closed Trip API, generated Client/Types and REAL shared NoRedirectTransport capability checks; only the last URLSession transport is replaced by the shared owner's existing internal in-process interceptor seam. The actual client supplies the original per-work validator. Request bytes, responses and error paths execute through those checks. This is not a fake accepted-source constructor, product alternate transport flag or a real HTTP request. The public factory's actual networking path is compiled but deliberately retired before network in its runtime control. Legacy public generic transport actually refuses POST and retains draft. No application credentials/network were used.

PASS: unsigned arm64 iOS17 simulator-target CJShell compilation (`ios-build.txt`) after all fixed inputs; only tests/docs changed afterward. PASS: unchanged UI contract7 positive/5 negative checks (`ui-contract.txt`). While waiting for pins, only syntax parsing was done; it was never counted as module/runtime acceptance. No failed assertion/setup compile occurred in this host check sequence.

## Scope and gates

Authored only TripContainerHost/TripShell, ManualPreviewResources/ContainerView, own Package product/path, host tests and contracts/ui. An internal factory exists only for offline integration tests; public host construction always uses the actual public timeout initializer. Old Account/Memory/NEEDS/Feedback/RUN business host source, brand/resources, App/signing/scripts and existing locks are byte-identical to e827. No domain, transport, API, source store or authority was privately edited.

All tests are synthetic/local/intercepted. No real account, endpoint/credential activation, URLSession dispatch, Keychain, SQL/PG, provider, App/simulator launch, device/VoiceOver, live redirect, signing, deployment or complete Issue22/I result. Readonly computation POST compatibility is distinct from real service acceptance; actual save/confirmation remains unavailable and every accepted preview has can_save=false. The individual four pins/f4/79/f931 and host independent gates are Main's responsibility, still not replaced by author passes.

Commands: established local module caches; swift test --disable-sandbox package CJShell/scratch /tmp/cj006-sdk-host-build/cache /tmp/cj006-spm-cache/--disable-automatic-resolution --filter 'ManualPreviewHostTests|TripContainerHostTests'. Unsigned build at /tmp/cj006-memory-ios with SDKROOT unset, arm64-apple-ios17.0-simulator/iPhoneSimulator27.1, target CJShell. Actual graph uses /tmp/cj006-needs-graph show-dependencies --format json after all c5 pins. UI checker python3 contracts/ui/check_contract.py.
