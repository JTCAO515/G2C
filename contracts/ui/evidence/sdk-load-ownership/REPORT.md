# CJ006 displaced SDK load: reproduced, exact ownership input needed

2026-10-22. Product source remains e18fdd7221040895a9172c337798034aa02e2f80. No AccountHost/CJSession/Package/lock/brand change in this diagnostic delta.

Read Testing's CJ-006-sdk-session-host/REPORT.md and located its exact test at snapshot/ios/Modules/CJShell/Tests/CJShellTests/IndependentSDKHostLoadTests.swift (the report-root filename was absent). Copied that test unchanged into owned related Tests and ran only IndependentSDKHostLoadTests. Both parameter cases old-return/old-throw FAIL; same-original storageUnavailable control PASS. B bytes, lifecycle.saved and B original operation remain healthy. Actual log before.txt; original32 positive evidence reused, not rerun.

## Public API insufficiency

Current accepted SessionLifecycle public isCurrent(operation) is `!blocked && ownsOperation(operation)`. It returns false both for:

1. the SAME original operation whose actual storage error just blocked it; and
2. an old operation replaced by another operation.

The exact ownsOperation predicate already exists, but is package-private to CJAuth; CJShell cannot call it. Public state is the CURRENT lifecycle state, not a tagged original-operation result. Checking state.saved can identify this healthy-B example, and capturing verifier generation/ID can reject the reported identity change, but neither proves original lifecycle ownership in the general same-identity replacement case. A replacement operation can itself be blocked with the same error while the old operation also has isCurrent=false. Error-name filtering or a copy of private SessionOperation fields is not an acceptable ownership check.

## Smallest required producer input

Main can route CJ007 to expose a read-only public predicate with existing `ownsOperation(_:)` semantics (name chosen by owner): same lifecycle instance/generation/original operation, remaining true when that SAME operation is blocked. No permission grant: public isCurrent remains the precondition for usable operations, and blocked ownership must not allow IO. No credentials/current-operation token need to be exposed, no wire/storage change or new wrapper.

After a fixed public input is available, the minimal host catch can first verify original UI/private request ownership, then canonical operation ownership. Displaced A should retire only its own waiting bookkeeping and withhold its error projection; it must not adopt/clear B, block B, or invent an authorization result. Same-original failures must still surface blocked. Capture/recheck trusted verifier generation/ID around synchronous load as an additional identity fence, not as a replacement for canonical lifecycle ownership.

## Current status

HOLD; no product repair or green claim yet. No private CJSession access, reflection/shadow identity, new framework, API guess, Keychain/network or device run. Regression-only commit is NOT a publishable repaired candidate. Package and lock remain unchanged, with no in-flight build; original write ownership remains for the eventual narrow repair and Main's separately specified pin step.
