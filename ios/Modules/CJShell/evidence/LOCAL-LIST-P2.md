# CJ006 local selection + original-binding P2 evidence

2026-10-22 Asia/Shanghai. Fixed source **f0c502fb2537be9c5e6fb709a2cd17b79dbd5e48**. This evidence commit adds no code. Source diff base **163e139c8e206f82a78b914e503dae6b3f9f6260**, the normal fixed ac298107 dependency intake. Contains both urgent P2 repair and preceding unreviewed local-list work; not a minimal-only patch on 3f65d5c. No dirty reset or second writer; prior 3f65d5c and 34ebd46 preserved.

## P2 before / after

Read Testing's fixed 3f65d5c REPORT.md and copied its exact independent test into owned CJShell tests. Before repair, current combined working source also reproduced **1 test / 2 failures**: old A save error cleared B configuration and invalidated B lease. Original output local-list-p2/before.txt retained. This confirms the issue remained relevant after the fixed dependency intake; no source downgrade or dropped assertion.

After repair, **17 related test functions PASS** in three suites (local-list-p2/after.txt): original host8, list5, reentry4 (save case executes both true/false storage-throw arguments). The original B-isConfigured and B.validateScope assertions remain, with added current-B editor/saved-marker checks. Old query failure after B bind, injected bind admission reentry, and old storage-load callback failure preserve B. Same-binding save failure still storage-blocks via original host test. Rejected unacquired scope no longer invokes resource invalidation; this intentionally protects a resource that could already be activated for another lease.

Projection selection tests verify no initial body load without manual IDs, exact UTF8-distinct NFC/NFD IDs, explicit draft loading, chosen-ID-only query, canonical phase refresh, old captured projection rejection and selection disabled during waiting/late invalidation. Updated prior fixtures use unique synthetic namespaces because newly consumed producer includes process-wide prior-action denial; no production authority or recovery gate was relaxed.

Final iOS standalone compile/sign PASS (local-list-p2/ios-build.txt), original adjacent module sources, arm64 simulator iOS17 target with SDK27.1. No wire/key type copies or producer edits; diff against ac298107 for CJMessageClient empty. Generated exports/pins from prior allocated preparation reused unchanged. `git diff --check` PASS. No unrelated full suite rerun.

## Actual bounded preview

Own CJ006-Shell-20261021 / iPhone17 Pro/iOS26.5 / 824A7623-8882-45C9-94A7-7BD2F758B685, bundle local.cj006.shell.demo, --message-demo. Defaults were re-established for exact CJ006 device after tool reset.

1. Opened assistant double-line → Local recovery. local-list.jpg shows unordered-local/not-server-history explanation, synthetic label, draft conversation reference and action ID/phase. No private body, receipt or key displayed. Main editor initially empty; query disabled until action selection.
2. Tapped draft reference; explicit replace confirmation appeared. Confirmed load; AX read back only then Synthetic draft / 合成草稿 in editor (draft-confirmed snapshot). Pending confirmation uses original lease-bearing projection.
3. Selected synthetic-original-1, closed sheet, then tapped original-action query. selected-original-query.jpg shows notObserved warning, unchanged selected draft, send disabled and synthetic-not-service-reply label. No request was sent; demo uses real core state transitions and a memory store.

Images were opened and inspected, target/text snapshots read back. These prove only the described simulated UI sequence, not live null decoding, ordering/history completeness, VoiceOver or real storage. No real credential or private input used. App stopped and device read back **Shutdown**; no other device operated. Artifacts hashed in local-list-p2/sha256.txt.

## Delivery / limits

Independent review/testing of both P2 and list delta pending; do not mark original P2 closed solely from author tests. Exact consumption/state contract: contracts/ui/LOCAL-RECOVERY-LIST.md. Auth/clear-failure and default-unconfigured gates remain; livePOST, real key namespace, Keychain, provider, network, server history and physical device remain UNRUN/unconnected. No push/remote PR/merge/deploy. Main may route this fixed composite candidate for focused dual review.
