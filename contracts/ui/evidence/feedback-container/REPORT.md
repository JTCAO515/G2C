# CJ006 Feedback two-entry container and unified 201156 graph

Base6128d42bc5c205086ed343755df553300bb0e624 and original acfb/f266/5226/4604/alias evidence preserved. Owner inputs were imported as separate exact commits, never edited by CJ006:

| Module/input | Owner fixed | Local import |
| --- | --- | --- |
| Feedback client | 69d679e849c6245b5098c1e5967a68a88efffd7e | 1673010 |
| Shared export / CJMessageClient | 514e0e3a80bd9a3e34248122915d52c86ee46230 | fe5bb66 |
| AUTH Feedback key purpose | f2c01d7e9e3292b7d8bcc207b965bf6a36cec96c | 38c5e39 |
| Memory201156 pin | d7f57ec549312f6cfc9951ddda4dce3d759baeda | 0730a77 |
| Trip201156 pin | d5769223e6edb87a547403c4eaac5860d484a662 | 2d6c4cd |
| NEEDS empty/nonempty final directory repair | 5ef0d75acf7c41f400fac833ed5fa654872b82e6 | 4d5900f |
| NEEDS201156 pin (includes cd33/5ef business fixes) | 3625cff8ba285296a92d3ea7cc34eec659a0e091 | 478e19b |

Waited for final NEEDS repair/pin before compiling the complete graph; no temporary second SDK or private manifest edits. Six final domain/shared module subtrees match their fixed owner trees. Ran the exact shared514 export script against official API201156c9bf9850f9b8e87dc1f986452ce1ae789f;16 new files hash-match, and the16 files in each prior d688/9dc/573 export remain intact.

PASS: actual CJShell graph contains CJShell, CJFeedbackClient, CJNeedsClient, CJTripClient, CJMemoryClient, CJMessageClient, CJAuth and **one unique CJFoundation201156 path** (10 transitive references). Actual graph hash/nodes/fixed trees/source protection are in provenance.json. Existing CJShellDemo uses this package graph; no formal product App/root or runtime launch is claimed.

PASS:127 functions in18 CJShell suites (`tests.txt`), including8 Feedback host functions with parameterized cases. Shared ShellState.apply/identity cleanup and the final SDK graph changed, justifying one complete affected-module run. An extra test-only callback-during-prepare case passed separately (`prepare-reentry.txt`); report127 full-run +1 targeted, not a claimed128-function full run. Prior targeted failures and independent holds are not erased.

Feedback tests prove: explicit unavailable default/public POST gate; answer and general empty text/opt-in separation; rejection of stale answer revision, implicit general context and shared client; no transcript prefill; language preserves voluntary edits; new answer retires old queued association while keeping general draft; binding callback source change; original general-null or linked-source receipt says submitted only; wrong hash/null/cancel retains original and cannot resubmit; account/background late query cannot reach B; missing store/key recovery failure; and answer change inside prepare cannot freeze/persist/dispatch old source. Actual generated clients use in-process intercepted GET for recovery. Synthetic prepareSubmit exercises only pre-dispatch fencing; no POST reaches transport. Public constructor's submit remains unavailable before credential/storage access.

PASS: unsigned arm64 iOS17 simulator-target CJShell build (`ios-build.txt`) compiles actual FeedbackView in both surfaces and all final fixed modules. Product source was unchanged after that build; only the final test/evidence was added. PASS: existing UI contract script (`ui-contract.txt`). No App/simulator launch, screenshot, VoiceOver, physical device, account, Keychain, live HTTP, PG, signing or release run.

Authored source is limited to FeedbackContainerHost/View, Answer/Memory entry wiring, ShellState answer revision/cleanup, ShellView composition, own Package product/path, host tests and contracts/ui. No feedback form/wire/provider reimplementation. Brand/avatar/assets, original AccountHost, NEEDS/Trip/Memory host business source, other module source and existing lock bytes remain unchanged (except the exact imported producer fixes/pins listed above).

NEEDS cd33 timezone and5ef pending repair, their201156 pin, and Feedback69d remain independently gated inputs. This container's local passes do not independently accept the entire NEEDS/Feedback combination, close Issues14/15 or authorize real POST. Real trustworthy answer/root source collection and account/resources/retention activation are still UNRUN; default screens are unavailable.

Commands use the established local CLANG_MODULE_CACHE_PATH and SWIFTPM_MODULECACHE_OVERRIDE. swift test --disable-sandbox package CJShell/scratch /tmp/cj006-sdk-host-build/cache /tmp/cj006-spm-cache/--disable-automatic-resolution (full; final single filter answerChangeInsidePrepareCallbackCannotFreezeOldAssociation). iOS build uses /tmp/cj006-memory-ios, SDKROOT unset, arm64-apple-ios17.0-simulator, iPhoneSimulator27.1 SDK, target CJShell. show-dependencies --format json used /tmp/cj006-needs-graph scratch after all fixed inputs; UI checker python3 contracts/ui/check_contract.py.
