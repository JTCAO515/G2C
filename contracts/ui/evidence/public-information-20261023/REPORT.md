# CJ006 launch placeholders, contact/help/privacy drafts and unavailable map

Base ebb70ca5e7ed09568b4636268ca6af4134f40a07. Scope: original Shell UI files, one small shared information view file, own tests and evidence. No peer, SDK, dependency lock, package, fixed graph script, root/Auth or other host source change. No second writer or rejected/deferred work resumed.

## Current JT decisions consumed

- Launch is free. Latest explicit currency/period supersedes the earlier unknown fields: future plan labels are exactly **US$19.99/month** and **US$39.99/month** in both languages. These are future subscription display placeholders, not a paid-service delivery or entitlement grant.
- Support: **support@go2china.space**. Contact: **jtcao@go2china.space**. No support hours/SLA or responsible legal entity inferred.
- No existing approved help/privacy manuscript: expose bilingual facts drafts, with entity, retention and third-party sharing pending confirmation. No legal/compliance or deletion promise.
- Amap verification is incomplete: Trips shows a static bilingual unavailable state. No SDK, Key, map tiles/points, location request, route data or provider call is added. This does not deliver Issue21 or map integration.

## Delivered UI and paths

- Memory keeps Account/Language and existing Help/Privacy/Support/Feedback navigation. Pricing appears **after** these information links, so the new passive display does not push the existing links behind a pricing section. Help also reuses the same display section after existing guidance.
- A native read-only Section says Free at launch / 首发免费, labels the two future placeholders and renders their exact raw labels with Text(verbatim:). It explains no purchase, billing, subscription, paid access or plan activation is enabled; benefits are not confirmed. It has no button, StoreKit/billing import, entitlement operation or price persistence. Account/invitation requirements remain unchanged.
- Memory → Support now has actual native mailto links for the confirmed addresses, plus selectable address fallback, bilingual labels/hints and Help/Privacy links. URLs contain only the exact address, no subject/body/user-data query. Opening delegates to the user's mail app; the user reviews/sends there. This work does not open that app or send mail, and the UI does not promise delivery/replies.
- Help is visibly a facts draft and retains existing account/invitation/draft/unknown-action/offline/deletion boundaries. Privacy is a structured facts draft with current local-preference/read/cleanup facts, separate stop-use/storage-cleanup/local-session semantics, and explicit unknown responsibility/retention/backup/third-party sharing/offline policy rows. Contact is a draft-inquiry destination, not an invented legal officer designation. No final privacy policy/publication claim.
- Trips adds one static Map section with Map unavailable / 地图暂不可用 and Amap verification incomplete / 高德认证尚未完成. There are no actions. Existing formal-trip read callbacks, selection/navigation, sheets, lifecycle and wire consumers are unchanged; no fake map or coordinates.

Files: PublicInformation.swift (closed display enum/contact URLs/native information views), MemoryShell.swift, HelpView.swift, TripShell.swift, PublicInformationTests.swift. Only these UI/test deltas should be integrated; do not whole-tree replace current canonical FEAS/Memory hosts or graph from this older owner's branch.

## Verification and preserved environment failure

Initial existing /tmp SwiftPM scratch/cache repositories had disappeared or lost revisions. The first test/build setup failed before executing tests or compiling the new UI. initial-cache-test-failure.txt.xz and initial-cache-ios-failure.txt preserve the failure; it is not a UI PASS or product failure. No shared cache cleanup, lock edit or peer mutation was used to resolve it.

Each of the11 original frozen revisions was confirmed in Testing's existing read-only checkout. They were cloned locally with --mirror --no-hardlinks --dissociate into this module's own ignored cache; all copied object stores are independent, with no alternates. private-cache.json records exact revisions/paths. Source checkouts were only read. Final build/test processes set protocol.https/http/ssh/git.allow=never through task-local GIT_CONFIG_COUNT, GIT_TERMINAL_PROMPT=0, --skip-update and --disable-automatic-resolution; no dependency installation/download or real-service call is required for the final runs. No global Git/config setting was changed.

The formal ebb70 preparation remains untouched. A new own ignored UI-check copy overlays only the five scoped UI/test files; all270 other base files, all12 formal peer inputs, manifests, SDK and locks remain byte-exact. This is a UI verification derivation, not a new formal graph input/pin. inputs.json.xz and verification.json record the overlays and actual frozen macOS/iOS checkout revisions.

Actual results:

- **PASS:9 functions /2 suites** (PublicInformationTests3 + existing ShellStateTests6). Checks exact confirmed future price labels across languages without access/state changes, exact addressed mailto URLs without prefilled private content, existing information routes/language/draft/generation preservation and original state invariants. No domain suites or old full-graph tests rerun/count inflation.
- **PASS: actual CJShell arm64 iOS17 simulator-target compilation**, installed iPhoneSimulator27.1 SDK. Compiles the real new SwiftUI information/map views in the existing complete fixed graph, not a synthetic Shell. No Demo/App install or launch.
- **PASS:** frozen actual macOS/iOS checkout revisions, all270 unchanged files, scoped source diff review and git diff --check. Ordinary compiler/cache warnings are preserved. The Trips diff is only the nine-line static section, with no new handler/task/import/request.
- **UNRUN:** real display/render/gesture/link activation in Simulator, actual mail-app handling/delivery/replies, VoiceOver spoken/focus behavior, payment/paid rights, Amap/provider/location and real service/device I. Model tests and compilation do not establish those results. No CUA or previously unknown/rejected input is retried.

## Reproduction inputs

The UI-check root printed in prepare.txt is `ios/Modules/CJShell/.local/public-information/81ee210b2e1c6c72`. It contains the exact unchanged ebb70 preparation files except the five task overlays listed in verification.json. Private cache is CJShell/.local/public-information-cache/81ee210b2e1c6c72; scratches/module caches are CJShell/.local/public-information-builds/81ee210b2e1c6c72/{mac,ios,mac-cache,ios-cache}. These are ignored local artifacts; no binary/cache is committed.

Final commands use env -u SDKROOT -u CJ_SHELL_ISOLATED_DEPS -u CJ_CLEANUP_ISOLATED_DEPS plus GIT_TERMINAL_PROMPT=0 and GIT_CONFIG_COUNT=4: protocol.https.allow=never, protocol.http.allow=never, protocol.ssh.allow=never, protocol.git.allow=never. Set task-local CLANG_MODULE_CACHE_PATH/SWIFTPM_MODULECACHE_OVERRIDE to the respective mac-cache/ios-cache, and use swift test/build --disable-sandbox --skip-update --disable-automatic-resolution --package-path <UI-check>/Modules/CJShell --scratch-path <private mac/ios scratch> --cache-path <private cache>. Test filter 'PublicInformationTests|ShellStateTests'; iOS build additionally --triple arm64-apple-ios17.0-simulator --sdk /Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator27.1.sdk --target CJShell. Exact final output is in tests-final.txt/ios-build-final.txt archives.

Price/currency/period fields are now confirmed and are no longer marked unknown. Privacy responsibility, retention/backup periods and third-party sharing still need confirmed facts; availability honesty is not a final legal policy. This local UI candidate does not close Issue7/21, establish service readiness or authorize public release. Archives preserve original bytes/SHA256 in archives.json.
