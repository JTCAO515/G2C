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
| Phase | M1 parallel lanes (ADR-0007 §2, JT approved 2026-10-28, lane table revised 2026-10-29): #196 merged; Lane A: M2唯一A承接线程；不恢复OldA并行写入。#337/#25由PR367/370/384收口，#286/#22/#373由PR371/372/376/377收口，均CLOSED。PR384锁head711573ef84e949267f17de9653e4482351d4b9ec合main e79f99f6a7c9a12c1e24520e92474a4ff98fc758，精确CI41294067734五job/最终lint全SUCCESS、独立APPROVE6556237870。新增当前五类App原生5PASS/0FAIL/0SKIP，含原结果中英、跨日重选新send4/接受/旧stale、Memory撤回后新模型排除旧偏好及拒绝重启、真实A200迟到B；全AX/扫描/私有PG停止PASS。旧正常候选九类、手动/重新规划候选层和正式main组合逐head保留，所有历史FAIL/UNKNOWN/UNRUN不改。M2实时只剩#21 OPEN：已交浏览/时间线/PLACE/讨论绑定，综合地图框未完成；JT原指令暂缓授权、地图保持UNRUN，不接Key或真实服务、不重复请求同一授权。当前无其他独立A实现项；M2/goal未完成，真实服务/费用/云/生产/设备按32/29。以下B/C为各owner历史快照，实时Issue/最新ADR优先。 Lane B: JT本轮354/360及追加source2 378全部L0/L1已交付关闭：PR359锁head490ecaf合ae417da6，source1 needs-structured.1；PR379锁19332a15合35fb4b3f冻结publisher@2/L0，PR380锁37b95f0f合c138fced交M29/同cursor结果运行；PR382锁2bb54fed合2d0a1011交needs-current-trip.1/source2。各精确head六类CI SUCCESS；source2含C M30实际合并树验收PASS。B实际签名API/受限PG/未patchrun_once+CLI/Fake/Meter、原bytes及owner/currentness/cancel/UNKNOWN均有证据；C函数/lease桥接不是C生产代证，C381/M30与336已由C交付。原clock P1已修且独审放行，原FAIL保留；schema跨字段P2保留，315本轮未投入。全部业务/共享锁已释放，通知已发，不等main CI/回执，当前仅本次B-only结束交接；A/C的M2/App及真实资源按各owner验收，不宣称全M2完成。 Lane C: 当前goal是与A/B协作直至M2里程碑收口，不是只完成旧227/17/18/22四票；旧goal已独立完成的证据保留，不能据此把M2标complete。C优先366已由PR368 final head853bea89ed4c0b0f8a197df8fa4c20ae4383bb08锁合196d38dbcd9721b057001255b226f95de2466484，精确CI41235845596全绿、独立新head APPROVE6548301786（原dbd0红线6548045808，12/12 blob和完整binary diff相同的无冲突普通main整合）。TRIP-scoped-discovery.1新GET原message_id/run_id→完整原reference/源当前原候选与diff，原Signer/act/回执保持；实际签名API/受限PG/原run_once/Meter/Fake/生产C publisher，21/123/5/10及test58通过，业务DML0/模型计量不增。A337/336/25已通知6548650385/6548650714/6548651029，366四框PASS/CLOSED。原8ERROR/两fixtureFAIL、旧独审环境ERROR保留；P2 metadata注释措辞随336阶段二整合，无候选原事实不授当前NEEDS/Memory许可。M2仍有21/22/25/286/336/337/354/360八张OPEN；C336框2/4阶段二需B360在336给L0追加publisher冻结，当前未收到，C不猜接口。B354/PR359 head9917e325 CI六类SUCCESS但OPEN，A286正式创建组合仍待B；A337新发现/diff/接受刚获C版本，真实UI未计PASS。C暂无其他独立M2后端项，等待实际B L0或A/B转来的C真实联调缺口，恢复即接，不等360整票关闭。不代做A/B、不把本线暂交当M2完成。main6bc15f2已绿；新196d38d mainCI运行中按ADR不预记绿，收口实时核验。App完整组合/阶段二、真实模型API/费用/云/生产/设备UNRUN，L2/L3按32/29。 |
| Accepted Issue | Lane A: JT持续授权全部M2 App；整个ios/**与docs/ui.md归A。337/25、286/22/373和既有244/271/266/228已按L0/L1关闭，21仅地图综合余项OPEN。正式B/C结果与source2已经组合，不再等待旧285/330/354/360停点。地图依JT暂缓UNRUN；不把未实现地图App转记成L1完成，不重开OldA或抢写后端；194/159跳过，329/332非本M2队列。真实资源/设备转32/29，M2/goal未完成。 Lane B: 本轮354、360、378均CLOSED，359/379/380/382均精确head CI全绿锁合；已通知286/373/21/22/336/337/25。默认legacy、source1和旧publisher/冻结版本保持，source2独立真实组合不由source1/scoped替代。B不改C/iOS、已应用迁移或弱化测试；仅追加本地M29，C后续M30已交。B旧343/327及更早交付和FAIL均留历史verification，本次JT指派无需逐项审批。B本轮交付与结束交接完结，具体B接口缺口继续按现授权响应；真实资源/设备证据仍不冒称。 Lane C: 当前goal是与A/B协作直至M2里程碑收口，不是只完成旧227/17/18/22四票；旧goal已独立完成的证据保留，不能据此把M2标complete。C优先366已由PR368 final head853bea89ed4c0b0f8a197df8fa4c20ae4383bb08锁合196d38dbcd9721b057001255b226f95de2466484，精确CI41235845596全绿、独立新head APPROVE6548301786（原dbd0红线6548045808，12/12 blob和完整binary diff相同的无冲突普通main整合）。TRIP-scoped-discovery.1新GET原message_id/run_id→完整原reference/源当前原候选与diff，原Signer/act/回执保持；实际签名API/受限PG/原run_once/Meter/Fake/生产C publisher，21/123/5/10及test58通过，业务DML0/模型计量不增。A337/336/25已通知6548650385/6548650714/6548651029，366四框PASS/CLOSED。原8ERROR/两fixtureFAIL、旧独审环境ERROR保留；P2 metadata注释措辞随336阶段二整合，无候选原事实不授当前NEEDS/Memory许可。M2仍有21/22/25/286/336/337/354/360八张OPEN；C336框2/4阶段二需B360在336给L0追加publisher冻结，当前未收到，C不猜接口。B354/PR359 head9917e325 CI六类SUCCESS但OPEN，A286正式创建组合仍待B；A337新发现/diff/接受刚获C版本，真实UI未计PASS。C暂无其他独立M2后端项，等待实际B L0或A/B转来的C真实联调缺口，恢复即接，不等360整票关闭。不代做A/B、不把本线暂交当M2完成。main6bc15f2已绿；新196d38d mainCI运行中按ADR不预记绿，收口实时核验。App完整组合/阶段二、真实模型API/费用/云/生产/设备UNRUN，L2/L3按32/29。 |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-11-01T10:08:03Z |

## Active Work

- Lane A: M2唯一A承接线程；不恢复OldA并行写入。#337/#25由PR367/370/384收口，#286/#22/#373由PR371/372/376/377收口，均CLOSED。PR384锁head711573ef84e949267f17de9653e4482351d4b9ec合main e79f99f6a7c9a12c1e24520e92474a4ff98fc758，精确CI41294067734五job/最终lint全SUCCESS、独立APPROVE6556237870。新增当前五类App原生5PASS/0FAIL/0SKIP，含原结果中英、跨日重选新send4/接受/旧stale、Memory撤回后新模型排除旧偏好及拒绝重启、真实A200迟到B；全AX/扫描/私有PG停止PASS。旧正常候选九类、手动/重新规划候选层和正式main组合逐head保留，所有历史FAIL/UNKNOWN/UNRUN不改。M2实时只剩#21 OPEN：已交浏览/时间线/PLACE/讨论绑定，综合地图框未完成；JT原指令暂缓授权、地图保持UNRUN，不接Key或真实服务、不重复请求同一授权。当前无其他独立A实现项；M2/goal未完成，真实服务/费用/云/生产/设备按32/29。以下B/C为各owner历史快照，实时Issue/最新ADR优先。
- Lane B: JT本轮354/360及追加source2 378全部L0/L1已交付关闭：PR359锁head490ecaf合ae417da6，source1 needs-structured.1；PR379锁19332a15合35fb4b3f冻结publisher@2/L0，PR380锁37b95f0f合c138fced交M29/同cursor结果运行；PR382锁2bb54fed合2d0a1011交needs-current-trip.1/source2。各精确head六类CI SUCCESS；source2含C M30实际合并树验收PASS。B实际签名API/受限PG/未patchrun_once+CLI/Fake/Meter、原bytes及owner/currentness/cancel/UNKNOWN均有证据；C函数/lease桥接不是C生产代证，C381/M30与336已由C交付。原clock P1已修且独审放行，原FAIL保留；schema跨字段P2保留，315本轮未投入。全部业务/共享锁已释放，通知已发，不等main CI/回执，当前仅本次B-only结束交接；A/C的M2/App及真实资源按各owner验收，不宣称全M2完成。 全部原始FAIL与旧快照留在历史verification；新JT指派与实时Issue优先于旧handoff。
- Lane C: 当前goal是与A/B协作直至M2里程碑收口，不是只完成旧227/17/18/22四票；旧goal已独立完成的证据保留，不能据此把M2标complete。C优先366已由PR368 final head853bea89ed4c0b0f8a197df8fa4c20ae4383bb08锁合196d38dbcd9721b057001255b226f95de2466484，精确CI41235845596全绿、独立新head APPROVE6548301786（原dbd0红线6548045808，12/12 blob和完整binary diff相同的无冲突普通main整合）。TRIP-scoped-discovery.1新GET原message_id/run_id→完整原reference/源当前原候选与diff，原Signer/act/回执保持；实际签名API/受限PG/原run_once/Meter/Fake/生产C publisher，21/123/5/10及test58通过，业务DML0/模型计量不增。A337/336/25已通知6548650385/6548650714/6548651029，366四框PASS/CLOSED。原8ERROR/两fixtureFAIL、旧独审环境ERROR保留；P2 metadata注释措辞随336阶段二整合，无候选原事实不授当前NEEDS/Memory许可。M2仍有21/22/25/286/336/337/354/360八张OPEN；C336框2/4阶段二需B360在336给L0追加publisher冻结，当前未收到，C不猜接口。B354/PR359 head9917e325 CI六类SUCCESS但OPEN，A286正式创建组合仍待B；A337新发现/diff/接受刚获C版本，真实UI未计PASS。C暂无其他独立M2后端项，等待实际B L0或A/B转来的C真实联调缺口，恢复即接，不等360整票关闭。不代做A/B、不把本线暂交当M2完成。main6bc15f2已绿；新196d38d mainCI运行中按ADR不预记绿，收口实时核验。App完整组合/阶段二、真实模型API/费用/云/生产/设备UNRUN，L2/L3按32/29。
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
| `docs/plan/issue-plan.md, docs/handoff.json, HANDOFF.md` | C-only native18/22 child structure and whole-line shared/owner stop after269/270/core280 delivery; preserve all A/B entries and old evidence. |
| `docs/plan/issue-plan.md, docs/handoff.json, HANDOFF.md` | C-only whole-line prerequisite snapshot after227, structured Trip/manual, formal read projection and source byte-budget delivery; preserve all A/B strings, original verification and FAIL. |
| `docs/handoff.json, HANDOFF.md, docs/plan/issue-plan.md` | One final B-only goal closeout and native child/queue mapping; retain every A/C snapshot, historical verification and failure. No executable change. |
| `docs/handoff.json, HANDOFF.md` | 仅A线Goal级交接：实时交付/证据及21/285/330依赖；保留B/C条目和全部历史FAIL，不把旧快照当当前事实。 |
| `docs/plan/issue-plan.md, docs/handoff.json, HANDOFF.md, backend/memory/TRIP-MESSAGE-ADAPTER-DESIGN.md` | C-only final scope/owner/real-producer stop plus25 child split; preserve A/B text and historical verification. No executable change. |
| `docs/handoff.json, HANDOFF.md, docs/plan/issue-plan.md` | Lane B 2026-10-31 final goal closeout: 330/315 investigation delivery and JT-approved 243 background-to-M3 transfer; only B-owned snapshot/plan portions, A/C and historical FAIL preserved. |
| `docs/handoff.json, HANDOFF.md, docs/plan/issue-plan.md` | Lane B343 final goal: producer/runtime and327 closure, M2 child milestones and consumer handoff; only B snapshot/mapping, preserveA/C and every historicalFAIL. |
| `docs/handoff.json, HANDOFF.md, docs/plan/issue-plan.md` | C-only actual interface stop after344 and336 Part1; preserve every A/B value and previous verification. No executable change. |
| `docs/handoff.json, HANDOFF.md, docs/plan/issue-plan.md` | C-only whole-line B360 L0 prerequisite after phase1 PR358 and priority source initialization361/362; preserve A/B strings and every historical verification. |
| `docs/handoff.json, HANDOFF.md, docs/plan/issue-plan.md` | C-only original goal closeout audit requested by JT: separate227/17/18/22 backend completion from later25/336 queue and A App; preserve A/B and every prior verification/failure. |
| `docs/handoff.json, HANDOFF.md, docs/plan/issue-plan.md` | C-only M2 whole-line actual external prerequisite after366, preserving old completed-goal evidence and A/B; M2 goal is not complete. |
| `docs/handoff.json, HANDOFF.md, docs/plan/issue-plan.md` | B-only final goal closeout for354/360/378 after359/379/380/382; preserve every A/C value and historical verification/FAIL. No executable change. |
| `docs/handoff.json, HANDOFF.md, docs/plan/issue-plan.md` | 一次A-only M2整线剩余地图暂缓交接；仅A当前快照/队列与证据，保留每一B/C值及历史FAIL。无可执行代码改动。 |

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
| pass | `C #269 / PR290 exact-head backend delivery` | head5d6a85be test57/defaultPG20/memory_run14 + CI41004578608 and lint41005826132 SUCCESS; independent APPROVE6515225732, locked merge278c9201, CLOSED. Exact JT-approved B assertion only; six other refusal checks preserved. Old279 FAIL retained. | https://github.com/JTCAO515/G2C/pull/290#issuecomment-6515225732 |
| pass | `C #270 / PR292 stop-use and final publication fences` | headb3642484 test57/defaultPG20/memory_run25 + CI41006417147/lint41007913999 SUCCESS; independent APPROVE6515464822, locked merge5c526ea1, CLOSED,227 AC4 backfilled. Real writer and actual worker/draft both lock orders; no physical cleanup or CJ020 completion. | https://github.com/JTCAO515/G2C/pull/292#issuecomment-6515464822 |
| pass | `C #18 core280 / PR282 FEASIBILITY@1.0` | head6fc1cd00 local57/feas119+22 subtests,15 existing opt-in skips; exact CI40998112655/lint40999352974, lockede652453e, main40999386836 SUCCESS.280 CLOSED; formal281/parent18 remain OPEN, not real route acceptance. | https://github.com/JTCAO515/G2C/pull/282 |
| unrun | `C227 typed preparation4465d7a / final integration pending` | Preparation only: author syntax2/typed actualPG9/legacy25/nonPG58 PASS, private1..21 up/down/up PASS; independent3f30d4b9/25/empty21 PASS/noP0P1, P2 translation fixed. Final B299 tools rebase/API-gen/default typed group/full current-head PG/CI/review/merge UNRUN. B299 failed CI owns required files; no bypass or overlap PR. | https://github.com/JTCAO515/G2C/tree/4465d7a00b72a8281bcf8445d4b6963314b60ca9 |
| PASS | `C227 final typed PR307 + descendant main` | 5c1071c7:58/23 typed10, exact CI41036315055+APPROVE6519883016, merge56df1394; all227 frames checked+CLOSED, A228 notified6520253789. Descendant main37dbe880 CI41040047684 green;56 main cancelled, not PASS. | https://github.com/JTCAO515/G2C/pull/307 |
| PASS | `C Trip structured/manual/initialize/origin PR311` | e8f40441:58/24, actual signed MESSAGE/worker/Fake/root acceptance/init/manual7, migrations1..22 roundtrip39tables/nonemptydown/RLS. CI41045669402+APPROVE6521237676, merge14065019. P1 b26 withdrawn and fixed before merge; old23/24 hardcoded21 FAIL retained and C assertion strengthened, no B edits. | https://github.com/JTCAO515/G2C/pull/311 |
| PASS | `C formal FEAS data/current read PR314 exact head` | 1ee3eb7b:nonPG58, exact CI41049584175 all green+APPROVE6521766557, merge193d51dc. Independent component46+12subtests/8 owner-PG probes,15 old opt-in skips retained; original output bytes equal. Local full23/24 FAIL atB registered_exit340 kept; fresh samehead targeted1/1 PASS. Actual signed runtime/writer publication UNRUN -> B305; no false L1/complete281. | https://github.com/JTCAO515/G2C/pull/314 |
| PASS | `C source raw byte budget PR316` | b5fe757f:Trip104/manual8 exact-limit and one-byte-over actual PG PASS; CI41054394556 all green, locked merge70265358d0e8a560bd9b6b307b2d1e051c08997c.312 CLOSED. Counts intent and original MESSAGE bytes in the same budget; no schema/permission/wire/lease changes. | https://github.com/JTCAO515/G2C/pull/316 |
| UNRUN | `C remaining NEEDS-bound runtime/Trip integration, App and real resources` | 281 runtime/signed API/restricted-role/writer-publication +204/285 real source/actual planning remain blocked by B305 afterB306; data contracts already frozen. App A, real services/model/cloud/keys/fees/device not run; Goal not complete. | https://github.com/JTCAO515/G2C/issues/305 |
| PASS | `B265 PR299 regression fix` | f06de27 test57/57/defaultPG22/22, original299/303/323 assertions byte-identical; exact CI41030333266/lint41032821160 green, independent increment APPROVE6519039311, locked merge729f6637. | https://github.com/JTCAO515/G2C/pull/299 |
| PASS | `B303 NEEDS@1.0 codec freeze` | 86dc873 codec/domain49/49, NEEDS PG78, exact CI41033663493/lint41033663627 green; ordinary-code selfcheck, locked merge9a005683. Old candidate/HTTP/frozen versions retained. | https://github.com/JTCAO515/G2C/pull/304 |
| PASS | `B306 actual synthetic FACT registered host` | 809c894 test58/58/defaultPG25/25 plus independent codec9/related59/actualPG+CLI; exact CI41059860360/lint41059957805 green, APPROVE6523484173, locked merge4c7a5acb. Actual step/tool/output/time/admission/cancel/unknown original exposure and no redispatch, data all synthetic. | https://github.com/JTCAO515/G2C/pull/318 |
| PASS | `B305 formal NEEDS manual/preview/runtime` | 7cfe484 test58/58; be975 defaultPG26/26 and targeted unchanged-part reuse plus68ad currency tests89/independent11;23/23 reviewed files byte-identical into7cfe. Exact CI41064144370/lint41064144265 all green, APPROVE6524088648, locked merge5321c30e. Native MIG1..23 roundtrip/minACL/old ABI refusals/cross-owner/ACK/CAS/real publication lock orders and worker CLI PASS. | https://github.com/JTCAO515/G2C/pull/319 |
| FAIL | `B historical failures retained` | Historical, superseded:299 old registry-bound assertion failure reproduced; local source/CLI preparation and preview regex/ACK-injection/request-fixture errors;0023 initial legacy UPDATE and down error-class failures fixed in new migration/ABI path without changing old assertions. Wrong uncommitted context_id-slash fixture withdrawn after frozen32hex grammar verification; original legal action_id slash PG passes. Cross-package pytest duplicate-name collection fixed by existing per-package commands, no test exclusion. | https://github.com/JTCAO515/G2C/pull/319 |
| UNRUN | `B remaining external/App/consumer acceptance` | A266/320/321 native UI; C281/204/285 full FEAS/planning and background23; real providers/collection/LLM/keys/accounts/cloud/fees/device/production not run. Parent progress does not close those owner/resource gates. | https://github.com/JTCAO515/G2C/issues/32 |
| pass | `Lane A PR313/308/328 delivered App slices` | 271/17原生7/0；21独立浏览3/0；266/13与PLACE9/0。精确CI/适用独立审查和锁head已完成；fca main41113555625实际五job绿。原313 merge run取消，不称PASS；真实服务/设备未跑。 | https://github.com/JTCAO515/G2C/pull/328 |
| pass | `Lane A PR331 exact-head native/CI/review/closure` | head4f2ec992锁合并34305250，228/12已关；原生8/0/0、10 MESSAGE/10正式Fake worker调用；L0 564/0及1既有可选SKIP；CI6类全SUCCESS，独立APPROVE6536273412。P1反向旧writer绕过已修复真实验收；P2 #332后续；索引02 SHA256 4f0c02d7c1425ef05949ddb0dd0617d46bbe7f3f2abc60fc7f38f414c7ead183。15场历史FAIL保留，main343 CI仍运行，未当PASS；L2/L3 32/29登记UNRUN。 | https://github.com/JTCAO515/G2C/pull/331#issuecomment-6536273412 |
| pass | `C 2026-10-31 exact-head code closeout` | 325 test58/PG28 and old/new graph original guard2/2;339 test58/PG29 and actual14;341 test58/PG30 and actual4 plus independent5 probes;345 scope37/old33 subtests and registered actual15/FEAS4. Each exact code head CI green before locked merge. Prior31 candidate full run and prior originalFAIL/P1 remain historical; no real service/device/fee claim. | https://github.com/JTCAO515/G2C/pull/345 |
| pass | `Lane B #330 final PR342 exact-head CI and locked merge` | Head85acf4ece652ec508e3ed54abae882a6cb83e4af, CI41166636674 all six classes SUCCESS; locked mergee88f9a5a. Full redline APPROVE81ddd7c plus conflict-free latest-main integration with all31 PR files byte-identical. Local test58/58, full30 PG groups at C339 candidate, latest C341 and C345 affected combinations all0, scoped21 PASS. Main CI not waited. | https://github.com/JTCAO515/G2C/pull/342 |
| pass | `Lane B MESSAGE-send.3 actual source/lifecycle acceptance` | Signed local API/restricted PG/explicit M2/run_once/CLI/FakeProvider; structured.1/2 source precision, Trip/version/day/item/owner negatives, ambiguity no latest, old/new original bytes/status/history/cancel/UNKNOWN, ABA/revocation/both Trip writer publication orders. Default travel_message entry always runs oldsend2 and newsend3 in separate fresh clusters; five independent failure probes preserve nonzero failures. New profile is discussion-only; old creation only unupgraded scopes; existing MEMORY refuses upgrade until adapter. | https://github.com/JTCAO515/G2C/issues/330 |
| unknown | `Lane B #315 original failure/root cause` | Original historical count/cause UNKNOWN and FAIL retained. Current full registered_exit and 100 distinct-owner actual API/CLI trials PASS with count1; historical1ee full-run Unicode component alsoPASS. Its separate missingPG16 RUN environmentFAIL and later correctPG16 RUN PASS remain distinct. This does not reproduce the original failure or prove a fix/no regression;315 staysOPEN, two acceptance boxes unchecked. | https://github.com/JTCAO515/G2C/issues/315 |
| pass | `Lane B #315 safe recurrence diagnostics delivered with PR342` | Original340/d6c2d86 candidate two files byte-identical in342; all89 original assertion conditions unchanged. Controlled captured-count1to0 makes originalassert FAIL with safe status/ack/operations/exposure, no token/private input/sentinel; diagnostic DB unavailability explicit. The controlled failure is reporting verification only. Original340 headCI green is historical; actual delivery uses final342 exactheadCI.340 remainsCLOSED archive, not claimed separately merged. | https://github.com/JTCAO515/G2C/pull/342#issuecomment-6538290125 |
| pass | `Lane B JT-authorized #243 background transfer and #9 closure` | Actual PLACE299/265 and FACT318/306 tool evidence retained; background frame explicitly transferred toM3 #23 with full limits/admission/cancel/UNKNOWN/original-task acceptance UNRUN. Remaining L1+L2 transfers complete;243 and9CLOSED,242/244 and5/8 preconditionsCLOSED. No background/real-fee acceptance claimed. | https://github.com/JTCAO515/G2C/issues/23 |
| pass | `B final closeout: python3 -B scripts/handoff.py render; check; git diff --check` | Only permitted B snapshot keys/entries and B plan mappings changed; all non-B top-level keys and A/C string/entry portions retained. Generated handoff matches JSON; no executable, permission, migration, contract or CI change in this final document PR. | — |
| pass | `Lane B343 Part1 contract PR349` | Head e107eda7959eba648d5dfc79f75142e612c32dde locked merge96808a4b, exact CI allSUCCESS and independentAPPROVE6540217289. MESSAGE38 PASS; appended send4/profile2/schema/interfaces/examples only, old frozen files unchanged. All336/337/343/344 M2 and four consumers notified; runtime not claimed in Part1. | https://github.com/JTCAO515/G2C/pull/349 |
| pass | `Lane B343 Part2 actual runtime PR350` | Head74fa0bc2c62ffe0ef456be5cee7640d970a24be6 locked merge1e3af625ef163539ec3efca19f61f2863aa19db3; exact CI41181005753 all6 classesSUCCESS, independentAPPROVE6540666190. Local58/58,147+34subtests, defaultPG30/30 and final integrationPASS. M27local-only emptyup/down/up and populated refusal/minRLSowner negatives. SignedAPI/runtimePG/formalrun_once/Meter/Fake, actualCtyped longterm+temporary realnamespace/currentfence, Cscopedpreview/solewriter+RUNeffectonecursor, owner/hash/member/namespace/ABA/revoke/cancel/UNKNOWN/deadline/rollback/commitACKloss/originalbytes allPASS. Test C bridge is not actual C336/C344 productionrelease. MainCI not waited. | https://github.com/JTCAO515/G2C/pull/350 |
| pass | `Lane B327 supported send2 history regression verification` | history2 actual signedAPI/runtimePG/originalM2worker reads exactoriginalUTF8/hash/text/reference,2page continuity,wrongowner cursor409/auth401 and corrupt reference503; oldv1 still503 by frozen semantics. OldA script13PASS1FAIL retained, not falsely rerun or changed.327CLOSED and228notified6540938015; no new write permission or type downgrade. | https://github.com/JTCAO515/G2C/issues/327 |
| unknown | `Lane B343 review P2 future consumer work` | NoP0/P1. P2 frozen outputschema admits some inconsistent descriptor combinations; runtime revalidates actualoriginalbytes, future schema mustappendversion. Deterministic Memorycapture TripSHARE→Memory vs publicationMemory→TripUPDATE probeRuntimeUnknown, no dirtywrite/overreach; C344 must shortchecksource_lock=False andaddconcurrencytests. Recorded343comment6540675548 and four finalconsumer notices. Not calledPASS or blocking forJT. | https://github.com/JTCAO515/G2C/pull/350#issuecomment-6540666190 |
| pass | `Lane B final handoff render/check/diff and A-C preservation` | Only allowedBsnapshotkeys/prefixedentries and Bplan row/section changed; allA/C portions/nonallowedkeys and historicalverification prefix retained; generatedMD matchesJSON. FinaldocPR has no executable/contract/migration/test/CIchange. | — |
| pass | `C344 production adapter and C336 normal runtime Part1` | PR352 exact e3c6f20 CI all green, independent APPROVE, test58/PG31/new5/old10; PR353 exact3fbb489 CI all green, scoped11 and independent expiry rollback proof, actual canonical source/model/same-cursor proposal/original confirmation/act/receipt recovery. Prior32 full run and old P1/FAIL preserved. Expansion/rejected-preview restoration NOT PASS. | https://github.com/JTCAO515/G2C/pull/353 |
| pass | `C phase1 scope explanation and protected legacy initialization` | PR358 e31911c exact CI all green, test58/manual56+33subtests. PR362 final1f2de5f exact CI41212477041 all green, final PG14, prior trip115/test58/needs15/scoped11; independent fixed-P1 event/rollback/ACK/expiry/source5 PASS, APPROVE6545048896. Old P1 and early ERROR retained. No stage2/B360 frozen outcome claim. | https://github.com/JTCAO515/G2C/pull/362 |
| pass | `Original C goal completion audit:227/17/18/22 backend only` | Live original issues, child acceptance and 14 merged PRs verified; every exact-head CI SUCCESS, each head is merge parent and each merge ancestor of current main. Existing redline APPROVE reused; ordinary282/316/345 post-merge independent supplement APPROVE6546570218/6546575006/6546579649, new focused5/8/37+33sub/15/4 PASS. Backend tree306cd6 equals green916045; green568a67a also verified. Parent22 remains OPEN for A286. Later336/B360 is not an original-goal blocker. Final handoff/main CI remains a live publication gate. | https://github.com/JTCAO515/G2C/issues/22 |
| pass | `C366 discovery delivery and M2 prerequisite audit` | PR368 final853bea89 exact CI41235845596 SUCCESS, independent APPROVE6548301786, source21/trip123/edit_memory5/typed10 and test58 PASS. Actual HTTP original receipt→source-current candidate/diff→original action/readback, DML0/no model or meter increment. P2 metadata comment and all old ERROR/FAIL retained. M2 remains OPEN; B360 L0 not frozen, C phase2/App UNRUN, B354/359 CI green but unmerged. No C-ready implementation besides a new real integration defect. | https://github.com/JTCAO515/G2C/issues/366 |
| PASS | `PR359 exact-head CI41276188165; scripts/test.py; pg_suites.py; needs_creation_pg.py` | B354: head490ecaf00dbfb65530eea3221a04f012484631bc锁合ae417da65d14279937804113dbb4d2cf2506382e，六类SUCCESS/test58/PG32。真实签名API/受限PG/未patchrun_once及实际CLI/Fake/Meter/C needs_local source1→原Signer-act/structured2/NEEDS basis；旧legacy与currentness/owner/UNKNOWN拒绝保持。旧INIT拒绝与C追加source-init交付分开。 | https://github.com/JTCAO515/G2C/pull/359 |
| PASS | `PR379/380 exact-head CI41278030255/41280244048; scoped_result/clock/migration checks` | B360: L0 head19332a15锁合35fb4b3f；L1 head37b95f0f锁合c138fced，六类SUCCESS/test58/默认PG33全0。追加publisher@2、独立result effect、同cursor completed、新status/history/display与M29最小RLS；实际C函数/typed-memory/NEEDS lease桥接的0/1模型、原bytes、rollback/物理ACK/原ID重启、Trip/ABA/account/deadline/cancel/UNKNOWN及真实预算拒绝PASS。空库M1–29 up/down/up、非空down拒绝、owner反例PASS。独立P1首次clock回退原1FAIL/2PASS保留，修后3/3及actualPG10/10 PASS、同轮APPROVEf56逐字一致整合复用；B probe非C生产代证。 | https://github.com/JTCAO515/G2C/pull/380 |
| PASS | `PR382 exact-head CI41283249833; needs_replanning_pg.py; M30 combined-tree check` | B378: head2bb54fedb99f094c2baf960f551545c063189e7c锁合2d0a1011a4c015e63e13fea29c8a22caa20dbe7b，六类SUCCESS/test58/PG33。source2正式run_once+CLI/签名API/受限PG/Fake/Meter/C needs_context真实输入Trip/proposed_fields→原发现/Signer-act/receipt；原手动文本+独立fixed Trip v3保持，采用新Trip v1。NEEDS/selection/Trip变化、fixed/owner、queued/in-flight cancel/UNKNOWN与原status/history/replay bytes均独立PASS。含C M30实际合并树cf52fb1e5a66013c5d1d14b066367d21fb2ede68再次PASS，实际merge tree相同。 | https://github.com/JTCAO515/G2C/pull/382 |
| UNRUN | `real models/API/accounts/fees/cloud/Supabase/production/device` | B本轮未使用真实资源或费用；App、设备、目标网络与M2全局完成按A/C/JT对应证据，不用B PG/Fake或C接口桥接代替。315未新增投入，原FAIL/UNKNOWN保留。 | https://github.com/JTCAO515/G2C/issues/315 |
| PASS | `A #337/#25 PR367/370/384 exact-head delivery and actual App` | PR384 head711573ef84e949267f17de9653e4482351d4b9ec锁合e79f99f6a7c9a12c1e24520e92474a4ff98fc758；CI41294067734五job与最终pr-lint全SUCCESS，独立APPROVE6556237870。HTTP189+Recovery50、RUN87PASS/1既有SKIP、Preview60、Shell260、App23/21及Simulator build PASS。新增五类实际App5/0/0、全AX/扫描/PG停止PASS；索引SHA256 bfe25ab2ed608b444c2da64ffcd59abde60b2f55a3c6448a8cb7a65b820234e2。每场实际head/原ID/bytes/hash分别保留，来源准备每场另2次Fake，非全场零/一模型。旧正常候选九类和历史FAIL不改。 | https://github.com/JTCAO515/G2C/pull/384 |
| PASS | `A #286/#22/#373 manual editing and source2 planning App closure` | PR371/372/376/377已锁head合并，原适用红线APPROVE及每个最终精确CI全绿。377 head50d656e14a319f97fe0977603d627d1f4c216be7合6bfa1077，CI41289497751及main41292256206五job全SUCCESS。新增八场8/0/0与正式main2d0a实际App source1采用→手动标题/固定v3→source2新Trip采用ACK未知→中文重启原GET1/0/0分列，原Trip bytes/hash/NEEDS保持；main组合索引83f05d987ca900a25d59b91748ab1cbe2313f0839b46ba8a444ad3fdcda7a105。三票已CLOSED，候选层未冒称main复跑。 | https://github.com/JTCAO515/G2C/pull/377 |
| UNKNOWN | `post-merge main e79f99f6 CI41295812771` | PR384合并后main CI仍运行中，未记PASS；实时状态优先，若新失败由对应owner及时修，不用PR head绿冒充main绿。 | https://github.com/JTCAO515/G2C/actions/runs/41295812771 |
| UNRUN | `A #21 maps / M2 milestone and goal completion` | 实时M2仅21 OPEN。浏览/时间线/PLACE/讨论绑定L1已交PR308/328/364；综合地图/实际点位/许可/坐标与权限组合未完成。JT暂缓授权，地图UNRUN，未接Key/真实服务；未完成地图App不转记为L1完成，不重复请求同一授权。整线无其他独立实现项，M2/goal未完成；恢复条件为JT明确调整原暂缓指令和安全资源范围。 | https://github.com/JTCAO515/G2C/issues/21 |
| UNRUN | `A real models/accounts/API/fees/cloud/production/device/VoiceOver` | 337/25及286/22/373的真实服务与真机等适用项已实际追加32/29回链；本机签名API/受限PG/Fake/模拟器/全AX不当作真实模型/云RLS/设备/现实行程可行性。所有历史FAIL/UNKNOWN/UNRUN保持。 | https://github.com/JTCAO515/G2C/issues/32 |

## Blockers

- L2/cloud/OTP/real model/device resources, branch protection and production keys remain JT-owned.
- Lane C: M2未完成。C366已关、当前唯一C后端前置是B360 L0新publisher结果冻结通知（尚无B通知；C评论6548676112只是缺口记录），收到即开始336阶段二，不等B整票关闭。A286还等B354/PR359（六类CI绿但OPEN），A337正在消费新发现接口；这些实现归A/B，C不能抢写。当前无其他独立C后端票或已上报未修C联调缺口；等待B真实冻结或A/B新的C缺口，不等JT重复审批。
- Lane A当前整线剩余依赖：实时M2仅#21 OPEN。地图SDK/平台Key类型、来源/缓存许可、同provider实际点位/坐标转换、无定位权限组合及综合双语呈现均UNRUN；JT已明确暂缓授权，A不得接Key/真实地图服务，也不重复询问。owner JT为恢复该授权/安全交接，A为随后App实现，B/C后端已交不再是本线停点。恢复条件为JT明确调整原地图暂缓指令及对应资源范围；恢复后从最新main按原21框补实现和实际证据，不自动恢复OldA。真实服务/费用/云/生产/真机仍需各自既有授权；M2/goal保持未完成。
- Lane B scope remainder: 354/360/378本轮后端交付均闭，无待实施B切片；A373/337及21/22/25的整体收口按实时各owner证据，不能由B后端或B测试桥接代宣称。C381/M30生产结果实现与336已由C交付；schema1跨字段约束P2仍记录，运行状态机/SQL拒绝矛盾结果，后续收紧schema须追加版本。原clock P1的1FAIL/2PASS保留，修后3PASS/实际PG10PASS及独审APPROVE；315原FAIL/UNKNOWN/OPEN保持且本轮未投入，23后台UNRUN不变。
- Lane B true resource stops: 真实模型/API、Gaode/weather/authority数据采集、账号/密钥、费用、云/Supabase/生产、破坏性操作及设备/目标网络仍按JT敏感资源停点；本轮未触发或使用这些资源，L2 #32原登记保持。实际App/设备不由B本地PG/Fake验收替代。没有因等待回执或main CI把整线标blocked。

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

- Action: A: 先核实时M2 OPEN票、21原验收、PR384与最新main CI。337/25及286/22/373已关闭，不重做已有实现，不恢复OldA并行写入。唯一剩余是21地图综合框，按JT暂缓保持UNRUN，不调用地图/接Key/重复求授权；没有独立可推进项时按goal blocked audit规则记录，不制造忙碌或标complete。JT明确调整原暂缓指令并完成安全资源交接后，再由唯一A从最新main恢复21，B/C实际接口缺口交对应owner；保留原ID/bytes/hash/历史FAIL，L2/L3仍按32/29。 B: 本轮354/360/378及B-only结束交接完结；按实时Issue/Git验359/379/380/382及消费通知。C若报真实B接口缺口，按现授权优先在360/343响应，不以旧handoff限制重复求批准；除此不自开未指派领域。source1 needs-structured.1与source2 needs-current-trip.1分开，publisher2结果没有扩大/接受权限。315继续OPEN、本轮不再投入；不等待main CI/回执，不替A/C宣布M2或App/真实资源完成。  C: 继续M2 goal，不把旧四票或366已交当完成。先读实时336/360（区分C阻塞留言与B正式L0冻结）、337/366/354及最新PR，fetch后逐diff查锁。B新结果ABI一冻结，即复用原Memory/NEEDS/Trip活lease和explain，追加本地immutable/FORCE RLS最小SELECT INSERT结果表/有界新读版本，原raw仅恢复，Memory撤回/纠正后内容withhold，Trip前进标过期，无接受动作/无新ID；同cursor原RUN/worker/Meter/Fake完整故障组合，登记26/27后关336并通知337/25。A/B真实组合若转来C缺口立即优先修；不代改ios/B/旧冻结契约或迁移，不猜未冻结字段。#21/#22/#25与milestone只有各owner适用L0/L1和跨线证据齐全后收口；App/真实资源UNRUN。无C可推进项时按实际依赖blocked audit，保持M2未完成。
- Expected observation: A: 337/25、286/22/373 CLOSED，21 OPEN且地图原总框未勾；384 MERGED于e79f99f6、711精确CI及APPROVE均实际成功。当前原生五类5/0/0，正式main source2 ACK组合1/0/0及旧候选层分开，历史FAIL保留。e79合并后main CI41295812771运行中，不预记绿；M2和goal未完成。 C: 366 CLOSED/PR368 MERGED，final853bea89 exact CI全绿/独立APPROVE，原HTTP receipt驱动发现→diff→原action同Trip读回已实证。M2仍OPEN：21/22/25/286/336/337/354/360；336框2/4未完成，B360 L0未到，App刚获C新版本。此前旧goal完成不等于本M2 goal complete；C暂交且无独立项，外部真实依赖明确，main196d38d与最终文档CI以实时状态验真。  B: 354/360/378 CLOSED；359/379/380/382 MERGED，各精确head六类CI SUCCESS。M29、publisher@2/result恢复与source2正式run_once/CLI均可复核；原Trip/proposed_fields、原bytes/receipt/history、当前性/owner/cancel/UNKNOWN及真实计量边界PASS；source2合并树含C M30再次验收PASS。所有业务锁已释放，通知286/373/21/22/336/337/25已发。历史FAIL保留，真实资源/设备不据B证据变PASS。
- Resume command: `# A M2当前收口/地图暂缓审计；保持唯一A owner，不恢复OldA
git fetch origin
git status --short --branch
gh issue list --repo JTCAO515/G2C --milestone 'M2 记忆与行程能力' --state open
gh issue view 21 --repo JTCAO515/G2C --comments
gh issue view 337 --repo JTCAO515/G2C
gh issue view 25 --repo JTCAO515/G2C
gh issue view 286 --repo JTCAO515/G2C
gh issue view 22 --repo JTCAO515/G2C
gh issue view 373 --repo JTCAO515/G2C
gh pr view 384 --repo JTCAO515/G2C
gh run list --repo JTCAO515/G2C --branch main --limit 3
python3 -B scripts/handoff.py check
# B/C historical snapshot commands retained below; live Issue + latest ADR prevail
# C M2 ongoing: candidate discovery delivered; wait only for actual frozen ABI or C integration defect
git fetch origin
gh issue view 366 --repo JTCAO515/G2C --comments
gh issue view 336 --repo JTCAO515/G2C --comments
gh issue view 360 --repo JTCAO515/G2C --comments
gh issue view 337 --repo JTCAO515/G2C --comments
gh issue view 354 --repo JTCAO515/G2C --comments
gh pr view 368 --repo JTCAO515/G2C
gh pr view 359 --repo JTCAO515/G2C
gh issue list --repo JTCAO515/G2C --milestone 'M2 记忆与行程能力' --state open
gh run list --repo JTCAO515/G2C --branch main --limit 3
# B343交付及C接口反馈；不把讨论/DTO/ABI当写权限
gh issue view 343 --repo JTCAO515/G2C --comments
gh pr view 349 --repo JTCAO515/G2C
gh pr view 350 --repo JTCAO515/G2C
gh issue view 336 --repo JTCAO515/G2C --comments
gh issue view 344 --repo JTCAO515/G2C --comments
gh issue view 327 --repo JTCAO515/G2C
python3 -B scripts/handoff.py check
# B本轮354/360/378已交；仅核实时况及实际接口反馈，不重开旧队列
gh issue view 354 --repo JTCAO515/G2C
gh issue view 360 --repo JTCAO515/G2C --comments
gh issue view 378 --repo JTCAO515/G2C --comments
gh pr view 359 --repo JTCAO515/G2C
gh pr view 379 --repo JTCAO515/G2C
gh pr view 380 --repo JTCAO515/G2C
gh pr view 382 --repo JTCAO515/G2C
python3 -B scripts/handoff.py check`

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
