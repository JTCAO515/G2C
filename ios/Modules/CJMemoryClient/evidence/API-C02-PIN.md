# Memory shared CJAPI c02 pin candidate

Product baseline: `d7f57ec549312f6cfc9951ddda4dce3d759baeda` (verified clean).
Shared input `540da02a335e96e98917ffd3d94a395f8ca2d892` was imported separately as
`2ee77299cbe84c4b1b83cac4501e7f3766b9e7d0`; all eight imported files were checked
byte-identical to the original owner commit. Review this Memory delta from 2ee7729.
Those prerequisite changes belong to CJ009, not this product delta.

Only product hunk: Package.swift's existing sibling CJMessageClient path changes
from `.generated/201156c9bf9850f9b8e87dc1f986452ce1ae789f/CJFoundation` to
`.generated/c02cf08e52a0d8ffc2fefac99226654a7e01539c/CJFoundation`.
Official SDK identity remains c02; the later evidence-only candidate does not
replace it. Prior pin documents remain historical; no second SDK was created.

## Author verification

- PASS: official exporter used fixed CJ005 Git objects in this isolated clone.
  All 16 files in each 573/9dc/d688/201156/c02 cache equal their respective fixed
  commits. Previous caches preserved. [Provenance](api-c02-provenance.json)
  records current file hashes and verified prior-export hash-manifest digests.
- PASS: independent 201156→c02 comparison: old **21 paths / 79 schemas** unchanged.
  SDK Package.swift/Package.resolved and MemoryClientConfiguration.swift byte-equal.
- PASS: resolved dependency graph has two Memory/Message references to one
  canonical c02 CJFoundation path. This does not certify the CJShell/RUN App graph.
- PASS: **8 affected test methods**, actual generated reads and receipt codec,
  whole/fractional dates, malformed non-null fallback, expired-auth failure,
  opaque exact-byte detail/list and NFC/NFD row identity ([tests](api-c02-tests.txt)).
- PASS: unsigned generic iOS Simulator SDK package build with existing resolved
  versions required ([build](api-c02-ios.txt)). Full local logs retained at
  `/tmp/cj011-api-c02-tests.log` and `/tmp/cj011-api-c02-ios.log`.
- PASS: Memory Sources, Tests and Package.resolved byte-identical to d7f57ec;
  whitespace/scope checks pass. Existing 884/business/repair evidence is reused;
  no unrelated full test suite, PG or real service was run.

Pure pin PASS does not release any business HOLD or independent gate, grant live
POST, or establish App/model/Keychain acceptance. Default POST and all prior
repair boundaries remain intact. No other consumer/root source edit, actual
business request, signing change, push, merge or Issue closure. Original
Main/Review/Testing/Publish and CJ006 full graph consumption proceed separately.
