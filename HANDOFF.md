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
| Phase | M1 parallel lanes (ADR-0007 §2, JT approved 2026-10-28, lane table revised 2026-10-29): #196 merged; Lane A M1 App complete: #159/#194/#164/#212 and parents #7/#10 are closed; #167 PR253 locked head71e4cab merged1f960a1, all main CI40938740022 jobs green; #11 all seven frames have evidence and is closed. Native matrix04 23/23 PASS on the #249 backend combination; real models/tools remain L2 #32. M1 milestone remains open for JT. JT unblocked #198 (local history wiring) and decided #168 Part2 scope (transfer structured time to M2; user-visible draft failure to #170). Lane B: M1 #198/#170 and parent #19 complete. M2 #242 producer PR249 is merged. After A prerequisite1f960a1/main40938740022 passed, PR251 was replaced without force push by PR255 at392a4bbe2d1046d5b6bc2b76df2d212a06fdbc6d. Local test57/PG18 pass, but independent final review reproduced an uncaught UnicodeEncodeError in the registered model input boundary, leaving RUN running with provider0. JT explicitly requires stopping on blocking review: no repair or consumer merge; #242/#9 stay open and the subsequent B queue has not started. Lane C: #168/#169 and M2 #226 delivered with reviewed heads and green post-merge CI; #227/#228 remain future work and #12 stays open. |
| Accepted Issue | Lane A: #167 and parent #11 closed with L1 evidence; requested M1 App goal complete, M1 milestone remains JT-owned. M2 A queue authorized by JT 2026-10-30: docs PR then #244, #228, #21 App; #244 depends on #242. Lane B: M2 #9 / #242 stopped on PR255 independent review at392a4bbe; await JT instruction before repair/resumption. #243 depends on #242; #13 then #16 then #14 remain subsequent work. Lane C: requested scope through #12/#226 complete; next queue is #227 then #228. |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-29T20:24:36.445345+00:00 |

## Active Work

