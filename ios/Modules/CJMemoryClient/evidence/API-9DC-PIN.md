# Memory shared CJAPI pin candidate

Product baseline: `884a070ab51653776e17f77afb8b3628fd89e994`.
Dependency preparation is a separate unchanged import of CJ009
`4fb05cc1f28382c5a4e97efdd833d5f079997c96`, local commit
`9615c29bc35c150556bd82dc7d26094c112fc8f6`. This prerequisite belongs to CJ009,
not the Memory product delta. Review this follow-up from local 9615c29.

The only product hunk changes CJMemoryClient/Package.swift's existing local
CJFoundation dependency from `.generated/57336d501e5691302a3d5e9770f07666d1c57d4a`
to `.generated/9dc67ced50a0cb7611a84b4adf97ab0b43c88bea`, under the same sibling
CJMessageClient. This supersedes the initial README's historical 573 path only
for this follow-up candidate. API and export gate acceptance remains separate;
this candidate is not activation or full CJShell/Trip graph acceptance.

## Verification

- PASS: fixed CJ009 exporter run only in this isolated clone, using fixed CJ005
  Git objects. Both the retained 573 export and new 9dc export have all 16 files
  byte-identical to their respective official commits. No generated rewrite/copy
  under Memory or a second named SDK exists.
- PASS: independently compared fixed OpenAPI JSON. All prior 10 paths and 24
  schemas equal; ios manifest/lock and MemoryClientConfiguration.swift byte-equal.
  Exact hashes and fixed input identities: [provenance](api-9dc-provenance.json).
- PASS: `swift package show-dependencies --format json` gives two references to
  one canonical CJFoundation path, both 9dc. The Memory and Message consumers
  resolve the same package. Whole CJShell/Trip graph is not claimed here.
- PASS: 8 affected test methods (including both whole/fractional date cases),
  actual generated Client reads, groups/empty list, original receipt query,
  expired-auth failure, malformed non-null fallback, opaque list/detail exactness
  and NFC/NFD row identity. [Output](api-9dc-tests.txt), full local output
  `/tmp/cj011-api-9dc-tests.log`.
- PASS: unsigned generic iOS Simulator SDK module compile
  ([result](api-9dc-ios.txt)), full log `/tmp/cj011-api-9dc-ios.log`.
- PASS: all Memory business source, tests and own Package.resolved are unchanged
  from 884a070. Previous 29 + identity results and original failure evidence are
  retained/reused; no unrelated suite or real-service test rerun.

No new business behavior, live request, Keychain/provider operation, root lock,
CJShell/Auth modification, schema change, network write gate, push or merge.
Production POST remains closed. New wire/shared-export independent gates and
Main/Publish integration remain required; full App/Issue12 gates remain UNRUN.
