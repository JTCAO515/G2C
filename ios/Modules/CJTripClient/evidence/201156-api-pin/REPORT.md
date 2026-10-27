# Feedback201156 shared API pin — compatibility only

Starting consumer head: `5b277cdd72d68467de1208af009fe9f615fcf7d0`.
Separate local fixed-dependency import: `9bf02f504e63e70725d92e98e56759217e7eb7f5`.
Product pin diff base is that import commit; head is the commit containing this
report. Product changes are only CJTripClient/Package.swift and this evidence folder.
Business Sources, Tests, lock and POST gates are byte-identical to5b277cd.

Exact shared owner input: CJ009 `514e0e3a80bd9a3e34248122915d52c86ee46230`
from cj-009-memory-api-pin. Exact API export:
`201156c9bf9850f9b8e87dc1f986452ce1ae789f` from cj-005-foundation.
Package now uses the sole shared path:

`../CJMessageClient/.generated/201156c9bf9850f9b8e87dc1f986452ce1ae789f/CJFoundation`

The preparation imports only owner-authored shared Package.swift, generation
script and generated-pin manifest. All16 exported package files are exact fixed
API git bytes. No generated/root source or other consumer was authored/rewritten.
Do not publish local dependency prep over the shared owner's integrated branch.
The original d688/9dc directories and all their file hashes are unchanged. The573
export was absent in this clone before this task and remains absent: it was neither
removed nor replaced. Historical pin reports remain intact; this report and current
Package.swift specify the new dependency.

## Actual checks

- PASS: old19 OpenAPI paths and73 schemas equal the previous d688 definitions.
- PASS: all73 previous generated schema declarations and63 SDK blocks for21 old
  operations (Client, Operations, convenience methods) remain exact. API manifest,
  lock and MemoryClientConfiguration.swift are byte-identical. `provenance.json`.
- PASS:8 existing targeted codec tests/2 suites run with the new official generated
  Client: proposal states, formal list/detail/historical receipt, C keysets,
  exact cursor/null behavior, illegal nonnull oneOf fallback, accept/reject version
  rules and original Action.raw bytes. `codec-tests.txt`; Tests were not modified.
- PASS: recompiled the already accepted evidence probe
  `../d688-api-pin/DateConfigurationCheck.swift` against the new CJAPI objects.
  Whole/fractional RFC3339, round-trip and invalid-date rejection pass; no parser
  added. Command and output in `date-command.json`, `date-compile.txt`, `date-check.txt`.
- PASS: package graph resolves both consumer edges to one CJFoundation identity and
 201156 path; unsigned generic iOS Simulator build succeeds with locked versions
  and automatic package resolution disabled. No launch/signing. `ios-build.txt`.
- PASS: protected Sources/Tests/Package.resolved match5b277cd byte-for-byte;
  old exports unchanged and new manifest hash recorded in `provenance.json`.

The same8 codec test filter from the d688 report was reused. No full34-test rerun,
PG, real Keychain or product HTTP. Original34-test and two-P2 repair evidence stays
separate and is reused; this pin does not reopen or release any business gate.

One evidence-script attempt read the package-graph file before its producing
SwiftPM command finished and failed JSON parsing. After waiting for successful
completion, the exact check passed; that setup error was not a product failure
or compatibility result. The schema checker now includes generated `@frozen`
enum declarations, covering all73 rather than only62 non-frozen declarations.
SwiftPM's deprecated --skip-update and generated unused-public-import warnings
remain visible in logs; generated source was not altered to suppress them.

Provenance command (read-only):

```sh
swift package --package-path ios/Modules/CJTripClient \
  --scratch-path /tmp/cj015-trip-client-build --skip-update --force-resolved-versions \
  show-dependencies --format json > /tmp/cj015-feedback-package-graph.json
# Wait for the preceding command to finish before reading its output.
python3 ios/Modules/CJTripClient/evidence/201156-api-pin/check_pin.py \
  <local>/Documents/Codex/2026-10-21/cj-005-foundation \
  /tmp/cj015-feedback-package-graph.json
```

Independent pin Review/Testing: PENDING. Any business HOLD remains unchanged;
pin PASS is not release authorization. Public POST remains disabled. CJShell/
Feedback integration, real account/confirmation issuer, provider, rendered UI,
physical device, CI, deployment, push/PR/merge and Issue closure were not performed.