- Lane A App complete: #159/#194/#164/#212 and parents #7/#10 already delivered. #167 PR253 final head71e4caba4c3dbbda65dd372724ad43c448021932 independently APPROVED6506103720, exact CI40936684595 and lint40938671881 success, locked merge1f960a11a26e596b6913adfa6fdb99312dbbd45d; main40938740022 all five jobs success. Matrix04 actual headcac619a/basebeb05b5 (includes #249): 23/23 native PASS, each xcresult1/0/0; RUN57/Shell213/Debug/Python57/PG17. Rebase to final head changed only inherited handoff; entire executable tree equality independently verified and original report head preserved. Bilingual stream/stop/failure/unknown, actual answer/draft budget exhaustion, original recovery and worker CLI zero redispatch, actual pending draft effect1/formal Trip0, cross-account refusal, full AX all and token scans pass. Fifteen screenshots attached6505864430/6505884940. #167 three frames and #11 seven frames linked to evidence and closed. Historical FAIL/interrupted/diagnostic and older-head records retained. Real tools/models/fees/cloud/device/VoiceOver/deployment remain UNRUN; real tools/models tracked L2 #32, memory-version fence stays #17. M1 milestone is open for JT. No M2 #244 implementation started.
- Lane B: #198/#170 and parent #19 remain complete with their historical evidence. #242 scope/design approved6497345414/6501046786; producer PR249 mergedbeb05b5 with green main. A prerequisite #167/PR253 merged1f960a1 and main CI40938740022 five jobs success. No-force rebase of969b3e8 produced392a4bbe2d1046d5b6bc2b76df2d212a06fdbc6d, replacement PR255; PR251/old branch remain preserved. This head test57/57 and complete PG18/18 exit0 (e2e37, registered_exit included); independent run50+usage35 tests and54 subtests plus registered_exit PG pass. Blocking independent counterexample: API accepts a JSON-escaped lone surrogate, registered _model_input UTF8 encoding escapes as UnicodeEncodeError; formal worker aborts with provider0 and original RUN still running. Standard PASS does not cover that failure and no final APPROVE exists. JT ordered a stop on blocking review, so implementation repair/merge and later tickets are withheld. #242/#9 stay open; #243 remains dependent, then #13 PLACE, #16 FACT, #14 NEEDS require their own split/draft/freeze and JT source decisions. Real tools/background business producers, provider/fees/cloud remain UNRUN; generic controlled probes prove infrastructure only.
- Lane C: #168 Part2 PR208 merged414b0ac with main CI40807520711; #169 PR222 merged630a611 with main CI40821295205; M2 #12 split into #226/#227/#228 with native sub-issue links. #226 PR236 exact head26332b2 independently APPROVED6493581381, all CI40852784786 passed, locked mergee022eac and main CI40854592928 all green. Local test57/57, PG14/14 (e2e37), independent e2e37 including MEMORY6 and migration data retention. #17 now explicitly carries the #11/#19 memory-version fence; #227 consumes it. Requested C goal ends after this first M2 slice; #227/#228 remain OPEN, not implemented. Local MEMORY activation is explicit/private-policy-only; no App/automatic recall or cloud/real-account claim.
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
| `docs/handoff.json, HANDOFF.md` | B #242 independent blocking-review stop; retain candidate, PASS and FAIL evidence, exact next action and JT resumption gate. A/C entries preserved. |

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
| pending | `[Historical at969b3e8] Lane B #242 consumer post-A merge gate` | Historical waiting state retained from PR251. A #167/main green, replacement rebase and local gates are now satisfied; PR255 has a blocking Unicode REQUEST CHANGES and JT ordered a stop. Final consumer APPROVE/merge remain pending; original link records the prior coordination. | https://github.com/JTCAO515/G2C/issues/242#issuecomment-6504795674 |
| pass | `Lane A #167 matrix04 on #249 backend baseline` | Actual cac619a/basebeb05b5: 23/23 native, each xcresult1/0/0; RUN57/Shell213/Debug/Python57/PG17. Canonical ledger/original recovery, actual operator and worker CLI, cross-account, AX all and scans independently verified. Later71e4cab differs only in inherited handoff; original report head unchanged. | https://github.com/JTCAO515/G2C/pull/253#issuecomment-6506103720 |
| pass | `Lane A #167 PR253 exact-head review and locked merge` | Head71e4caba full CI40936684595 and lint40938671881 success, independent APPROVE6506103720, locked merge1f960a1. Fifteen actual native screenshots attached to PR. | https://github.com/JTCAO515/G2C/pull/253 |
| pass | `Lane A #167 post-merge main CI40938740022 and parent closure` | All five main jobs success at1f960a1; #167 three frames and parent#11 seven frames linked to evidence and closed. #165/#166 remain closed; L2 #32 and memory fence #17 retained. M1 milestone remains open for JT. | https://github.com/JTCAO515/G2C/actions/runs/40938740022 |
| pass | `A closeout: python3 -B scripts/handoff.py render; check; git diff --check` | A-only allowed handoff fields and generated Markdown; B/C text and all previous verification entries preserved. No executable changes. | — |
| pass | `A M2 planning + M1 closeout: handoff render/check and git diff --check` | Three documentation files only; JT approved M2 lane ownership, queues and per-file locks on 2026-10-30. Open PR251 file list has no overlap with docs/plan/** or the handoff pair. New-head CI, final independent review and merge remain pending. | — |
| pass | `Lane B #242 rebased392a4bbe local required gates` | test.py57/57 and pg_suites.py18/18 exit0, including registered_exit and e2e37. Independent run50/usage35 plus54 subtests and registered_exit PG also pass; these do not cover the blocking surrogate counterexample. | https://github.com/JTCAO515/G2C/pull/255 |
| fail | `Lane B #242 independent final review Unicode counterexample` | Actual @2 API accepts escaped lone surrogate; formal worker raises uncaught UnicodeEncodeError, provider0, original RUN remains running. Blocking review; JT stop instruction applies. No repair/consumer merge or later queue implementation performed. | https://github.com/JTCAO515/G2C/pull/255#issuecomment-6507373104 |
| pass | `B review-stop handoff render/check/diff-check` | B entry only; A/C text and historical verification retained. Generated HANDOFF matches JSON. Functional failure remains explicit. | — |

## Blockers

- L2/cloud/OTP/real model/device resources, branch protection and production keys remain JT-owned.
- Lane B #242: PR255 at392a4bbe has a reproducible independent blocking Unicode input-boundary finding; await JT resumption decision per current stop instruction. Pending repair is precise encoding failure mapping with actual API/worker regression, followed by affected/full required checks and fresh independent exact-head approval. Do not merge, close #242 or start #243/#13/#16/#14 while this stop applies. Migrations1–17, frozen contracts/RLS and other-lane ownership remain unchanged; no real resources or keys.

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

- Action: A: JT approved M2 queue/ownership and per-file locks on 2026-10-30 (docs/plan/issue-plan.md). After this M1 handoff + planning PR is locked-head merged and main CI green, check #242: if closed do #244, otherwise do #228 frames 1–3 using #226. #228 frame4 waits for C #227 current context freeze. Record a stop before changing parent; #21 App waits for B #13 PLACE freeze. #194/#159 await JT wording. Entire ios/** belongs to A. B: wait for JT instruction on the PR255 blocking review before repairing or resuming. Preserve392a4bbe and both PR histories; the next concrete action is to contain registered model-input Unicode serialization failure at its input boundary and add an actual API/worker regression, without masking internal errors or weakening validation. Then use fresh exact-head checks, independent APPROVE, locked merge and green main before closing #242/updating #9/notifying #244. Continue #243, then #13 PLACE, #16 FACT, #14 NEEDS only after the stop is lifted; new contracts/source decisions retain JT gates. C: #226 save/read is complete; next queue #227 (current cross-session consumption) then #228 (App memory). The requested C goal ends after #226; future work needs its own scope/ownership checks. A/C implementation status is retained for its owners; B producer readiness and closure are freshly verified here; current Issue/PR state takes precedence. One open PR per lane; shared files one PR at a time.
- Expected observation: A: #167 and #11 are closed with linked native23/23, exact-head independent APPROVE and green post-merge main. App reads original v2 persisted budget stages; failure/unknown never imply budget exhaustion or safe generation retry. Actual tools/models remain L2 #32, memory-version fence #17, M1 milestone open. C: #168/#169/#226 are closed with evidence; #12 remains open for #227/#228. No automatic recall/App completion is inferred from the server save/read slice. B: #242/#9 remain OPEN. Local57/18 and independent85+54subtests/registered PG PASS coexist with a reproduced Unicode boundary FAIL; no final consumer APPROVE/merge/main CI exists. A prerequisite is already satisfied, so it is no longer the B blocker. No fabricated business producer, fee, source recording or completion claim.
- Resume command: `# A completed: audit closed issues; M1 milestone stays open
gh issue view 167 --repo JTCAO515/G2C
gh issue view 11 --repo JTCAO515/G2C
gh issue view 242 --repo JTCAO515/G2C --comments
gh pr view 255 --repo JTCAO515/G2C --comments
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
