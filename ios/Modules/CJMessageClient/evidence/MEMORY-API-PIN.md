# Shared CJAPI export advances to fixed Memory API candidate

Independent owner checkout cj-009-memory-api-pin, branch cj/009-memory-api-pin,
base actual merged main23e12f28435ab0ddc685d544670564e3fa79db41 (Publish local Git readback).
Original625b66d and dependency repair3c6de6a trees preserved, not rebased/overwritten.

Fixed producer57336d501e5691302a3d5e9770f07666d1c57d4a, not claimed merged main.
Single shared path for Message, future Memory and Shell consumers:

`ios/Modules/CJMessageClient/.generated/57336d501e5691302a3d5e9770f07666d1c57d4a/CJFoundation`

prepare_generated.py and this module's Package.swift now pin that exact revision.
Export still includes fixed manifests, official Sources and Tests; mandatory whitelist
asserts MemoryClientConfiguration.swift alongside Package.swift/Package.resolved so the
non-Generated helper cannot be silently omitted. Sixteen exact source files exported,
all hashes in generated-pin.json; helper SHA256 additionally in memory-api-pin-provenance.json.
No generated file rewriting or per-consumer second CJFoundation identity introduced.
Formal ../CJAuth CJMessageKeys dependency remains intact; no temporary key interface
package is restored. Original brand/CJShell/Auth source and manifests unchanged.

Read-only comparison against previous2f8 official OpenAPI: all five existing message/
draft paths and ALL existing component schemas are exactly unchanged. New Memory
schemas/operations are additive. Existing MESSAGE original-byte, required-null, cursor,
recovery and once-only/live-write rules are not edited by this pin change.

PASS: Standalone CJMessageClient Swift6.4/macOS package compilation and31 targeted tests:
13 TransportTests +8 HistoryReadTests +9 DraftPutTests +1 MemoryConfigurationExportTests.
The new test actually imports CJAPI and compiles Client(configuration:.memory) from the
exported helper, with a transport that would fail if called. Existing suites use only
synthetic interception/local data. This is NOT real Memory service/SDK account/Keychain/
HTTP write acceptance. Producer's date behavior/5-op evidence remains producer evidence;
this smoke test proves the helper is in this SAME compiled CJAPI module.

Cache copied locally from the previous owner dependency-fix checkout. Resolved states
all match fixed main CJAuth/CJShell lock states; runtime1.13.3, urlsession1.3.2,
http-types1.8.0 and formal AUTH closure unchanged. No dependency upgrade. Standalone
SwiftPM's expanded temporary Package.resolved was retained in ignored .build evidence,
then restored to source base; no lock/config authority expanded. Exact state inventory
and full log hash in memory-api-pin-provenance.json; concise output in memory-api-pin-tests.txt.

Full CJShell combination is deliberately UNRUN: its direct dependency still points to
old2f8 and ONLY CJ006 may update that manifest to the same shared573 path. Do not claim
whole-main graph/brand App build success from this standalone result. No other active
CJFoundation copy should be introduced to evade that required common pin.
Independent Review/Testing pending; no server, network business call, Keychain, PG,
POST/PUT activation, push, merge, deployment or signing change performed.
