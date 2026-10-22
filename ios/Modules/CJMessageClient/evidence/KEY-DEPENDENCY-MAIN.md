# Formal CJAuth key dependency — main graph repair

Independent owner checkout cj-009-key-dependency, branch cj/009-key-dependency.
Fixed merged-main input 3c52f72daf1d8e2304c0c569b47e68d92a4b323e from Publish's local
Git objects; original cj-009-message remains clean at625b66d and is not modified.
No remote/config/brand/App/entitlement edits or new implementation introduced.

Verified formal CJAuth MessageKeyInterfaces.swift is BYTE IDENTICAL to fixed f1ce075
interface export, SHA256 e67c45d1c22e71c83cb6e897c37f66ad10a4d2b9d08afe53910cc632097005e8.
Thus no interface/source-level ABI change is introduced by this dependency correction;
no independent binary ABI compatibility claim is inferred. Formal CJAuth already exposes
CJMessageKeys. CJShell depends on both CJAuth and CJMessageClient, so the old exported
CJMessageKeysInterface duplicates that target. Real pre-fix graph resolution reproduced
this exact conflicting-target error (key-dependency-before.txt), unrelated to logo assets.

Product diff is exactly two Package.swift lines:
- .package(path: "../CJAuth") replaces the old .generated/CJMessageKeysInterface path.
- CJMessageKeyBridge product package changes from CJMessageKeysInterface to CJAuth.
Formal AUTH source/product, CJShell Package and generated API bytes remain unchanged.
README minimally marks the old key preparation harness historical, not a main dependency.

PASS: actual fixed-main CJShell root graph `swift build` after the two-line correction
(key-dependency-main-build.txt). This compiles the real local Auth/Session/message/API/
Shell graph on macOS with Apple Swift6.4; generated unused-public-import warnings remain
nonfatal and were not edited. It is not an iOS signed App/visual logo/device acceptance.
PASS: CJMessageClient `swift test --filter KeyBindingTests` consumes FORMAL CJAuth product;
4/4 existing tests pass (key-dependency-consumer-tests.txt), synthetic key/provider only,
no actual Keychain or service use. No broader old test suite repeated.

Commands used from this checkout, with R=ios/Modules/CJMessageClient:

```
python3 $R/scripts/prepare_generated.py <fixed-CJ005-git-repository>
# Before-fix reproduction also exported historical key interface, then left it ignored.
CLANG_MODULE_CACHE_PATH=$PWD/$R/.build/clang-cache swift build --package-path ios/Modules/CJShell --scratch-path $PWD/$R/.build/main-graph --cache-path $PWD/$R/.build/cache --config-path $PWD/$R/.build/config --security-path $PWD/$R/.build/security
CLANG_MODULE_CACHE_PATH=$PWD/$R/.build/clang-cache swift test --package-path $R --scratch-path $PWD/$R/.build/client-check --cache-path $PWD/$R/.build/cache --config-path $PWD/$R/.build/config --security-path $PWD/$R/.build/security --filter KeyBindingTests
```

Existing local cache copied into this checkout; missing repository caches fetched by
SwiftPM under normal tool authorization. Exact resolved states all match fixed-main
CJAuth/CJShell locks; no new version selected. Standalone client test temporarily expanded
its local Package.resolved with the formal Auth closure; that auto-generated change was
preserved in ignored .build/key-dependency-raw and restored to the fixed base because this
lease is the two Package lines plus module evidence. Main graph continues to use its
unchanged complete CJShell lock. Exact resolution metadata and raw log hashes are in
key-dependency-provenance.json; raw full logs remain locally in that ignored directory.

Independent Review/Testing pending. No push/PR/merge/deployment, real Auth/provider,
network business call, PG, host Keychain, signing bypass or brand replacement performed.
