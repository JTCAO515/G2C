# Memory 9d package pin — 2026-10-23

Verified clean starting branch cj/011-memory-client at
`ba9ed1a81dc4ac035980b62f7cb95fb48ede07a4`; prior failures/evidence preserved.
Shared owner prep was imported unchanged in separate commits:
- `5d85408c641a50d922cc4bddef7148a449f05381` → local `dd184e7769e4a68d664005d1f94d82bfe8190ca5`.
- `e450e3828577feb211467e63177254f909b06b91` → local `c81c4604172208c20dc1eb734d654804ed1fcdf7`.
All 17 resulting shared files equal fixed e450 bytes. Review the Memory delta
from c81c460; shared prep belongs to CJ009 and is excluded from this product diff.

Only product hunk changes Package.swift's existing sibling CJMessageClient
CJFoundation path from `.generated/c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a`
to `.generated/9d0f4b4c1e89b28d01de18092b5bf695de5bcde7`.
No separate SDK copy, business behavior or other consumer modification.

Author evidence:
- PASS: all 16 official new export files exactly match fixed root 9d Git objects.
  All six earlier exports remain exact and preserved. [Provenance](api-9d-provenance.json).
- PASS: independent c5→9d comparison preserves old 23 paths / 86 schemas;
  SDK manifest/lock and MemoryClientConfiguration.swift byte-identical.
- PASS: actual resolved Memory/Message graph has two references to one canonical
  9d CJFoundation path. No remaining c5-dependent module in this package graph;
  whole USAGE/CJShell App graph is separately CJ006's responsibility.
- PASS: 9 existing affected test methods, including generated reads/receipt codec,
  whole/fractional dates, invalid non-null fallback, auth error, opaque ID/row
  identity and default live-write refusal before storage/credentials.
  [Output](api-9d-tests.txt). Existing accepted business gates reused, no full suite.
- PASS: unsigned generic iOS Simulator SDK compilation ([result](api-9d-ios.txt)).
  Full logs retained `/tmp/cj011-api-9d-tests.log`, `/tmp/cj011-api-9d-ios.log`.
- PASS: business Sources, Tests and Package.resolved byte-identical to ba9ed1a;
  whitespace and exact product scope verified.

Default POST and existing repair/HOLD boundaries remain. Pin compatibility does
not prove a usable attempt/source interface or full I acceptance; no such API
was guessed or introduced. No actual business network, Keychain, provider, PG,
old-data, permission/signature or deployment operation; no main edit/push/PR/merge.
Original Main/Review/Testing gates and unified CJ006 consumption follow separately.
