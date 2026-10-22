# Memory 33 package pin — 2026-10-23

Start verified clean on cj/011-memory-client at
`9de12d2d1d09ac7477a49cb27b1073792e1bcc4e`. Prior failure records are retained.
Shared input `6936a632ecc5cdbfd615b80c75312a09ed64b23a` is imported unchanged as
separate prep `9a19181a5ffb0f977bb1ed6c4ceb47c128662d97`; its eight files match the
original owner bytes. Review the product delta from 9a19181, excluding shared prep.

Only product hunk: Package.swift's sibling CJMessageClient/CJFoundation path
changes `.generated/9d0f4b4c1e89b28d01de18092b5bf695de5bcde7` →
`.generated/33cec5ba71d74820cb0acd3c89ecbe39ba125590`.
No new SDK copy or business/Tests/lock change.

Author checks:
- PASS: all 16 official 33 export files match fixed CJ005 Git objects. Seven
  earlier exports remain exact/preserved. [Provenance](api-33-provenance.json).
- PASS: independent 9d→33 comparison preserves old 24 paths / 88 schemas;
  SDK manifest/lock and MemoryClientConfiguration.swift unchanged. Shared
  Transport.swift remains byte-identical to accepted e450/94 behavior.
- PASS: actual resolved Memory/Message package graph has two references to one
  canonical 33 CJFoundation path, with no CJTripClient dependency. No missing
  Trip owner head is inferred or consumed; whole host graph remains CJ006's gate.
- PASS: 4 existing affected test methods, including whole/fractional date cases,
  generated groups/list/detail codecs, opaque IDs and rejection of invalid
  non-null receipt fallback ([output](api-33-tests.txt)). Other unchanged business
  gates, including row identity and default write refusal, are reused.
- PASS: unsigned generic iOS Simulator SDK module compile ([result](api-33-ios.txt)).
  Full local logs `/tmp/cj011-api-33-tests.log` and `/tmp/cj011-api-33-ios.log` retained.
- PASS: Sources, Tests and Package.resolved byte-identical to 9de12d2; own diff
  whitespace/scope verified. No unrelated full suite or real-service/cache test.

Module factories/permissions/real-source boundaries and default POST remain
unchanged. Pure pin compatibility releases no business HOLD and does not establish
association/attempt availability, whole App or full I acceptance. No actual
business network, Keychain, old database/cache, deployment or signing operation;
no other module/main edit, push or merge. Original independent gates and CJ006
unified graph consumption follow separately.
