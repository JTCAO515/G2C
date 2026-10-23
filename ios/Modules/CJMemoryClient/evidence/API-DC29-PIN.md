# Formal Memory dc29 consumer pin — 2026-10-23

Start verified clean on cj/011-memory-client at
`ea85fe080e926b7c569883588486b8795a18d4ab`.
Only product hunk changes the real Package.swift dependency from
`.generated/20aa50ed5c8449e6026155a6151f22041dee7fd4/CJFoundation` to
`.generated/dc29bb3634e63d8f065c38d39a7a0059f76cfa53/CJFoundation`, under the same
sibling CJMessageClient. This is the formal consumer manifest, not a test-only
substitution. Source/Tests/own lock and all peer/shared tracked files are unchanged.
Existing management/f87 candidates and all prior FAIL artifacts remain preserved.

## Fixed inputs and author checks

Shared source: `9b4852dfad418d124d60366ada8efb380a8ffc1d` (read-only).
Official root: `dc29bb3634e63d8f065c38d39a7a0059f76cfa53`.
All 16 official SDK build files were exported byte-exact in the existing ignored
cache, rejecting differing output. Previous 20aa export preserved. All six existing
Memory paths and 14 Memory-prefixed schemas compare equal to 20aa, including item/
source versions, lifecycle action/receipt fields and null unions. SDK manifest,
lock and MemoryClientConfiguration.swift byte-identical.
[Input hashes and comparisons](api-dc29-input.json).

The private graph `.build/dc29-consumer-1c8f36ed` assembles the formal candidate
module, exact shared9b4852d, canonical AUTH b24cc77, and the single official dc29
export, using their normal relative paths. No manifest rewrite/typealias or second
SDK identity. Original sibling tracked33 was not edited or used in this graph.
[Every input SHA and actual graph](api-dc29-consumer.json).

- PASS: actual CJMemoryClient public API/module and existing tests compile on the
  fixed graph; existing public NoRedirectTransport constructor remains compatible.
- PASS: six selected methods from MemoryClientTests.swift,
  IndependentContractAndStoreTests.swift and MemoryManagementTests.swift. Covers
  whole/fractional dates, malformed non-null fallback, opaque IDs, pause/resume
  historical receipt reconciliation, and public management/save refusal before
  credential or journal access. [Output](api-dc29-tests.txt).
- PASS: resolved graph has two references to one canonical dc29 CJFoundation path.
- PASS: unsigned generic iOS Simulator SDK consumer compile ([build](api-dc29-ios.txt)).
- PASS: all copied source/manifest/lock hashes preserved after compilation/tests;
  own diff scope/whitespace checked. Full logs `/tmp/cj011-dc29-tests.log` and
  `/tmp/cj011-dc29-ios.log` retained. Prior unchanged 41-method business evidence
  reused; no full suite or PG rerun and no test source edits.

The public production management/save closure and UI confirmation boundaries are
unchanged. No new factory activation, real business network/credential/Keychain/
provider/device operation, peer/Shell/backend edit, push/merge or Issue closure.
This author consumer candidate requires original independent Review/Testing.
Whole FEAS/CJShell App graph and real-service/I acceptance remain UNRUN here;
shared export PASS and this pin result do not release any business HOLD.
