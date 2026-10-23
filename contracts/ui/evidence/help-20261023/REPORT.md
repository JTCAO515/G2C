# CJ006 bilingual help and source-level accessibility continuation

Base 31045af6f2ef1ebaabb6d33de252a74235832e16; only CJShell and own UI evidence changed. Prior render/input FAIL/UNKNOWN remains in render-20261023 and was not retried or relabeled. This is actual product source work, not only an acceptance-gap document.

## Delivered behavior

- Memory → Help now uses native List sections for first account creation, invited eligibility, draft review/rejection, offline availability/expiry, original Usage reads and deletion/local cleanup boundaries. Direct existing NavigationLinks lead to Account, Language, Privacy and Support. No new service, route type, business operation or persistent data layer.
- Registration remains conditional on configured account services, email verification remains conditional on its actual response, and account creation never grants invitation eligibility. Old data/subscriptions do not migrate.
- Current Trip draft decision UI is read-only; help explicitly explains that closing is neither rejecting nor accepting/saving. Unknown outcomes require original-action reconciliation, not replacement submission.
- Offline reader/expiry and deletion/closure are unavailable in this interface. Stopping use, storage cleanup and local-session cleanup are separate. No retention duration, human assistance, immediate disconnected-device wipe or support response is promised. Privacy/support text now names the missing policy fields instead of silently implying complete terms.
- Assistant resigns draft focus when leaving its Tab or opening one of its existing sheets; draft content and canonical failure sources are unchanged. This fixes the missing source-level focus cleanup, but actual keyboard behavior remains unverified.
- Official Usage reference labels are stacked with fully wrapping/selectable IDs and combined label/value accessibility elements. Both explicit buttons have bilingual hints describing their separate read-only steps. No automatic status query or new source authority.

Sources: accepted docs/scope.md account/old-data boundaries and pending invitation/offline/retention/legal fields; docs/memory.md deletion-vs-cleanup and disconnected-device boundaries; docs/ui.md draft/keyboard/large-text constraints; current AccountView, TripContainerProposal and OriginalUsageContainerHost actual capability states. Testing ISSUE-CLOSURE-20261023/REPORT.md #7 supplied the acceptance gap, not permission to invent policies.

## Actual verification

- build.txt: real iOS CJShell build + standalone existing Demo link/sign PASS. No Xcode project, root, SDK module, dependency lock or production config changes.
- state-tests.txt: existing six ShellState tests PASS, including language/navigation/draft preservation and identity invalidation. This validates the model only; no mirrored copy tests added and no domain suites rerun.
- ui-contract.txt: existing seven positive/five negative UI samples PASS. git diff --check PASS.
- Existing dedicated CJ006 simulator 824A7623-8882-45C9-94A7-7BD2F758B685, iOS26.5, normal working XcodeBuildMCP stop/install/launch/read-only snapshot path. Demo-only --help-preview preselects the actual Help route with no configured resources, in isolated cj006.demo.help preferences. English PID4704 (--help-preview); Chinese accessibility3 PID5470 (--help-preview --chinese --large-text). Screenshots and runtime snapshots show actual initial text wrapping and existing Back/Tab semantics. No live account, Keychain, provider or external network.
- No new tap, CUA selection, scroll, keyboard action or VoiceOver activation was attempted. Prior CUA call ended in timeout/kernel reset, no outstanding tool execution is held here, but its approval/input outcome remains UNKNOWN and Main's earlier waitingOnApproval report is preserved. Preselected-route rendering does NOT establish navigational reachability by actual activation, full long-page scrolling, sheet exit, keyboard behavior, VoiceOver speech or focus order.

## Concrete JT information still required

Support contact/destination, availability hours, response timeframe and responsible operator; privacy responsible entity/contact and processing terms; retention periods by domain, backup cleanup periods, deletion/recovery boundaries and responsible party; maximum offline validity, start/renewal points, expiration behavior and reconnection/account-closure cleanup boundary; invitation issuance/revocation rules and owner. No values are guessed. These fields and working support/privacy materials remain acceptance gaps; naming them honestly does not satisfy complete-policy AC.

Issue7 stays open: actual primary VoiceOver path, full large-type/keyboard/long-text interactions, and finalized privacy/support content still need evidence/inputs. Issue4 and I#4/#5 remain separately assessed. Current source/readiness work does not claim real business I or App/device acceptance.
