# Memory c5 package pin — 2026-10-23

Verified start: branch cj/011-memory-client, clean at
`4eac4ee563eafd44c26438902077839bcc558989`; no reset or worktree replacement.
Shared prep imports are separate, unchanged owner commits:
- `3090777b4e10a6135823e3342e5e8b6c34aa9e6b` → local `927b1a3ce281295c1d983cbc11475d60a4cc595b`.
- `f4c17b59213828543cef042d127c56d8467963d8` → local `c6733527502b4c15feb1348271a412e05b0ed5e7`.
The 12 resulting shared files equal fixed f4 bytes. No later 5d/9d input consumed.
Review the Memory product diff from c673352; prep is excluded from this delta.

Only product hunk changes the existing sibling CJMessageClient CJFoundation path
from `.generated/c02cf08e52a0d8ffc2fefac99226654a7e01539c` to
`.generated/c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a` in Package.swift.
This candidate supersedes earlier pin documents' paths; no second SDK is copied.

Author checks:
- PASS: fixed exporter output equals all 16 official c5 files. All five previous
  exports remain exact and preserved. [Hashes/provenance](api-c5-provenance.json).
- PASS: independent c02→c5 comparison preserves old 22 paths / 81 schemas;
  manifest, SDK lock and MemoryClientConfiguration.swift byte-identical.
- PASS: resolved Memory/Message graph has two references to one canonical c5
  CJFoundation path. Whole preview/Trip/CJShell App graph remains CJ006's check.
- PASS: 9 existing affected test methods: generated groups/list/detail/receipt,
  whole/fractional dates, invalid non-null fallback, opaque exact bytes/row IDs,
  explicit auth failure, and default Memory live-write refusal before credentials
  or storage. [Output](api-c5-tests.txt). Prior business gates reused; no full suite.
- PASS: unsigned generic iOS Simulator SDK module compile ([result](api-c5-ios.txt)).
  Full local logs `/tmp/cj011-api-c5-tests.log`, `/tmp/cj011-api-c5-ios.log` retained.
- PASS: Memory Sources, Tests and Package.resolved byte-identical to 4eac4ee;
  whitespace/scope checks pass.

Pure pin compatibility does not release business HOLDs or prove preview/App/real
service acceptance. Memory default POST remains closed. No actual business
network, Keychain, old database, deployment, signing/permission change, push/merge
or Issue closure. Original independent gates and CJ006 unified graph follow separately.
