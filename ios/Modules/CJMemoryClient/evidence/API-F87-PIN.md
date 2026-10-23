# Memory f87 dependency candidate — 2026-10-23

Verified clean start: cj/011-memory-client at
`3b4ef16a3bf1e52428b35704131bce9af87a7592`.
Shared source inspected read-only at `5075bcf604e959d5c4592071a1e9de39d8687395`;
official root SDK `f87a78a9d8984c59905e385483f17dddd8144d8a`.
This instruction permits only the Memory module and fixed ignored export output;
no sibling/shared tracked files or commits were imported/changed in this step.

Product hunk: the existing Package.swift CJFoundation path changes
`.generated/33cec5ba71d74820cb0acd3c89ecbe39ba125590` →
`.generated/f87a78a9d8984c59905e385483f17dddd8144d8a` under sibling CJMessageClient.
The official 16-file export was prepared there as ignored fixed dependency data,
with conflict checks before writes and exact post-export SHA checks. No second SDK
identity or new business/prepare abstraction was introduced. Previous exports and
failure evidence are retained.

## Author checks and precise remaining graph gap

- PASS: all 16 exported files match fixed official Git bytes, before and after the
  isolated SDK build. Old 25 paths / 90 schemas compare equal. SDK manifest/lock
  and MemoryClientConfiguration.swift remain byte-identical to 33. Actual shared
  Transport.swift equals fixed 5075. [Hashes](api-f87-provenance.json).
- PASS: this Memory manifest parses and contains the exact f87 path.
- PASS: official f87 CJAPI target compiles in a separate scratch directory within
  this module; five existing Memory operation call signatures and `.memory`
  configuration typecheck against that compiled SDK. No operation was executed.
  [Commands, result and checked calls](api-f87-checks.txt).
- PASS: Memory Sources, Tests and Package.resolved, plus the entire tracked
  sibling CJMessageClient subtree, equal the starting fixed bytes; diff whitespace
  and scope verified. Prior valid business/runtime-codec evidence is reused.
- UNRUN: full Memory consumer compile, affected runtime tests, iOS consumer compile
  and actual single-f87 consumer graph. The current sibling
  `ios/Modules/CJMessageClient/Package.swift` still points to **33** (original shared
  fixed `6936a632ecc5cdbfd615b80c75312a09ed64b23a`, local prep `9a19181`). It would
  conflict with this module's f87 dependency. No knowingly conflicting build was
  attempted and no temporary replacement manifest was used to claim graph PASS.

Required next dependency: Main/original shared owner must make the exact
**5075bcf** shared preparation available in this clone/composition, including its
Package f87 alignment, or grant its unchanged prerequisite import separately.
This task does not modify that owner's tracked manifest. No Trip dependency exists
in the Memory manifest. Whole Cleanup/CJShell unified graph remains a host gate.

This is a partial compatibility candidate, not full pin/graph PASS or activation.
New wire independent gate remains pending. POST, factory, permissions and original
business HOLDs remain unchanged. No full suite/PG/device/Keychain, actual business
request, cache/data operation, deployment, push/merge/Issue closure or message to
another thread. No new product feature or complete I acceptance is claimed.
