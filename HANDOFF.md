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
| Phase | M1 parallel lanes (ADR-0007 §2, JT approved 2026-10-28, lane table revised 2026-10-29): #196 merged; Lane A: M1/#167/#11 remain delivered. M2 planning/M1 handoff PR254 mergedbbbe864; JT efficiency ADR update PR278 merged670af5d. #228 frames1-3/5 delivered via PR289 headcb6d907 merged a889ec8; frame4 remains OPEN waiting C227 actual typed/travel consumption. #244 closed via PR294 head80a9ef8 merged87f5928, exact CI all six categories green/PG20, native registered logical12 plus retained @1 compatibility and current-main combination PASS. Remaining authorized A queue is temporarily blocked by C227 travel notice and B13/263 PLACE@1.0 freeze; #21 App UNRUN. Goal is not complete. B/C snapshots below are retained for their owners; live Issue/ADR0007 authority supersedes old approval wording. Lane B: #242 closed via PR259 and separate B handoff261, all exact-head review/CI and post-merge main green. #243 Part1 PR262 merged3caece7/main40964376354 green; frames1/2/4 PASS but business frame3 UNRUN, so243/9 OPEN and B remainder suspended. JT inserted B #273 under parent12 before13: travel identity/MESSAGE reference design r1 at PR275/head0faa438, not frozen or implemented; concrete DDL/down/RLS/grants require JT approval. Then return13->16->14; PLACE263-266 are planning only. Lane C: JT split delivery; #227 Part1 PR267 locked head2de7c674 merged e2d01529 with green main40972422603, AC1/3 backfilled; AC2/4 remain partial + child stops. #12 suspended for C. #17 native backend269 ->270, App271 A-owned; planning/design PR272 head3cc8323 locked-merged54cd5b3, postmerge main40978598661 pending at this snapshot. New edit/ACL/API design awaits JT specific approval, no implementation/migration executed. |
| Accepted Issue | Lane A: requested M2 queue docs ->244 ->228 ->21 App is partially delivered. Docs254/278 and244 are complete;228 is OPEN with four of five frames PASS,12 OPEN;21 App waits13/263 freeze. Entire ios/** A-owned; no unassigned271/286 work taken. #194/#159 wording is skipped per JT standing rule. No real services, model fees, cloud or physical device activated. Lane B: parent12 / #273 travel identity and MESSAGE reference, inserted by JT2026-10-30. Direction approved; specific contract, four-table DDL/receipt marker/eight restrictive policies and registry write scope await JT. No new implementation. Parent9/243 business remainder suspended; later13/16/14 retained. Lane C: #17/#269 design approval stop; backend269 then270, App271 A-owned. #227/#12 remain open, suspended C travel/lifecycle remainders. Do not wait for whole227/12 to start17; no new implementation before approved source/DDL/ACL/API scope. |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-30T05:56:50.234387+00:00 |

## Active Work

- Lane A: PR289 headcb6d907e04667fedcc572d37c4eeabbaf53c8bdb locked-mergeda889ec844ca828bac76baecee4cc0b7924266ca4; CI41001326191 + lint41001987151 all6 PASS/0 FAIL, PG20/20. Independent APPROVE5404a08 (review5707916485) carried through conflict-free rebase with21/21 byte-identical PR files under JT rule. Original UI13/13 at5404a08 plus4 real new-B-backend native combinations atcb6d907 PASS; Memory45/HTTP3/Shell213 independently PASS.228 frames1/2/3/5 checked;4 awaits C227 actual typed/travel integration, no cross-conversation substitute. PR294 head80a9ef82a24c10225eb4f4a58805ad375697ef7a locked-merged87f5928e2fee0380e1830a48feabe05cf348284b; exact CI41008734221/lint41008930563 all6 PASS/0 FAIL, PG20/20, ordinary test-only author selfcheck per new ADR. Registered @2 logical12 native cases PASS with explicit original heads (d75f189 nine,2d33bdb switch/Release,6e87b28 expiry), original @1 compatibility1 PASS and new-main @2 combination1 PASS. Original IDs/command/input/message/ledger fingerprints, actual401 admission +503/unknown protected read, real signed-token expiry, actual revocation/switch held reads, full AX and all-token/key/plaintext scans PASS.82 baseline assertion lines and23 original cases retained. All historical FAIL retained, no production App/backend/contract/migration/CI edits in244. #9 frames4/5 backfilled but9 remains OPEN for243 business remainder. L2/L3 registered32/29, UNRUN. Remaining A goal temporarily all blocked by C227 notification and B13/263 PLACE freeze; source checks and blocked comments recorded on228/21. Postmerge main CI not waited under JT rule; do not claim it PASS until read back.
- Lane B: #242 closed PR259/head42e3abb APPROVE6508547074, locked merged419d5a, main40956679529 five success; four L0/L1 frames/#9 mappings backfilled and A244 notified6508886939. B closure handoff261/head39467be APPROVE6509172708, merge7eb9b54/main40961533279 green. #243 Part1 PR262/headbd336aa APPROVE6509540461, merge3caece740433a559630e89900e51062742b5a845/main40964376354 green; exact test57/PG18 and independent registered PG pass, all51 prior assertions retained. Frames1/2/4 PASS; actual tool/background business frame3 UNRUN,243/9 OPEN. This child stop is recorded; no fake producer closes it. PLACE13 children263/264/265(B)/266(A) were created, no PLACE implementation or freeze; local unfinished draft retained. JT next inserted #273 under12 before13. Read C227 comments6507728939/6507885699/6507972794 and pinned3b1c0df proposal/typed files; C Part1 later maine2d is known conversation-only. B PR275/head0faa438 supplies detailed proposed TRAVEL-CONTEXT@1/MESSAGE-send2/ref/lease, explicitneeds reference, selection ABA epoch derived from immutable refs, four metadata tables plus receipt marker/compatibility RLS/up-down/minimal grants. Existing Meter/@1 reused; all new SQL and functionality UNRUN, not frozen. Storage-registry corresponding write scope also awaits JT; no C/ios/applied migration/actual permission changed.
- Lane C: historical #168/#169/#226 remain delivered with reviewed heads and green main; #12 is open. JT 2026-10-30 split #227: actual runtime Part1 now delivered via PR267 head2de7c674aa043291d09b6578447bbc8b3e9253a0, full local test57/PG19, memory_run9 @1/@2 signed API/runtime-role worker/CLI; independent redline APPROVE6510812133 plus B3 PG and4 additional actual worker combinations. Exact CI40969971693/lints green, locked mergee2d01529c80f135f44317476fec3e6c78b5897aa, postmerge main40972422603 five SUCCESS. Long-checkout PG socket exit1 and earlier no-tests command retained; same-head short full19 rerun PASS, no assertions weakened or tests deleted. #227 AC1/3 checked, AC2 travel context/typed DDL and AC4 full lifecycle are partial + stops; #12 suspended for C, not closed. Native #17 backend269 edit/enable ->270 old-result fence; App271 A owns, all parent7 frames mapped. PR272 head3cc8323117a6eecd11d452729cde6ee16ec9b587 adds C plan and concrete EDIT-ENABLE-DESIGN.md only, independent docs APPROVE6511510238, locked merge54cd5b3cd76e5c638621c17c31f5a477785b6d6f; postmerge main40978598661 pending at handoff snapshot. New source approval/history, paused-version anchor, proposed up/down, management FORCE RLS/item column grants and specified B API activation need JT approval (question pending); no new SQL executed or closed factory bypassed. Only existing schema constraint names were queried in empty private PG; that cluster stopped. #270 stop-use writer needs its own detailed approval, never physical cleanup/#26 completion. Entire ios/CJMemoryClient/CJTripClient and271/228 A-owned. Further C queue18 FEASIBILITY draft/JT freeze then22 backend remains; #18/#22 not started.
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
| `docs/handoff.json, HANDOFF.md` | C-only #227 runtime evidence and cross-travel owner-freeze stop; A/B status text/history retained. B257 closed without merge, freeing this handoff pair; B258 owns runtime coordination files. |
| `docs/handoff.json, HANDOFF.md` | B inserted273 detailed contract/DDL approval stop;243 partial/real-producer hold and later13/16/14 preserved; only B fields, retain A/C/history. |
| `docs/handoff.json, HANDOFF.md` | C-only transition from split227 Part1 delivery to17/269 concrete design stop; retain A/B prefixes, status and history. |
| `docs/handoff.json, HANDOFF.md` | A-only goal-level M2 delivery/dependency-block snapshot under JT efficiency rule; preserve B/C text, all prior verification and historical FAIL. No extra handoff per ticket. |

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
| pending | `[Historical at969b3e8] Lane B #242 consumer post-A merge gate` | Wait for #167 merge and green main, then rebase/new-head verification and independent final APPROVE. Consumer not merged; #242/#9 remain open. Historical prior waiting state; now superseded by PR259 closure evidence below. | https://github.com/JTCAO515/G2C/issues/242#issuecomment-6504795674 |
| pass | `Lane A #167 matrix04 on #249 backend baseline` | Actual cac619a/basebeb05b5: 23/23 native, each xcresult1/0/0; RUN57/Shell213/Debug/Python57/PG17. Canonical ledger/original recovery, actual operator and worker CLI, cross-account, AX all and scans independently verified. Later71e4cab differs only in inherited handoff; original report head unchanged. | https://github.com/JTCAO515/G2C/pull/253#issuecomment-6506103720 |
| pass | `Lane A #167 PR253 exact-head review and locked merge` | Head71e4caba full CI40936684595 and lint40938671881 success, independent APPROVE6506103720, locked merge1f960a1. Fifteen actual native screenshots attached to PR. | https://github.com/JTCAO515/G2C/pull/253 |
| pass | `Lane A #167 post-merge main CI40938740022 and parent closure` | All five main jobs success at1f960a1; #167 three frames and parent#11 seven frames linked to evidence and closed. #165/#166 remain closed; L2 #32 and memory fence #17 retained. M1 milestone remains open for JT. | https://github.com/JTCAO515/G2C/actions/runs/40938740022 |
| pass | `A closeout: python3 -B scripts/handoff.py render; check; git diff --check` | A-only allowed handoff fields and generated Markdown; B/C text and all previous verification entries preserved. No executable changes. | — |
| pass | `A M2 planning + M1 closeout: handoff render/check and git diff --check` | Three documentation files only; JT approved M2 lane ownership, queues and per-file locks on 2026-10-30. Open PR251 file list has no overlap with docs/plan/** or the handoff pair. New-head CI, final independent review and merge remain pending. | — |
| pass | `C #227 product head6a69183 full local gates` | test.py57/57 and pg_suites.py18/18 exit0. Includes B baseline groups plus new memory_run7/7, signed API/runtime-role PG/actual run_once and CLI new process/FakeProvider/metered exit. Later candidate3b1c0df changes only proposal docs. Does not prove cross-travel or complete #17 lifecycle integration. | https://github.com/JTCAO515/G2C/issues/227#issuecomment-6507885699 |
| not-run | `C #227 travel-context/typed-memory/new migration and full closure` | Lease/cross-lane design directions approved; C typed wire/DDL proposal6507972794 ready. B producer/lease and reference keys not frozen; no new typed implementation or migrations executed. Remote feature CI/independent final APPROVE/locked merge/postmerge CI UNRUN; no issue closure. | https://github.com/JTCAO515/G2C/issues/227#issuecomment-6507972794 |
| fail | `[Historical] B #242 PR255 Unicode counterexample at392a4bbe` | Actual private PG accepted escaped surrogate, formal run_once raised UnicodeEncodeError, provider0 and RUN remained running. Original blocking result retained; later fixed, not rewritten as PASS. | https://github.com/JTCAO515/G2C/pull/255#issuecomment-6507373104 |
| fail | `[Historical] B #242 PR258 wrong wire assertion at0bd3a2c` | Independent registered PG exited1 because the new test expected None instead of frozen string none; CLI encoding recovery had succeeded. Exact assertion corrected at4c5c2cc without changing product wire. | https://github.com/JTCAO515/G2C/pull/258#issuecomment-6508018586 |
| pending | `[Historical] B #242 interrupted old-head gates at0bd3a2c` | Author full PG intentionally interrupted exit130 and private server stop confirmed; CI40952243785 cancelled. This old run never completed and is not PASS. New exact-head full gates completed separately. | https://github.com/JTCAO515/G2C/pull/258 |
| pass | `B #242 PR259 exact head42e3abb43b745f7bb801c5a435b71e5c293776c8` | test57/57, complete PG18/18 including e2e37 and registered Unicode CLI regression; exact-head full CI and independent red-line APPROVE. All four L0/L1 frames PASS; historical FAIL/interruption evidence retained. | https://github.com/JTCAO515/G2C/pull/259#issuecomment-6508547074 |
| pass | `B #242 PR259 exact-head CI` | Five CI jobs and required PR lint success on 42e3abb43b745f7bb801c5a435b71e5c293776c8. | https://github.com/JTCAO515/G2C/actions/runs/40954637859 |
| pass | `B #242 post-merge main CI` | Locked-head merged419d5af45a67fe5b30220bb662ca3f3e61cafb4; all five main jobs success. #242 closed, #9 mapping and A #244 notification backfilled. | https://github.com/JTCAO515/G2C/actions/runs/40956679529 |
| pass | `B #242 closure handoff render/check/diff-check` | Only B entries plus timestamp and generated HANDOFF; A/C and historical evidence retained. | — |
| pass | `C #227 Part1 PR267 exact head/local/independent/remote and postmerge main` | 2de7c674: local test57/PG19 (memory_run9), independent test57/memory_run9/B3 PG and4 supplement worker combinations; CI40969971693/lint all SUCCESS, APPROVE6510812133, locked mergee2d01529, main40972422603 all5 SUCCESS. AC1/3 checked; AC2/4 partial child stops. | https://github.com/JTCAO515/G2C/pull/267#issuecomment-6510812133 |
| pass | `C #17 native split and proposed edit/activation design` | 269/270/271 linked as native children of17;270/271 blocked_by269; all7 parent frames retained/mapped. PR2723cc8323 static diff/metadata and independent docs APPROVE6511510238, all headCI passed, locked merge54cd5b3. New SQL not executed, no grants/API/source implementation. | https://github.com/JTCAO515/G2C/pull/272#issuecomment-6511510238 |
| pending | `C #17 PR272 postmerge main40978598661` | Running at this handoff snapshot; query the exact live run and Issue269 before proceeding, do not restart on observation timeout or infer PASS. | https://github.com/JTCAO515/G2C/actions/runs/40978598661 |
| not-run | `C #269/#270 implementation, typed travel migration, App and further queue` | New edit/source/ACL/API and future stop-use writer await specific JT approval; typed travel awaits B freeze/DDL approval. All new abilities UNRUN. No real model/external service/device/deployment;18/22 not started. | https://github.com/JTCAO515/G2C/issues/269#issuecomment-6511462512 |
| pass | `B #243 Part1 exact headbd336aa and post-merge main` | test57/PG18 + independent registered PG; exact CI40961999127/lint40962857168, final APPROVE6509540461, locked merge3caece7 and main40964376354 five success. Frames1/2/4 backfilled, business3 UNRUN and243/9 OPEN. | https://github.com/JTCAO515/G2C/pull/262#issuecomment-6509540461 |
| pass | `B #273 native split and detailed proposal` | B273 native child12, five graded frames unchecked; plan inserts273 before13 and records existing PLACE263-266. JSON syntax/links/up-down object-name accounting and diff check only; these are document checks, not new functional acceptance. | https://github.com/JTCAO515/G2C/issues/273 |
| pending | `B #273 contract/DDL/permissions/runtime` | Specific freeze and approval required. New SQL never executed; no applied migration/permission/runtime/C/ios changes. New contract validator, DDL syntax/up/down, RLS/old-consumer/currentness/locks and C/A actual integration UNRUN. | https://github.com/JTCAO515/G2C/pull/275 |
| pass | `B #273 DRAFT document delivery only / PR275` | Exact head0faa438a5389151735a720d5f08860faaa22ebc4 CI40982433354 five jobs and latest lint40984090044 success; independent docs-only APPROVE6512457047, locked mergec9f77d1c4ea9d62659242fd6da3a0df1bb178faf. Approval is only draft-document entry, not JT freeze/DDL/permission/registry scope. All new behavior and SQL checks remain UNRUN; postmerge main40984501081 must be read back separately before closing this handoff gate. | https://github.com/JTCAO515/G2C/pull/275#issuecomment-6512457047 |
| pass | `A JT2026-10-30 M2 planning and efficiency authorization` | PR254 mergedbbbe864 with original independent approval/CI; later explicitly authorized ADR efficiency PR278 exact839cc7d CI6/6 locked-merged670af5d. No workflow or test gate weakened beyond JT stated process revision. | https://github.com/JTCAO515/G2C/pull/278 |
| pass | `A #228 ready save/read/recovery slice / PR289` | Source-equivalent independent APPROVE carried across21 byte-identical files; exact cb6d907 CI6/6 and defaultPG20, originalUI13 plus actual newbackend4 native PASS with original heads retained; locked mergea889ec8. Frames1/2/3/5 checked,4 UNRUN;228/12 OPEN. All historical FAIL retained. | https://github.com/JTCAO515/G2C/pull/289 |
| pass | `A #244 registered App consumption / PR294` | Exact80a9ef8 allCI6/6 + PG20, author test-only check; locked merge87f5928. Logical native@2 matrix12 PASS with explicit heads, @1compat1 and current-main1 PASS; no quota/429 injection, actual auth401/protected503unknown, original fingerprints and full AX/scans. Baseline82 assertion lines/23 cases retained;244 CLOSED,9 OPEN. L2/L3 UNRUN registered32/29. | https://github.com/JTCAO515/G2C/pull/294 |
| pending | `A remaining #228 frame4 and #21 App` | #227 actual typed/travel consumer notification and #13/#263 PLACE@1.0 freeze absent at snapshot. Only remaining authorized A goal scope; no new functional implementation or PASS claimed. Recheck live notices; goal not complete. | https://github.com/JTCAO515/G2C/issues/228#issuecomment-6516049704 |

## Blockers

- L2/cloud/OTP/real model/device resources, branch protection and production keys remain JT-owned.
- Lane C #269: await JT specific implementation approval of EDIT-ENABLE-DESIGN.md (PR272/3cc8323): new exact-edit-source/history/paused anchor, proposed migration/up/down and RLS/column grants, named B management API local files. No new DDL/API activation before approval. #270 full lifecycle/withdrawal writer needs separate design/approval. #227 AC2 waits B travel-context/MESSAGE/lease freeze and typed DDL approval; AC4 waits269/270. These are child stops, #12 suspended; do not turn them into a whole-line travel-context wait.
- Lane B #243: only actual tool/background producer frame3 remains UNRUN, integrated by corresponding feature slices13/16/23;227 is structured-memory consumption, not a background producer.243/9 remain OPEN; no entire-parent dependency or fake callback substitutes for actual integration.
- Lane B #273: direction is already JT-approved, but PR275/head0faa438 detailed contract and specific DDL/down/RLS/grants need explicit freeze/approval before any implementation or private-PG DDL execution. Proposed4 tables, nullable receipt marker,8 restrictive MESSAGE/RUN gates and corresponding registry write scope are not authorized by direction alone. C typed implementation/DDL and A clients remain their owners; new memory/travel behavior cannot be claimed from legacy conversation tests.
- Lane A goal remaining: #228 frame4 waits C #227 actual travel/typed-memory notification after B273 MESSAGE2/real lease delivery; lifecycle-only227 frame4 PASS is not that travel integration. #21 App waits B #13/#263 fixed PLACE@1.0 with examples/consumer surface; old CJ-PLACE-GAODE candidate is not substitute. Both are dependency stops, not new JT approval requests; no other authorized A queue item is ready. #244 CLOSED; #228/#12/#21 remain OPEN. Recheck notices before resuming; do not invent fields or start unassigned271/286.

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

- Action: A: docs254/278 and244 delivered;228 frames1-3/5 delivered, frame4 awaits C227 actual typed/travel consumer notice; next21 App awaits B13/263 PLACE@1.0 freeze. Recheck those live issues/notifications; when ready resume only the authorized queue, use existing signed local API/private PG/formal run_once/explicit profiles/FakeProvider, preserve raw IDs/UNKNOWN and all FAIL. No new approval needed for the JT standing local scope; sensitive external/key/cloud/destructive/test-weakening boundaries remain. Entire line currently dependency-blocked and goal not complete; this is the one goal-level A handoff. Old B/C approval prose is their historical snapshot; use live Issue and latest ADR0007. B: wait for JT specific decision on #273 detailed PR275/head0faa438 (direction not re-requested): freeze TRAVEL/MESSAGE2/ref/lease, approve concrete up/down/limited RLS/grants and registry entry write scope. Do not execute new SQL even in private PG or modify runtime before approval. Once approved, compatible consumer first, producer activation second, actual restricted PG/API/worker/Fake tests and exact-head CI/independent redline APPROVE/locked merge/main green; then notify227/228 with frozen keys and delivery head. Parent12 is not closed by B alone. Return13->16->14 afterward; those need their own drafts/source decisions, no live APIs/fees/keys. C: finish PR272 postmerge main40978598661 and this separate C-only handoff exact-head CI/independent APPROVE/locked merge/main green. Wait for JT response to269 design comment6511462512; if approved, fetch latest main/manifest, recheck per-file locks and declare coordinator functions on269 and B current ticket, implement only approved new source/DDL/ACL/API scope with full real runtime-role PG and redline gates. Otherwise preserve design stop without implementing. After269 do270 fence and backfill227 AC4; when B freezes travel context revisit227 AC2, obtain concrete typed DDL approval first. App271/228 A; original12 closes only after227 and228 both close. #18 contract/JT freeze/PLACE-NEEDS gates and #22 backend follow; no real services/keys.
- Expected observation: A:244 CLOSED with three L1 frames PASS and L2/L3 deferred/registered32/29;228 four L1 frames checked and4 OPEN,12 OPEN;21 App UNRUN for PLACE freeze. Actual evidence keeps original heads and separates UI13, new-backend4, registered logical12, @1compat1 and current-main1; no real provider/fees/device or deployment PASS. C: #168/#169/#226 are closed with evidence; #12 remains open for #227/#228. No automatic recall/App completion is inferred from the server save/read slice. B: #242 CLOSED;243 component frames1/2/4 PASS, business frame3 UNRUN and243/9 OPEN. New273 exists under12 with five unchecked L0/L1 frames; only proposal/static document checks performed. Contract freeze, DDL syntax/up/down/RLS/runtime/new consumers all UNRUN. Proposed keys are not permissions; MESSAGE-send1 and old memory/applied migrations unchanged.13 children planned, PLACE/FACT/NEEDS implementations not claimed.
- Resume command: `# A remaining goal: read live notices; do not replace missing frozen producers
gh issue view 228 --repo JTCAO515/G2C --comments
gh issue view 227 --repo JTCAO515/G2C --comments
gh issue view 263 --repo JTCAO515/G2C --comments
gh issue view 244 --repo JTCAO515/G2C
# B/C historical snapshot commands retained below; live Issue + latest ADR prevail
# C next queue (outside this completed requested slice)
gh issue view 227 --repo JTCAO515/G2C
# B current inserted ticket, implementation stopped for concrete approval
gh issue view 273 --repo JTCAO515/G2C --comments
gh pr view 275 --repo JTCAO515/G2C --comments`

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
