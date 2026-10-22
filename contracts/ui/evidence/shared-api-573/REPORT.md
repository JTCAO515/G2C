# CJShell shared CJAPI573 alignment — separate from host P2

2026-10-22. Host fix fixed first at **33829deaa99173f24ba622141521a2df30d7f335**, after exact Auth ab37 intake (a19db476ba81827fd2c281f96ca9fe9e06212761). Its ownership24-test result remains independent of this pin step. The small later cdf541f note corrects transient lock-status provenance only, not host code.

Producer source was located through the official CJ009 chat readback: `/Users/jtsm5p/Documents/Codex/2026-10-21/cj-009-memory-api-pin`, fixed **d0f396ceaff5a7d51ddc3a623b35e3eef9191412**. Original cj-009-message and Publish checkouts did not contain this object; no guessed moving source was substituted. Normal exact intake merge **50b13bb745e012759ceb67976aa80fea96ad46d2** imported the producer's export/script/manifest evidence unchanged.

Own Package-only commit **03063cd752863af8cb6fd01da0984c826a03f479** changes exactly ONE direct dependency path:

`../CJMessageClient/.generated/2f8be7c3e2dd298457488412b3a5e3b2ca59ca93/CJFoundation`
→ `../CJMessageClient/.generated/57336d501e5691302a3d5e9770f07666d1c57d4a/CJFoundation`.

All Auth/CJAuthSupabase products, brand resources and other package bytes are unchanged. No second active CJFoundation dependency, new wrapper, lock upgrade or brand edit. Existing old ignored exports are not deleted and are not referenced by the active graph.

Ran unchanged producer prepare_generated.py against exact CJ005 git objects, after target/ancestor symlink checks and confirming the new directory absent. Verified all16 SHA256 hashes and required non-Generated MemoryClientConfiguration.swift. generated-pin.json has no diff from d0; no manual generated source edits.

PASS: CJShell graph compile plus20 affected ServerHistoryHost/ServerDraftSaveHost test functions using actual generated/client code with purely synthetic interception. Existing GET/cursor/original CAS/unknown/cancel gates remain. PASS: unsigned iOS CJShell module build, arm64 iOS17 simulator target / installed SDK27.1. No App signing/launch/device, actual Memory/server request, Keychain/account/network business action. Memory client623/container wiring remains outside this delta; helper presence/graph compile is not full Memory acceptance.

`git diff --check` PASS; dependency/package/resource/lock preservation is recorded in scope-proof.json. This pin compile does NOT approve the previously held host. Main should route host33829de with Authab37 to its original dual acceptance, and the separate Package03063cd with producerd0/API573 to integration checking. No remote push/PR/merge/deployment performed.
