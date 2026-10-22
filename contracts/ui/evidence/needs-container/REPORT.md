# CJ006 NEEDS container and unified d688 graph

Started from clean f266935ca21f25ee768a7bc81b656b320fa82080; preserved typed clearf266, Memory5226 and Trip4604 source. Exact owner inputs imported in separate commits (no prep ancestry wholesale):

| Module | Fixed owner input | Local import |
| --- | --- | --- |
| CJNeedsClient | 8c28bcb2facef0c76ebf8b997101c6b18d44f17f | 2d9910e |
| CJMessageClient/shared export | 165a0c0137e9baa59c1cf93df7a67d342b6d5b6a | 3034839 |
| CJAuth NEEDS purpose (includes prior typed clear) | 668d96b8e22227160991e2416dc547dacf12246b | 404b13c |
| CJMemoryClient d688 pin | 012e06686db273a0a7c707fd4e46bf954dc5c341 | b87e9fc |
| CJTripClient d688 pin (business12df unchanged) | 5b277cdd72d68467de1208af009fe9f615fcf7d0 | 85673df |

All five complete module subtrees match those owner fixed inputs. Only CJShell's Package changes its own product dependency/path. Waited for both consumer pins before compilation; no temporary second SDK or edits to other owners' manifests. Used exact imported prepare_generated.py against CJ005 fixedd688c01dc0fb18488a1e9c49414a039ce0126204 to export16 files. New hashes match; old9dc/573 exports remain unchanged.

PASS: actual resolved CJShell graph contains CJShell, CJNeedsClient, CJMemoryClient, CJTripClient, CJMessageClient, CJAuth and **one unique CJFoundation d688 path**. Eight transitive references point to the same path; they are not eight packages. See provenance.json for fixed trees, graph hash and resolved dependency pins. Existing CJShellDemo consumes this package graph; no new formal product App root or live launch is claimed.

PASS:117 functions across17 CJShell suites (`tests.txt`), including10 new NEEDS host functions and all existing clear/Memory/Trip/message/history controls. Because ShellState's shared invalidation hook and the actual shared API graph changed, the whole affected module was run once. A final test-only addition for pending key callback A→B replacement passed separately (`key-reentry.txt`); no unchanged full run repeated. Final count is117 full-run +1 targeted function, not a claimed118-function full run.

NEEDS checks cover explicit unavailable defaults/no automatic GET or save; optional fields and decimal12.3400 preservation; local correction limited to explicit pace with original expectedVersion despite latest9; history/receipt exact revision2 and original bytes rather than latest; filtering another needsID's pending record; null/mismatched revision/cancel unknown results; queued work/editor old selection rejection; account/background late results; current callback/session retirement; duplicate one-use work; missing store/key; synchronous key callback replacement. Canonical clients execute against intercepted GET only with synthetic data/temp encrypted records. No new action or real POST is issued.

PASS: final unsigned arm64 iOS17 simulator-target CJShell build (`ios-build.txt`) compiles the actual bilingual sheet/detail/editor components. No App/simulator/device UI or VoiceOver run.

The documented UI contract checker initially failed because it required the entire API path set to equal only /v1/probe. Root API bytes are unchanged from f266 and already have6 accepted paths. The repair keeps API version1.0.0, exact probe GET shape, RequestId semantics and all7 positive/5 negative UI fixtures, but checks probe presence instead of an obsolete global inventory. `contract-before.txt` preserves FAIL; `contract-after.txt` PASS. No API schema/source was edited to satisfy the checker.

Authored delta: NeedsContainerHost/View, AssistantShell entry, ShellState/ShellView hooks, minimal own Package dependency/path, NEEDS host tests and contracts/ui. Brand/avatar/resources, signing/App files, other module sources and all existing dependency locks are unchanged. Independent gates for the new module and pin combination remain Main's responsibility; author results do not replace them or close Issue14/I. Public production POST stays closed; actual trusted account/source collection/extraction, live endpoint, Keychain, user save, device and release remain UNRUN.

Commands: established module-cache environment; swift test --disable-sandbox package CJShell using /tmp/cj006-sdk-host-build and /tmp/cj006-spm-cache; final unsigned iOS build uses /tmp/cj006-memory-ios, arm64-apple-ios17.0-simulator, iPhoneSimulator27.1 SDK and target CJShell with SDKROOT unset. Actual graph uses swift package show-dependencies --format json with /tmp/cj006-needs-graph scratch, resolved from existing local cache. UI checker: python3 contracts/ui/check_contract.py.
