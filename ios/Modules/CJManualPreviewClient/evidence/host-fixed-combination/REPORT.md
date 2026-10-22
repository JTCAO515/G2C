# CJ-017 db48855 + shared94 fixed combination

Consumer source: `db4885593825f726c6eeefe459e53529708b6d7d`.
Shared fixed: `94c50ab6650e9defb0f7df6d7ccbb2bff250c947`, exact parent f4c17b5,
from original owner's independent `cj-009-preview-host-fix` worktree.
Separate raw import prep: `4c4d15a` (full identifier in inputs.json).
CJFoundation remains the same single c5 identity/path; Package and lock unchanged.
No5d/9d SDK upgrade or moving-source copy was consumed. Original trees not changed.

**No consumer runtime source change needed.** `git diff --exit-code db48855 HEAD --
CJManualPreviewClient/Sources CJManualPreviewClient/Package.swift
CJManualPreviewClient/Package.resolved` PASS. Shared module contents compared directly
against94c50ab with `git diff --exit-code`: PASS. Paths above are under ios/Modules.
Only original-owner dependency bytes are in prep; subsequent delta is local module
README/evidence. Original036/79/db and old f4 failure/HOLD artifacts remain unchanged.

## Actual narrow verification

Command:

```
cp ios/Modules/CJManualPreviewClient/evidence/host-fixed-combination/HostConsumerCombinationTests.swift ios/Modules/CJManualPreviewClient/Tests/CJManualPreviewClientTests/HostConsumerCombinationTests.swift
swift test --disable-sandbox --package-path ios/Modules/CJManualPreviewClient --scratch-path /tmp/cj017-manual-preview-build --filter 'HostConsumerCombinationTests|IndependentPreparationTests|PreparationOwnershipTests|exactOptInRunsOfficialClientAndPreservesFrozenNFDRequest|existingLiveTransportGateIsVisibleAndRetainsDraft'
```

**PASS: seven functions / five suites**, including six parameterized Host cases
and two prepare-callback positions. Full output in `combination-tests.txt`.
After verifying byte identity, the temporary target copy was removed; the executed
probe is retained in this evidence directory with its SHA256 for exact replay.

- Official generated preview through consumer + actual shared capability succeeds;
  exact frozen outgoing bytes/NFD/base content/version, three original-work validators
  and can_save=false are checked by the existing exactOptIn test.
- The new evidence probe uses that same real editor/factory/official generated request,
  injecting ordinary Host metadata immediately before the actual shared transport.
  All six variants (foreign, same origin, casing, explicit port, empty, duplicate mixed
  or matching values) reject before shared validation or underlying send: zero
  shared checks, zero wire calls; visible unavailable, no result, original draft kept.
  This is an input fault injector only, not a runtime metadata rewrite or fallback.
- Existing generic default transport still refuses preview POST and preserves draft.
- Exact independent preparation reentry repro and affected preparation owner controls
  pass: nested newer work survives both original source callbacks; outer throws
  retired, newer runs once without requiring the older caller, old perform cannot
  clear newer success, callback cancellation/edit remain retired.

No unrelated24-function full suite, backend/Trip/Auth suite or iOS build was rerun.
Swift test compiled the actual shared94 and consumerdb module graph for these checks.
Prior narrow consumer19 controls/shared owner11 evidence are attributed separately;
this report is author combined-consumption evidence, not independent shared review.

No URLSession/DNS/socket/external request, live account/credential, Keychain, provider,
SQL, service startup, signing/install, save/confirmation or deployment occurred.
Actual network/App factory/rendered UI/physical device/full Issue22 I remain UNRUN.
Shared and consumer independent Review/Testing results remain separate gates; this
report does not self-close either old HOLD. No push/PR/merge was performed.

`inputs.json` fixes exact inputs/prep; `sha256.json` records current runtime/manifest/
lock, probe and output. Host usage remains the explicit positive-finite-timeout
constructor documented in README, with its real original source/session/work guard.
