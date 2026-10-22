# CJ-008 author results

PASS — local author evidence only; independent Review/Testing pending.

- `tests-final.txt`: 12 Swift Testing functions, **44 expanded cases**, PASS.
  Generated actual Client + canonical real SessionLifecycle with in-memory persistence;
  canonical NoRedirectTransport default GET intercepted in-process (no socket).
  Exact original escaped/decomposed Unicode bytes, operation/run association,
  decimal strings beyond Int64, null versus actual zero, four statuses, cancelled
  and exceeded meaning, sixteen invalid-wire variants, eight HTTP/JSON/error variants,
  no configuration/credential, one-shot/multi-owner preparation, actor/session/selection
  ABA, equal-revision prepare reentry, final callback reentry, and body await followed
  by a newer result with/without old Task cancellation.
  Body test waits until the actual HTTPBody iterator has started, not just send return.
- `ios-compile.txt`: unsigned compile of CJUsageClient for
  `arm64-apple-ios17.0-simulator`, PASS; no simulator launch or App integration.
  Sources unchanged since this compile; final additions affected only tests/docs.
- `scope-checks.txt`: exact shared prep, unchanged base AUTH tree, canonical8b runtime
  inputs, eleven existing lock entries and seven SDK export hashes PASS.
- Initial staged whitespace check flagged original compiler output whitespace.
  Archived that exact log losslessly as gzip (SHA256 of decompressed original: 5ce4ea7c2c65be2263f6782ef3d4aa3eab81a81b61db9d1a2b48e9dd43ed7660).
  Final staged `git diff --check` before fixed commit PASS.

Preserved non-PASS evidence:

- `first-build.txt`: FAIL stale copied shared lock lacked AUTH transitive pins.
  Fixed only this module's new lock using accepted shared+AUTH union, no upgrades.
- `second-build.txt`: module compile PASS; test runner FAIL no tests yet created.
- `tests-1.txt.gz`: FAIL compiler diagnostic for lazy test fixture initializer.
  Fixed test fixture with a method initializer; no product workaround.
- `tests-2.txt`: earlier 8-function / 39-expanded-case PASS.
- `tests-3.txt`: FAIL test fixture throwing nil-coalescing expression, fixed locally.
- `tests-4.txt`: 12-function / 43-expanded-case PASS before body-iterator gate refinement.
- `scope-check-first.txt`: initial whole AUTH subtree-to8b assertion FAIL; diagnosed
  pre-existing documentation/evidence-only difference. Runtime input comparison PASS;
  no AUTH edits made. The earlier eleven-pin lock comparison itself passed.

UNRUN: independent review/testing, remote CI, account/keychain/old cache, actual
network/API service/SQL/provider/billing, App/CJShell integration, rendered UI,
accessibility/device validation and complete Issue9 I acceptance. No push, PR,
merge, deployment or issue closure. Requested model gpt-6.1-sol medium / Standard;
effective model/tier UNKNOWN.
