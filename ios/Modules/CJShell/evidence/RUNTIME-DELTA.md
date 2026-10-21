# CJ006 runtime / identity delta

Date: 2026-10-21 Asia/Shanghai. Reviewed base e722befc9adf53e07dfb508198ff49710ab91b01 → source a9d0a9da13ec507882939e7c13114acda348e509. This report's containing commit only adds evidence. Original RESULTS.md remains historical; this report supersedes its runtime UNRUN subset.

Author-owned simulator: CJ006-Shell-20261021, iPhone 17 Pro / iOS 26.5, UDID 824A7623-8882-45C9-94A7-7BD2F758B685. Created new; no CJ004/CJ005/VP device modified. Reused prior standalone bundle before minimal fixes, then rebuilt only CJShell/Demo. App local.cj006.shell.demo. Final device state read back Shutdown, app stopped. No real service/account/network integration.

## Fixes and focused tests

- Review P2 reproduced visually: line.2.horizontal produced an empty history circle. Replaced with two native Capsule strokes; actual rendering is visible in final-draft-keyboard-en.jpg and assistant-zh-draft-retained.jpg. The labelled history button opens the actual history sheet (history-zh.jpg; snapshot step history-tap-zh). No guessed symbol substitution.
- Added FocusState + native keyboard Done/完成; observed keyboard dismiss and retained draft. This addresses difficulty returning from an empty scroll area to tabs. Assistant uses a NavigationStack for the keyboard toolbar, without an app navigation title/bar.
- UI@1.1 replaces external unbound body/direct domain writes with ShellPresentation + captured ShellGeneration. invalidateIdentity rotates then clears all private UI state; language/selected tab remain. Existing AUTH draft is not imported. See contracts/ui/README.md migration and host responsibilities.
- New identity test passed: clears draft/context/path/body/all page states; rejects old generation after reset and after new B content; rejects another instance's token; language preserves current generation. Six Swift tests passed total (runtime/swift-tests.txt). Prior independent five-state/7-positive/5-negative results remain scoped to e722bef; author reran changed version example check PASS. No unrelated test suite run.

## Observed runtime results

| Scope | Result / evidence |
| --- | --- |
| Four tabs | PASS on this simulator: exact order in English and Chinese AX snapshots; visited Assistant, Trips, Plugins, Memory. |
| Account in Memory | PASS: Memory list exposes account/language/help/privacy/support while disconnected; account destination explicitly says no account service. snapshots memory-en/account-en. |
| Language and navigation | PASS: English → Chinese while inside Language remained on same route; tab round-trip returned to same Language route; Chinese → English stayed there. language-zh-route-retained.jpg and corresponding snapshots. |
| Draft retention | PASS: actual keyboard input read back exactly Beijing draft 006; changing to Chinese and returning to Assistant preserved exact value. final-draft-keyboard-en.jpg → assistant-zh-draft-retained.jpg. Earlier typing ACKs with no focus did not change UI; they are not counted. |
| Language persistence | PASS: stopped/relaunched process, Chinese labels persisted; new draft is empty as explicitly designed. relaunch-zh-persisted snapshot. |
| Plugin placeholder | PASS observed: unavailable/next-version translation text; only four tabs are actionable targets, no tool action or permission prompt appeared. plugins-zh.jpg. This is not a full network audit. |
| Neutral Muse layout | PASS for observed normal size: no app-wide top bar, separate two-line/history, neutral avatar/name and disabled gift; status safe area preserved. Normal keyboard draft and Done visible. |
| Large native body | PASS for rendering and scrolling only: synthetic 40-paragraph bilingual text at accessibility3, observed first section, paragraph 4, paragraph 27, then final status. large-long-body-top / large-body-scroll-at-visible-region / large-body-scrolled-verified / large-body-bottom images. The sample is labelled synthetic. |
| Large font + keyboard | PARTIAL: input and Done are visible, Done dismisses keyboard (large-keyboard / large-keyboard-dismissed snapshot); body viewport is heavily compressed/partly obscured by floating header and composer. Gallery also adds a large close control above shell. Full usability/layout acceptance remains FAIL/OPEN for this combination; no claim that last paragraph is comfortably readable with keyboard open. |
| AX | PASS limited to semantic observation: tab labels/order, history action, Message draft/消息草稿 value, account/language navigation and Done were exposed and operated via AX-target tools. Disabled gift/media/send are excluded from actionable targets. Actual spoken VoiceOver order/disabled announcements and external keyboard navigation UNRUN. |

Screenshots are unedited XcodeBuildMCP JPEG captures; runtime/snapshots.json preserves semantic snapshots. runtime/sha256.txt records image and snapshot hashes. Tool screenshot/gesture ACK alone was not used as evidence: images were opened and inspected. Full-screen scroll-area swipe landed on composer and did not move text; bounded gesture in the visible text region did, with paragraph changes confirmed visually. An invalid CUA Simulator binding did not operate a device. Some initial input used a Pinyin keyboard and produced composition text; the final retention check started fresh with the English keyboard and exact observed draft.

## Remaining

UI@1.1 consumer reconfirmation by CJ007, fixed-delta Review/Testing and full host AUTH mapping are pending. Local token is not an authorization credential and cannot fence external host caches or server work; host must validate real identity after awaits independently. Large-text+keyboard composition above remains open. True VoiceOver, physical devices, performance, iOS 17 runtime, memory CRUD and all real services remain UNRUN. CJ004/CJ005 I gates unchanged; Issue #7 stays open. No push/remote PR/merge/deploy.
