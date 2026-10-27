# RUN c02cf08 SDK pin — compatibility only

Starting consumer head: `d5769223e6edb87a547403c4eaac5860d484a662`.
Separate original-owner dependency preparation:
`3b6d6d88470ac6d17d0e6913789a99d5288cb0ce` (parent d576922).
Product pin commit's parent is that preparation; head is the commit containing
this report. Product diff: one Package.swift path replacement plus this evidence
folder. Business Sources, Tests, Package.resolved and POST gates are unchanged.

Fixed shared owner: `540da02a335e96e98917ffd3d94a395f8ca2d892`
from cj-009-memory-api-pin. Official API identity stays
`c02cf08e52a0d8ffc2fefac99226654a7e01539c`; the later a5f evidence-only input
was not substituted as SDK identity. Sole dependency path:

`../CJMessageClient/.generated/c02cf08e52a0d8ffc2fefac99226654a7e01539c/CJFoundation`

Preparation imports the owner's exact shared Package.swift/prepare_generated.py
and generated-pin manifest. All16 exported files equal fixed official API git
objects. This is dependency preparation, not a new shared-module implementation;
Publish must consume the accepted original-owner dependency through its own lane.
No root generation/source, other consumer or CJShell was edited.

## Actual checks

- PASS: old20115621 OpenAPI paths and79 schemas remain equal; all79 old generated
  schema declarations and69 SDK blocks (23 old operations across Client,
  Operations and convenience methods) remain exact. `provenance.json`.
- PASS: API Package.swift/Package.resolved and official Memory date helper are
  byte-identical; prior date runtime evidence from `../201156-api-pin/` is reused.
  No date-parser or lock change, no new date probe needed.
- PASS:8 existing affected codec tests/2 suites with the new generated Client:
  proposal states, formal record/list/detail versus historical receipt, keyset
  cursors and null/fallback rejection, accept/reject version constraints, exact
  original Action bytes. Tests unchanged; `codec-tests.txt` preserves results.
- PASS: package graph has one CJFoundation identity/path, c02cf08, for both consumer
  edges. Unsigned generic iOS Simulator compilation passes with locked versions
  and automatic package resolution disabled; no launch/signing (`ios-build.txt`).
- PASS: all48 prior exported files (201156, d688,9dc) retain their exact hashes.
  The573 export was already absent in this clone; none was deleted/changed.
- PASS: every business source/test and the consumer lock matches d576922 bytes;
  new Package.swift hash and old export hashes are recorded in `provenance.json`.

Only the same eight codec methods used for201156 were run, not the whole34-test
business suite. Earlier business/P2 repair evidence is retained and reused.
Compiler logs contain the existing SwiftPM --skip-update deprecation and generated
unused-public-import warnings; excerpts retain deduplicated warnings and full-log
hashes. Generated source was not altered to suppress warnings.

Provenance reproduction (read-only):

```sh
swift package --package-path ios/Modules/CJTripClient \
  --scratch-path /tmp/cj015-trip-client-build --skip-update --force-resolved-versions \
  show-dependencies --format json > /tmp/cj015-run-package-graph.json
# After the command completes:
python3 ios/Modules/CJTripClient/evidence/c02cf08-api-pin/check_pin.py \
  <local>/Documents/Codex/2026-10-21/cj-005-foundation \
  /tmp/cj015-run-package-graph.json
```

Independent pin Review/Testing remains PENDING; existing business HOLD/repair
status is unchanged. Pure pin PASS is not business acceptance. Public POST remains
closed. No PG, real Keychain, product HTTP, real account/confirmation/provider,
rendered UI/device, CI, deployment, push/PR/merge or Issue closure. CJ006 owns the
final App package graph and integration; this task does not perform that wiring.
