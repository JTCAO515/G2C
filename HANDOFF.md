# Project Handoff

> Generated from `docs/handoff.json`; edit the JSON, not this file.
> Run `python3 -B scripts/handoff.py render`, then `python3 -B scripts/handoff.py check`.
> Repository files, Git, Issue and CI state remain authoritative.

## Five-Minute Takeover

1. Run `git fetch origin` and `git status --short --branch`; preserve unrelated work.
2. Read the mandatory files below in order.
3. Check open PRs and their exact-head CI before extending the current slice.
4. Execute only the next action; keep external-resource authorization separate.
5. Update the JSON and render this file before stopping.

## Snapshot

| Field | Current value |
| --- | --- |
| Objective | M1 主链路闭环（模拟器 L1）：账号、聊天、流式回答、草稿、确认与正式行程在 iOS 17.5 模拟器上以本地真实组合跑通，并按 ADR-0007 关闭 M1 的子票和父票；保留正式写入、原动作恢复及外部资源授权边界。 |
| Status | active |
| Phase | M1 parallel lanes (ADR-0007 §2, JT approved 2026-10-28, lane table revised 2026-10-29): #196 merged; Lane A M1 App complete: #159/#194/#164/#212 and parents #7/#10 are closed; #167 PR253 locked head71e4cab merged1f960a1, all main CI40938740022 jobs green; #11 all seven frames have evidence and is closed. Native matrix04 23/23 PASS on the #249 backend combination; real models/tools remain L2 #32. M1 milestone remains open for JT. JT unblocked #198 (local history wiring) and decided #168 Part2 scope (transfer structured time to M2; user-visible draft failure to #170). Lane B: #198/#170 and parent #19 closed; formal local NEEDS/provider_call host PR240 merged573faf1 with all main CI green. Persistent protection0016 prevents configuration downgrade. B M1 is complete; M2 #9 is split into #242/#243/#244 by PR245. First slice #242 has approved scope/design; producer PR249 is merged at beb05b5 with green main. Consumer candidate969b3e8 has local test57/PG18 and all head CI green, but awaits A #167 merge and green main before rebase/final review/merge. Lane C: #227 partial runtime candidate6a69183 has local test57/PG18 including actual-worker memory_run7 PASS. Latest candidate3b1c0df adds only version-design docs; JT approved lease and cross-lane design directions. Full cross-travel scope and #17 lifecycle integration remain unproven. Await B travel-context/MESSAGE/lease freeze and separate typed-schema approval; no typed migration implemented. C handoff PR256 remains closed while B PR257 holds the pair. |
| Accepted Issue | Lane A: #167 and parent #11 closed with L1 evidence; requested M1 App goal complete, M1 milestone remains JT-owned. M2 A queue authorized by JT 2026-10-30: docs PR then #244, #228, #21 App; #244 depends on #242. Lane B: M1 #198/#170 and parent #19 complete; M2 #9 / #242 consumer awaiting A #167 merge and green main; #243/#244 depend on #242. Lane C: #12/#227 -> #17 -> #18 -> #22 backend only. #227 partial code verified locally; cross-travel protocol awaits B owner freeze. Entire ios/#228 are A-owned, #12 stays open. |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-29T20:11:13.033527+00:00 |

## Active Work

