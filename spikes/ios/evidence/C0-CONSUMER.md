# C0 consumer confirmation — CJ-004

- Source commit: `db9c040f262032acaf5375db43d7169b3217e504` in CJ-005; formal path `contracts/api/openapi.json`. Read with `git show`, never from its moving worktree.
- Evidence: `c0-source.json` records SHA-256; `c0-generate.log` and `c0-tests.log` retain generation/test output.
- Generator 1.14.2 + Runtime 1.13.3: **PASS**, regenerated client compiles under Xcode 27.1 / Swift 6.4 on macOS arm64. Four independent consumer tests PASS: generated normal result, unknown maps to structured default failure with reconcile_original, conflict remains failed, missing mandatory X-Request-ID fails visibly.
- Consumer confirms **BASE@1.0 probe/error/request-id shape only**. Mock/in-memory transport, not live HTTP, Auth, RUN or SSE acceptance. No claim about CJ-005's other checks, independent review, CI or merge.
- Formal schema and fixtures are extracted to ignored `.cache/c0-consumer`; no tracked duplicate source. `scripts/prepare-c0.py <CJ-005-repo>` recreates that snapshot then use `swift test --package-path .cache/c0-consumer --cache-path .cache/spm --jobs 4` from `spikes/ios`.
- The disposable `/probe` and SSE schema in `Sources/SpikeClient` is not adopted as product API. JSON probe cases now have C0 consumer coverage. Keep its SSE-only investigation isolated until RUN/SSE owner publishes its contract, then remove that temporary schema and point product generation to the formal source. C0 does not freeze RUN/SSE.

Final delta: C0 has 5 tests, with the invalid-body test running 3 cases (missing required fields, malformed JSON, unknown status enum). All PASS in `c0-tests-final.log`. Temporary JSON endpoints/models have been removed from `Sources/SpikeClient/openapi.yaml`; it is SSE-only. Final SSE tests: 5 PASS in `tests-sse-final.log`.
