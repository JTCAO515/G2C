# CJ006 accepted-message RUN container and unified c02 graph

Base144eff8458f26b34f43cb6ed93ec8a47c7a469aa. Original NEEDS144, Feedback79c/f19 and all old FAIL/evidence preserved. Exact producer imports, separate from authored host source:

| Input | Owner fixed | Local import |
| --- | --- | --- |
| Run client | 84f41e1d5c76db789565e46fb05377f27fedea45 | 3e03ae7 |
| Shared SDK export | 540da02a335e96e98917ffd3d94a395f8ca2d892 | 1ccb94a |
| Memory c02 pin | 4eac4ee563eafd44c26438902077839bcc558989 | b06976e |
| Trip c02 pin | b7966a1a95ed3e9b4c701f616693cf7e13d2d313 | 54da082 |
| NEEDS c02 pin | 25e50dbc25cc5aa9443b2d6da50c514528b2b3c6 | b594300 |
| Feedback c02 pin (business f19) | 147a9ae3d9dc9e1b182c6f9b01482dfe5f6fcc53 | b691b76 |

Imported full shared540 unchanged, not the RUN clone's three-file prep or unrelated ancestry. All six final module subtrees match owner fixed trees; AUTH remains exactf2c. The exact540 script exported official c02cf08e52a0d8ffc2fefac99226654a7e01539c16-file package. New and prior201156/d688/9dc/573 exports hash-match and remain intact. No a5f evidence hash, manual generated edits, second SDK or other-owner source changes.

PASS: actual CJShell graph contains CJShell, CJRunClient, CJFeedbackClient, CJNeedsClient, CJTripClient, CJMemoryClient, CJMessageClient, CJAuth and **one unique CJFoundation c02 path** (12 transitive references). Source trees, graph hash/nodes, export hashes and unchanged resources/locks are in provenance.json. Package compilation is not a real App authorization claim.

## Actual source path tested

Synthetic MESSAGE is staged and marked queryRequired using canonical recovery (no POST), then actual generated MessageHTTPClient.query accepts a matching receipt and stores its typed encoded payload. CJShell captures that exact current accepted record; RunDisplaySource receives the original generated receipt and original session operation. Actual generated RUN GET reads only that message. No fixture-only host receipt shortcut is used in positive integration tests. Negative cases deliberately inject malformed/hash-mismatched accepted payloads or staged/notObserved state and prove no RUN work is created.

PASS:35 test functions in6 affected suites (`tests.txt`): RunContainerHost plus existing AssistantMessageHost/local recovery list, identity/reentry and ShellState controls. New cases verify7 status/partial/complete states, exact Unicode/query source, no duplicate body persistence, original input/receipt retention, queued A vs selected B, selection callback reentry, late A response, background queued work/reselection, account/session retirement and failure hiding old fallback. Original127/full module and unrelated144/79c suites are reused, not rerun wholesale.

One adjacent author check exposed a host cleanup mistake: canonical select could return false after a newer prepare won inside its callback; host then cleared that work. `select-reentry-before.txt` preserves3 runtime failures. Removed only the duplicate host cleanup and left canonical model responsible. The final35 run includes that regression PASS. A later test-only expansion checks message-binding callbacks at4 capture/selection positions; all4 PASS in callback-positions.txt (same function, not4 new functions). No product change followed final iOS build.

The initial new test helper did not compile because a class-only credential protocol was modeled as a struct and Swift Testing expressions needed explicit nested try/separate closure input. Those test setup diagnostics are losslessly preserved in initial-test-compile.txt.xz with hash in provenance.json; corrected before any runtime assertion. The synthetic accepted-query setup was also aligned with canonical queryRequired state before runtime. These are not producer failures or claimed behavior regressions.

PASS: final unsigned arm64 iOS17 simulator-target CJShell build (`ios-build.txt`) and UI contract7 positive/5 negative sample check (`ui-contract.txt`). No App launch, simulator/device rendering, VoiceOver, real account/Keychain, HTTP socket, PG, worker/provider, streaming, server cancellation, signing or deployment.

## Limits and ownership

Authored only CJShell RunContainerHost/View, read-only accepted-receipt capture and synchronous RUN invalidation hooks in AssistantMessageHost, Assistant flow/identity/background wiring, own Package dependency/path, related tests and contracts/ui. Prior Account/Needs/Feedback/Trip/Memory business host source, brand/resources, other module source and existing locks unchanged. No source identity or answer invented. Exact live credential/root composition remains unconfigured: root must provide the accepted credential callback/model and original verified session operation; CJShell does not derive bearer/identity itself.

Independent RUNclient/SDK/pin/host gates remain Main's review/testing responsibility. This read-only candidate does not close original Issue11 streaming/stopping/provider/I, or waive another domain's gate. Default POST/write gates unchanged.

Commands use established local module caches. Tests: swift test --disable-sandbox package CJShell, scratch /tmp/cj006-sdk-host-build/cache /tmp/cj006-spm-cache/--disable-automatic-resolution, filter 'RunContainerHostTests|AssistantMessageHostTests|LocalRecoveryListHostTests|IdentityCallbackReentryTests|IndependentHostReentryTests|ShellStateTests'; final callback expansion filters selectionCallbackCannotAdoptNewMessageUnderOldCapture. iOS uses existing /tmp/cj006-memory-ios, SDKROOT unset, arm64-apple-ios17.0-simulator/iPhoneSimulator27.1, target CJShell. Actual graph uses /tmp/cj006-needs-graph show-dependencies --format json after all fixed inputs; UI checker unchanged.