- Lane A App complete: #159/#194/#164/#212 and parents #7/#10 already delivered. #167 PR253 final head71e4caba4c3dbbda65dd372724ad43c448021932 independently APPROVED6506103720, exact CI40936684595 and lint40938671881 success, locked merge1f960a11a26e596b6913adfa6fdb99312dbbd45d; main40938740022 all five jobs success. Matrix04 actual headcac619a/basebeb05b5 (includes #249): 23/23 native PASS, each xcresult1/0/0; RUN57/Shell213/Debug/Python57/PG17. Rebase to final head changed only inherited handoff; entire executable tree equality independently verified and original report head preserved. Bilingual stream/stop/failure/unknown, actual answer/draft budget exhaustion, original recovery and worker CLI zero redispatch, actual pending draft effect1/formal Trip0, cross-account refusal, full AX all and token scans pass. Fifteen screenshots attached6505864430/6505884940. #167 three frames and #11 seven frames linked to evidence and closed. Historical FAIL/interrupted/diagnostic and older-head records retained. Real tools/models/fees/cloud/device/VoiceOver/deployment remain UNRUN; real tools/models tracked L2 #32, memory-version fence stays #17. M1 milestone is open for JT. No M2 #244 implementation started.
- Lane B: #198 closed with PR206 and independently verified A native08; #170 and parent #19 closed after PR213/223/230/235/237/240. Final host head861cb67 independently APPROVED6494916060, full head CI, locked merge573faf1, main40862391938 all five success. Fixed executable source test57/57 and PG16/16; independent host/needs/budget and e2e37/37, original downgrade regression zero calls/RUN/proposal and unchanged ledger. Config-loss, two activation/send lock orders, ACK unknown, original period, cross-scope and corrupt-ledger refusal pass. Historical FAIL retained. #212 native failure UI is closed; #167 native budget remains A-owned and was notified6495204833. M2 #9 now has native children #242/#243/#244 (M2, B/B/A; 5/5/4 ACs), with #243/#244 blocked_by #242. PR245 planning sync merged4580bae. #242 scope approved6497345414 and design revision6500837427 independently approved6501046786. Producer PR249 head8a8d01b independently approved6502906442, locked mergebeb05b5, main40915741036 green. Consumer branch b/242-consumer head969b3e8a157a8af270def2943103528cf2a867e2 / draft PR251: actual test57/57, PG18/18, CI40929997672 and lint40929997633 all success; independent code pre-review6505187118 has no findings but is not final APPROVE. JT requires A #167 merge plus green main first; B then rebases and repeats new-head CI/final independent review. PR251 may be temporarily closed solely to serialize this handoff PR; branch and evidence retained. Generic three-kind probes are infrastructure evidence, not real business tools/models/memory or costs. #242/#9 remain open.
- Lane C: #168 Part2 PR208 merged414b0ac with main CI40807520711; #169 PR222 merged630a611 with main CI40821295205; M2 #12 split into #226/#227/#228 with native sub-issue links. #226 PR236 exact head26332b2 independently APPROVED6493581381, all CI40852784786 passed, locked mergee022eac and main CI40854592928 all green. Local test57/57, PG14/14 (e2e37), independent e2e37 including MEMORY6 and migration data retention. #17 now explicitly carries the #11/#19 memory-version fence; #227 consumes it. JT authorized backend-only queue #227 -> #17 -> #18 -> #22 on 2026-10-30; entire ios/CJMemoryClient/CJTripClient and #228 transferred to A. #227 design6507251012 and R1 lease direction approved. Candidate6a6918338628a2f8f3b17ebfc2809f250c42cec9 adds canonical capture/held publication lease, explicit local selection, minimal declared worker/run_worker/draft wiring, and actual runtime-role memory_run PG group. Complete local test57/PG18 exit0; new group7 includes signed API, actual worker/CLI process, source expiry, committed epoch change, size bound, missing-config rejection and metered original exit. Failed initial test command used nonexistent test_worker.py and ran no tests; corrected 34 focused tests PASS. Latest3b1c0df12c8262e1b0e9260d1f5900f5113987f2 adds only proposal docs. Cross-session is not cross-travel: MESSAGE-send.1 rejects non-null Trip and current contexts are conversations, so AC2/full AC4 remain UNRUN and #227/#12 stay open. JT approved C drafting cross-lane version plan then approved its direction, not executing DDL or modifying B-owned files. Draft6507885699/details6507972794 propose B-owned pre-Trip travel-context identity/MESSAGE reference and C typed MEMORY; no new storage/permissions or frozen contracts changed. B notified6507973414; await B freeze of identity/owner/schema/lifecycle/lease/old-consumer protocol before dependent implementation. #17/#18/#22 not started. C standalone handoff remains queued/closedPR256 due B PR257 shared lock; no independent final APPROVE, remote feature CI or merge claimed.
- #186 four cleanup PRs #187–#190 merged with exact-head review; #186 remains open for its owner (Claude). PR #195 (#194 insertion) and #197 (#186 handoff note) are superseded by this revision.

