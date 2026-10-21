# CJ009 Swift client recovery core

Parent 9e2a7e3cfe89cccabb691c5febe9e74938c6b1ee; only new CJMessageClient package.
Swift6.4 Apple toolchain, arm64 macOS27 host; package deployment baseline macOS14/iOS17.
Platform CryptoKit, no external packages. No real account/keychain/transport/provider calls.

PASS: 9 Swift Testing checks, tests.txt. Includes encrypted original bytes/draft reload,
query-only unknown/null, same bytes cannot use replacement ID, late instance/generation/
account/environment callbacks, latest-operation receipt digest/ID matching, missing/wrong
key/corruption failure, ambiguous atomic write readback, Unicode byte-exact IDs, and
ciphertext scope swapping rejection. XCTest displays 0 because tests use Swift Testing;
the actual Swift Testing result is 9, not 0. Tests create only uniquely named synthetic
temporary directories and random in-memory keys; no real credential files read.

PASS: independent writer/reader process invocations of test-only CJMessageRecoveryProbe,
process-write.txt and process-read.txt. `.build/process-fixture-01` contains encrypted
synthetic records and a random test-only 0600 key generated externally for the two runs.
Separate process reopen preserves original ID/bytes/draft and null remains query-only.
This happened before an additive stage same-body/re-key rejection and extra old-instance
assertion; storage/process paths unchanged and final nine-test run covers those additions.
Evidence is reused, not relabelled as a later repeated process test.

Build progression: initial sandbox cache denial retained in initial-build-environment.txt;
redirecting caches reached sandbox manifest restriction. Normal tool approval permitted
same scoped tests. One test #require macro needed an inner `try`; fixed without changing
behavior assertions. Final build/tests PASS. No shared configuration or PG rerun.

Command (repository root):

```sh
CLANG_MODULE_CACHE_PATH="$PWD/ios/Modules/CJMessageClient/.build/clang-cache" swift test --package-path ios/Modules/CJMessageClient --cache-path "$PWD/ios/Modules/CJMessageClient/.build/cache" --config-path "$PWD/ios/Modules/CJMessageClient/.build/config" --security-path "$PWD/ios/Modules/CJMessageClient/.build/security"
```

Process run used same Swift options and `swift run CJMessageRecoveryProbe write|read`
with the explicit synthetic store path and synthetic key path under .build; no key bytes
were printed or committed. Never use the test key-file provider in product code.

Fixed CJSession ef2c7da4 read for semantic consumption only; AUTH-CONSUMPTION.md records
host mapping/key/clear-failure gaps, no copied AUTH interface or speculative dependency.
No second wire schema: ID/raw binding to generated request and real receipt decoding await
CJ005 fixed generated consumer. Swift storage serialization is a local encrypted snapshot.

UNRUN: real auth/Keychain integration, iOS compilation/device/file protection, UI integration,
HTTP transport/service, crash/power-loss/fsync durability, backup rollback defense, real
cleanup/retention, independent Review/Testing. Module is single-writer only. No push/merge.
