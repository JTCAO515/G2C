# CJ022 20aa consumer dependency candidate

Base `2772d896db33344126eae2d025cd7d378dff1c8e`, clean before this task. Product manifest changes exactly one SDK path f87→20aa50ed5c8449e6026155a6151f22041dee7fd4. Business Sources, Tests and Package.resolved are byte-identical to base. The prior fixed f87 commit, its ignored mirror, all valid behavior evidence and older FAIL logs remain intact. Only CJOfflineTrip paths change; canonical sibling/shared/Trip paths are not written.

## Fixed local graph

`scripts/prepare_20aa_validation.py` creates a new ignored mirror under this module's `.build`, refusing to replace any existing mirror. It reads only exact Git objects:

- shared CJ009 `cc9e2c3ba1fb8fe7582e5e4664a924b1c6b93f71`, never its moving checkout HEAD;
- Trip CJ015 `b3485ef02bbe4cc9bfcebfc1f9c61a1a67670ce5`, whose source behavior is the prior a5cc line;
- AUTH `4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e`;
- official SDK `20aa50ed5c8449e6026155a6151f22041dee7fd4`, all16 inputs including its original lock verified against the shared fixed manifest;
- unchanged CJ022 business Sources/Tests/lock from this task's base plus the one-line product manifest change.

`inputs.json` lists owner/head/hash for every mirrored file. The 20aa preparation succeeded on its first run by reading AUTH4eac from the fixed AUTH owner repository. It created a fresh `20aa-validation-cc9e2c3-b3485ef` mirror and left all earlier f87 mirrors intact. No second tracked SDK, wire schema, provider or business abstraction is created.

## Executed checks

All Swift commands ran under outer sandbox-exec `(version 1) (allow default) (deny network*)`, using only preexisting local package cache with forced resolved versions. SwiftPM's inner sandbox was disabled under that outer network restriction.

- PASS actual CJ022 graph (`closure.json`): four references to exactly one CJFoundation path, all20aa; no mixed f87/33/9d SDK dependency in this mirror.
- PASS public-only consumer typecheck against newly built mirror modules (`PublicConsumer.swift`, measured exit0 in `checks.json`; output in public-compile.log).
- PASS two minimal codec functions (`tests.log`): exact original bytes/nonce and invalid draft/null/duplicate/mismatched-original rejection. These are in-memory synthetic fixtures; they perform no App cache write or real source call. Prior unchanged file/clock/accepted-source/reentry behavior evidence is reused.
- PASS all mirrored inputs rehashed after validation, including original locks; TripRecord, TripDetailResponse, TripDocument, TripDocumentItem and getTrip path schema equality f87→20aa; CJ022 Sources/Tests/lock unchanged (`checks.json`). Frozen AAD/source identity remains its prior business-format version.
- PASS macOS package/test-target compile and git diff --check. 20aa iOS target build and complete fca5 App dependency graph/build/runtime remain UNRUN.

This is necessary product dependency preparation for the newer fca5 host input. It does not certify that host's full graph. Factory, offline permission, production TTL/trusted clock, real source/cache root, Keychain, CLEANUP/device and I acceptance remain closed or UNRUN. Candidate requires independent Review/Testing and Main/Publish integration. No push, PR, merge, main update or deployment.