## Accepted Assumptions

- 本轮本地 API 使用 app_from_environment 强制签名入口、私有 PG、FakeProvider 和临时开发身份；不是生产、OTP 或真实模型验收。
- DEBUG 开发环境由 operator 提供；token 的本地 issuer/audience/subject 仅分区模拟器数据，不作为生产身份验证。真实业务权限仍由服务端校验。

## Frozen Decisions

- ADR-0001 产品与用户控制边界继续有效。
- qwen3.8-flash 与北京端点已选定；P2b 原作者报告真实 smoke 4/4，本轮未重跑。
- ADR-0004 已接受；单一 Python 发行包 cj，保留领域 import 名，不恢复同仓 hash pin 或 Git 导出依赖。
- P2：北京、邮箱 OTP、最低 iOS 17。
- JT 当前指令：Codex 实现/测试/交付，Claude 架构/规划/审查，JT 决策与外部资源。
- 历史证据归档 tag evidence-archive-2026-10-27；不改写历史。
- JT 2026-10-27: PR #147 only uses Codex review instead of Claude; continue subsequent P2c work. This is not independent review and not blanket approval for later PRs.
- 已执行（#149、#150 合并；任务 B 为 #154，PR #172 合并）。
- GitHub visibility read-back 2026-10-27: PUBLIC. Secret/local-path prohibitions remain. No repository settings were changed in this task.
- 已执行并结束：#154 于 PR #172 合并，暂停结束。自 PR #171 起按 ADR-0007 第 7 条与 docs/plan/issue-plan.md 自动续作（JT 授权，2026-10-27）。
- JT 2026-10-27：仓库可见性当天先改为 PRIVATE，随后又改回 PUBLIC（gh 读回 PUBLIC）；去本机路径和秘密规则继续有效，许可证仍待定。ADR-0005/0006 的 V2 商业决策因此公开可见。
- accepted (JT 2026-10-27): ADR-0005 proactive fulfillment is V2 scope (backend JT Agent, signals -> cases -> AI execution with human confirmation); V1/P2 scope unchanged. Architecture and model choice remain proposed until the V2a shadow mode (docs/v2/shadow-mode.md).
- accepted (JT 2026-10-27): ADR-0006 V2 membership Free / Plus / Guardian via Apple IAP; human service bundled; memory never deleted by the system, user-requested deletion always honoured; prices pending.
- accepted (JT 2026-10-28): ADR-0008 消息发送许可：服务端会话头 CAS 为不可回退的首次发送证据；加锁的发送状态读取；MESSAGE-SEND@1 冻结，MESSAGE-draft.1 POST 撤回；App 真实发送只在 DEBUG 模拟器开发会话按 ADR-0008 第 7 条开放。

## Architecture Contracts

- contracts/api/openapi.json unchanged in P1.
- backend/migrations/manifest.json: versions 1-10, sha256-checked up/down; applied versions must never be edited.
- Single business authority and recovery semantics per ADR-0003 (proposed) remain the target for P2.

## Changed Files

