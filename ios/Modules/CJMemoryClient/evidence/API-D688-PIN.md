# Memory shared CJAPI d688 pin candidate

Product baseline: `ab8cf3eae5c79537ca05c800cad7f559b6187e86`.
Dependency preparation is the unchanged CJ009 commit
`165a0c0137e9baa59c1cf93df7a67d342b6d5b6a`, imported separately as
`83d9683f3458707a52a5a7379820867f9920e770`. Review this product delta from 83d9683;
the prerequisite files belong to CJ009, not this Memory delta.

The only product change is the existing Package.swift path:
`../CJMessageClient/.generated/9dc67ced50a0cb7611a84b4adf97ab0b43c88bea/CJFoundation`
→ `../CJMessageClient/.generated/d688c01dc0fb18488a1e9c49414a039ce0126204/CJFoundation`.
This supersedes earlier 573/9dc path evidence for the new candidate only. No second
SDK, business implementation, test, lock, Auth, CJShell or root-schema edit.

## Author verification

- PASS: CJ009's fixed exporter used fixed CJ005 Git objects in this clone only.
  All 16 files of each retained 573, retained 9dc and new d688 export exactly
  match their official commits. No export rewrite under this module.
- PASS: independently compared 9dc/d688 OpenAPI: old **15 paths / 34 schemas**
  equal. Package.swift, Package.resolved and MemoryClientConfiguration.swift
  byte-identical. [Exact provenance/hashes](api-d688-provenance.json).
- PASS: `swift package show-dependencies --format json` resolves Memory and
  Message's two references to **one canonical d688 CJFoundation path**. This
  verifies this module graph only, not the whole CJShell/NEEDS/Trip App graph.
- PASS: **8 affected test methods** using the actual new generated Client;
  whole/fractional date cases, groups/empty page, original receipt query,
  expired-auth error, invalid non-null fallback, opaque list/detail byte identity
  and NFC/NFD row identity. [Output](api-d688-tests.txt); full local output retained
  at `/tmp/cj011-api-d688-tests.log`.
- PASS: generic iOS Simulator SDK build with signing disabled and existing
  resolved versions required. [Result](api-d688-ios.txt); full local output
  `/tmp/cj011-api-d688-ios.log`.
- PASS: business Sources, Tests and Package.resolved byte-identical to ab8;
  whitespace/scope checks pass. The 884/ad1 29 + identity evidence and ab8 input
  evidence remain preserved/reused. No 29-test full rerun or PG execution.

Live POST remains closed. No live business request, actual account/Keychain,
provider, App launch, push/merge or Issue closure. New shared-input independent
gates and original Review/Testing/Publish remain separate; this is a candidate,
not activation or whole-App acceptance. Original Issue12 integration gates remain.