| Path | Reason |
| --- | --- |
| `docs/plan/issue-plan.md, docs/handoff.json, HANDOFF.md` | JT approved 2026-10-30 M2 ownership, queues and per-file locks, plus A-only M1 closeout; retain B/C evidence and historical failures. |
| `docs/handoff.json, HANDOFF.md` | Queue C-only #227 runtime evidence and cross-travel owner-freeze stop; A/B status text/history retained. PR256 remains closed while B257 owns the shared pair. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `python3 -B scripts/handoff.py render; python3 -B scripts/handoff.py check; git diff --check` | #196 docs-only change: HANDOFF.md matches docs/handoff.json; no whitespace errors. | — |
| pass | `uv run --locked python -B scripts/test.py` | #196 local run 57/57 on the rebased branch (docs-only; no code, test, migration, contract or CI change). | — |
| pending | `#196 exact-head CI and independent review` | Review of 6004dc6 requested changes (handoff fields, shared-file list); fixes in the next head need fresh CI and review. | https://github.com/JTCAO515/G2C/pull/196 |
| pass | `[#200 (#166) 历史] #166 full local checks / independent review / exact-head CI` | test57/57, PG11/11 including e2e28; independent review reproduced e2e28/28, all head jobs green. | https://github.com/JTCAO515/G2C/pull/200#issuecomment-6470507941 |
| pass | `[#200 (#166) 历史] #166 post-merge main CI40698481356` | Five jobs success on96e97af; #166 closed, parent evidence updated. | https://github.com/JTCAO515/G2C/actions/runs/40698481356 |
| fail | `[#201 (#168 Part1) 历史] pytest backend/agent/tests/test_draft.py baseline` | 4 failed /12 passed: duplicate fields accepted and Unicode error escaped the draft failure type. Evidence preserved outside repository. | — |
| pass | `[#201 (#168 Part1) 历史] pytest backend/agent/tests/test_draft.py after structure repair` | 16/16 passed. Includes duplicate spellings, unpaired surrogate and parser recursion bound. | — |
| pass | `[#201 (#168 Part1) 历史] uv run --locked python -B scripts/test.py; uv run --locked python -B scripts/pg_suites.py` | test57/57, PG11/11 including e2e29/29 with10 structural no-publication subcases. Later merged as PR #201 after exact-head CI and independent APPROVE (main CI 40702955553). Travel constraints and user-visible draft failure remain unresolved. | https://github.com/JTCAO515/G2C/pull/201#issuecomment-6471129685 |
| pass | `Lane A #159/#194 closeout` | PR202/211 exact-head CI and independent APPROVE; #194 Shell208, structure2+3, AX1+4. Six screenshots attached. Main40809944579 all five success; parent#7 closed. | https://github.com/JTCAO515/G2C/pull/211#issuecomment-6486610499 |
| fail | `Lane A #164 native04/native05` | Native04 four Debug cases passed, two XCTest AX/log callback crashes; native05 UI passed but container scan failed because simulator was Shutdown. Full native acceptance remains incomplete. | https://github.com/JTCAO515/G2C/issues/164#issuecomment-6486770716 |
| pass | `Lane B #198 closure` | Backend test57/PG11, independent redline review and postmerge main green; A native7/7 independently verified with exact-head CI. This is local L1, not cloud/device. | https://github.com/JTCAO515/G2C/issues/198#issuecomment-6487552011 |
| pass | `[Historical] Lane B #213 backend slice` | Independent redline review; test57/PG11 and dedicated PG/migration/cancellation evidence; locked-head merge64a1966 and all five main jobs green. Native #212 and budget/NEEDS remain unproven. | https://github.com/JTCAO515/G2C/issues/170#issuecomment-6487143581 |
| pass | `[Historical] Lane B budget/NEEDS design scope review` | Design9748174 revised after four findings; APPROVE-for-scope-review only. All new implementation checks UNRUN, JT scope approval pending. | https://github.com/JTCAO515/G2C/issues/170#issuecomment-6487473477 |
| pass | `Lane A #164 PR216 closeout` | Native08 7/7; HTTP82+Recovery37, rebased Shell213; DB original-ID/bytes, zero extra writes and app/artifact scans. Exact-head CI and final independent red-line APPROVE; post-merge main40815552071 all five success; #164/#10 closed. Prior failed runs preserved as historical evidence. | https://github.com/JTCAO515/G2C/pull/216#issuecomment-6487560776 |
| pass | `Lane A #167 Part1 PR229` | Exact head96e1973: native07 seven ready cases PASS; real budget UNRUN, overall PARTIAL_PASS. RUN45/Shell213; exact-head CI and independent final APPROVE; locked-head merge67417ff, main40826910920 green. Old failed runs retained. | https://github.com/JTCAO515/G2C/issues/167#issuecomment-6489552212 |
| pass | `Lane A #212 PR232 final acceptance` | Native12 exact b22de6f clean 9/9, 94 requests matched to DB/provider counts, cross-account8 refusals, AX complete sentences/audits, token scans; independent final redline APPROVE and locked merge dcf1c30, main40835826547 all five success. Historical native FAIL/interruption retained; typography diagnostic kept separate. | https://github.com/JTCAO515/G2C/issues/212#issuecomment-6490927280 |
| pass | `Lane A #167 unmerged v2 read candidate8b39fc7` | L0 Swift suite reports57 tests (opt-in liveLoopback skipped), explicit v2 path/stage/receipt/session/404-no-fallback negatives and Debug App build PASS. Existing App composition stays v1; no real budget native result or feature PR. | https://github.com/JTCAO515/G2C/issues/167#issuecomment-6491061753 |
| pass | `Lane A #167 supplementary published02/03 at a27af6b` | Two separate native single-case reports remain PARTIAL_PASS. Same clean head/source hashes; each original run has POST1/receipt1, provider2 (answer1/draft1), draft GET2, effect1 and its scoped pending proposal1/formal Trip0; reopen/full bilingual AX/token scans pass. Counts apply only to that original run. Real budget and external tools remain UNRUN. | https://github.com/JTCAO515/G2C/issues/167#issuecomment-6491513469 |
| pass | `C #168 / #169 reviewed delivery and post-merge main CI` | #168 PR208 main40807520711; #169 PR222 main40821295205. Both had exact-head full CI and independent approval. L1 only; real services remain separately gated. | https://github.com/JTCAO515/G2C/pull/222 |
| pass | `C #226 full local gates, independent red-line review and exact-head CI` | test57/57, PG14/14 including e2e37; independent test57 and e2e37 including Memory6 and migration retention. Head26332b2 APPROVE6493581381 and CI40852784786 passed. | https://github.com/JTCAO515/G2C/pull/236#issuecomment-6493581381 |
| pass | `C #226 post-merge main CI40854592928` | Mergee022eac: all five main jobs success. #226 five boxes and parent #12 partial progress backfilled; #227/#228 remain open. | https://github.com/JTCAO515/G2C/actions/runs/40854592928 |
| pass | `C closeout handoff render/check and diff check` | Documentation-only C entry update; verification performed before this handoff commit. | — |
| pass | `Lane B #170 / parent #19 final closure` | PR240 exact head861cb67 full CI and independent redline APPROVE6494916060, locked merge573faf1; main40862391938 all five success. test57/PG16, independent e2e37 and three PG groups, original downgrade regression. Parent subissues168/169/170/212 all closed; L2 #32 and memory fence #17 retained. A #167 native budget is not claimed. | https://github.com/JTCAO515/G2C/issues/19#issuecomment-6495191603 |
| pass | `B closeout: python3 -B scripts/handoff.py render; check; git diff --check` | B-only closure and producer-readiness update; generated handoff matches source. No executable files changed. Final host test57/PG16 and main CI remain the product evidence. | — |
| pass | `B M2 #9 native split and planning sync` | Native children242/243/244, milestone3, B/B/A ownership, AC5/5/4, and243/244 blocked_by242 read back. Parent six frames retained; L2 comment6495923145 and L3 comment6496027468 registered. PR245 exact-head CI and independent APPROVE6496380335, merge4580bae. This is planning evidence only; #242 implementation UNRUN. | https://github.com/JTCAO515/G2C/issues/9#issuecomment-6496027889 |
| pass | `Lane B #242 producer PR249` | Exact head8a8d01b independent APPROVE6502906442, all head CI green; locked mergebeb05b5 and main40915741036 all green. Migration0017 producer only. | https://github.com/JTCAO515/G2C/pull/249 |
| pass | `Lane B #242 consumer candidate969b3e8` | Actual test57/57 and PG18/18; CI40929997672 and lint40929997633 all success. Independent pre-review6505187118 has no code findings; not final merge APPROVE. Original FAIL/interrupted evidence retained. | https://github.com/JTCAO515/G2C/pull/251 |
| pending | `Lane B #242 consumer post-A merge gate` | Wait for #167 merge and green main, then rebase/new-head verification and independent final APPROVE. Consumer not merged; #242/#9 remain open. | https://github.com/JTCAO515/G2C/issues/242#issuecomment-6504795674 |
| pass | `Lane A #167 matrix04 on #249 backend baseline` | Actual cac619a/basebeb05b5: 23/23 native, each xcresult1/0/0; RUN57/Shell213/Debug/Python57/PG17. Canonical ledger/original recovery, actual operator and worker CLI, cross-account, AX all and scans independently verified. Later71e4cab differs only in inherited handoff; original report head unchanged. | https://github.com/JTCAO515/G2C/pull/253#issuecomment-6506103720 |
| pass | `Lane A #167 PR253 exact-head review and locked merge` | Head71e4caba full CI40936684595 and lint40938671881 success, independent APPROVE6506103720, locked merge1f960a1. Fifteen actual native screenshots attached to PR. | https://github.com/JTCAO515/G2C/pull/253 |
| pass | `Lane A #167 post-merge main CI40938740022 and parent closure` | All five main jobs success at1f960a1; #167 three frames and parent#11 seven frames linked to evidence and closed. #165/#166 remain closed; L2 #32 and memory fence #17 retained. M1 milestone remains open for JT. | https://github.com/JTCAO515/G2C/actions/runs/40938740022 |
| pass | `A closeout: python3 -B scripts/handoff.py render; check; git diff --check` | A-only allowed handoff fields and generated Markdown; B/C text and all previous verification entries preserved. No executable changes. | — |
| pass | `A M2 planning + M1 closeout: handoff render/check and git diff --check` | Three documentation files only; JT approved M2 lane ownership, queues and per-file locks on 2026-10-30. Open PR251 file list has no overlap with docs/plan/** or the handoff pair. New-head CI, final independent review and merge remain pending. | — |
| pass | `C #227 product head6a69183 full local gates` | test.py57/57 and pg_suites.py18/18 exit0. Includes B baseline groups plus new memory_run7/7, signed API/runtime-role PG/actual run_once and CLI new process/FakeProvider/metered exit. Later candidate3b1c0df changes only proposal docs. Does not prove cross-travel or complete #17 lifecycle integration. | https://github.com/JTCAO515/G2C/issues/227#issuecomment-6507885699 |
| not-run | `C #227 travel-context/typed-memory/new migration and full closure` | Lease/cross-lane design directions approved; C typed wire/DDL proposal6507972794 ready. B producer/lease and reference keys not frozen; no new typed implementation or migrations executed. Remote feature CI/independent final APPROVE/locked merge/postmerge CI UNRUN; no issue closure. | https://github.com/JTCAO515/G2C/issues/227#issuecomment-6507972794 |

## Blockers

- L2/cloud/OTP/real model/device resources, branch protection and production keys remain JT-owned.
- Lane B #242: consumer merge waits for A #167 to merge and latest main CI to pass, per JT coordination6504795674 and A freeze6504784577. Scope/design approval is complete; implementation and pre-review are complete at969b3e8, final post-A rebase/CI/APPROVE and merge remain pending. Applied migrations1–17 and old contracts/RLS remain frozen. #243/#244 depend on #242 and are outside this first-slice delivery; no fixture or M1 subset substitutes for generic acceptance.
- Lane C #227: await B-owned travel-context/MESSAGE and protected lease freeze; typed MEMORY schema/DDL/permissions are design only and need specific approval after B keys/lifecycle are fixed. Cross-travel and formal #17 editing/enable/withdrawal worker combinations remain UNRUN. B PR257 holds handoff files; C PR256 stays closed and must be refreshed from post-257 green main before review/open/merge. Prior 251/255 coordinator locks are closed; no B unmerged candidate was adopted.

## Risks

- DEBUG 开发组装仅限 Simulator、显式 loopback 和开发 token；不是生产认证/存储激活。Release 和真机保持未连接。
- 确认/未知恢复使用现有冻结语义；不代表真实服务、设备、备份恢复或长期数据生命周期验收。
- 原动作/模拟器 Keychain key 留在隔离开发命名空间，不删除无关数据；临时 API/PG 在脚本结束关闭。
- 证据在仓库外及 PR 描述；运行脚本会构建并安装目标 Simulator App，不能据此发布或安装真机。
- #144 独立 V2 范围继续保持不动；完整 P2c 仍缺 MESSAGE 发送许可及真实身份等阶段。

## Operator Actions

- JT 确认 #194 滴滴占位的最终中英文案，以及 App 内能否显示“滴滴”文字名称。
- JT 决定：是否启用 main 分支保护（仓库已 public，可免费启用）。
- JT 确认 #159 帮助/隐私/支持文案。
- JT 按需在 docs/authorizations/M1.md 批准 L2 外部资源；目前为空。
- 生产签名 key 来源/轮换、真实模型费用、真机/发布、许可证继续由 JT 决定。

## Next Smallest Action

- Action: A: JT approved M2 queue/ownership and per-file locks on 2026-10-30 (docs/plan/issue-plan.md). After this M1 handoff + planning PR is locked-head merged and main CI green, check #242: if closed do #244, otherwise do #228 frames 1–3 using #226. #228 frame4 waits for C #227 current context freeze. Record a stop before changing parent; #21 App waits for B #13 PLACE freeze. #194/#159 await JT wording. Entire ios/** belongs to A. B: preserve b/242-consumer at969b3e8 and restore draft PR251 after the handoff-only PR if temporarily closed. Wait for A #167 merge and green main; fetch/rebase onto that main, publish a replacement branch/PR without force push if head changes, run required tests and all new-head CI, obtain fresh independent final APPROVE, then lock-head merge and verify main. Only then reconcile #242 ACs and parent #9; #243/#244 remain dependent future work. C: retain c/227-runtime3b1c0df and exact product6a69183 evidence; do not equate conversation isolation with travel isolation or close227. B must freeze travel-context/MESSAGE/lease/schema reference; C then finalizes typed wire/DDL with JT approval before implementation. #17 split follows, then #18 FEASIBILITY draft/JT freeze with B PLACE/NEEDS gates, then #22 backend. First recheck B handoff257; after merge/main green create fresh C-only handoff candidate from that main without force push and obtain final independent exact-head CI/APPROVE. Until then closed256 only queues C state, no competing open handoff PR. All ios/#228 A; last closing227/228 reconciles and closes12.
- Expected observation: A: #167 and #11 are closed with linked native23/23, exact-head independent APPROVE and green post-merge main. App reads original v2 persisted budget stages; failure/unknown never imply budget exhaustion or safe generation retry. Actual tools/models remain L2 #32, memory-version fence #17, M1 milestone open. C: #168/#169/#226 are closed with evidence; #12 remains open for #227/#228. No automatic recall/App completion is inferred from the server save/read slice. B: original protected work cannot run without its configuration; #170 closure does not imply cloud/real-cost/native-budget completion. #9 is split; #242 producer is merged and consumer local infrastructure tests/head CI pass, but consumer merge/final approval remain pending A #167. #242/#9 stay open; no real model/tool/cloud/native acceptance is inferred.
- Resume command: `# A completed: audit closed issues; M1 milestone stays open
gh issue view 167 --repo JTCAO515/G2C
gh issue view 11 --repo JTCAO515/G2C
gh issue view 242 --repo JTCAO515/G2C --comments
# C next queue (outside this completed requested slice)
gh issue view 227 --repo JTCAO515/G2C`

## Rollback

revert PR #171 合并提交即可恢复原队列写法；GitHub 上的子票、里程碑与父票正文按 Issue 编辑历史（edited 记录）手工回退。无代码、迁移或配置变更。

## Mandatory Reading Order

1. [HANDOFF.md](HANDOFF.md)
2. [docs/adr/0007-issue-closure-workflow.md](docs/adr/0007-issue-closure-workflow.md)
3. [docs/plan/issue-plan.md](docs/plan/issue-plan.md)
4. [AGENTS.md](AGENTS.md)
5. [README.md](README.md)
6. [backend/README.md](backend/README.md)
7. [ios/App/README.md](ios/App/README.md)

## Integrity Check

```bash
python3 -B scripts/handoff.py check
```
