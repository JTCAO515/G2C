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
| Phase | M1 #163 server send-permit implementation and full local validation passed; preparing exact-head CI and independent red-line review. |
| Accepted Issue | #10 / #163: frozen MESSAGE-SEND@1 server CAS, locked send-status, parser split and active one-way trigger. |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-28T08:08:23.404769+00:00 |

## Active Work

- #185 PR #192 merged at958e157; exact-head CI and independent APPROVE passed, main CI40652241654 all five jobs green; five issue boxes backfilled and parent #5 synchronized.
- #163 now accepts only MESSAGE-send.1 writes with CAS; stored draft.1/send.1 remain readable. Original byte replay precedes active-head/CAS checks. Ordinary query active/generation guards preserved for existing RUN/USAGE safety.
- #163 locked send-status returns same-conversation receipt and active head, explicit null only for known absence; errors remain non200. Runtime role/RLS and #182 LOCAL binding hooks unchanged.
- New migration0012 prevents false->true chat reactivation; versions1..11 unchanged. MESSAGE PG tests cover all nine SEND-PERMIT invariants including both deterministic lock orders, closed replay, legacy reads and cross-account absence.
- Full test.py57/57 and pg_suites.py11/11 passed. Additional e2e16/16 includes forced accept-process exit after commit/before dispatch, reconstructed API, same-byte replay and exactly one original RUN. No cloud/model/real-account evidence claimed.
- Consumers changed only per ADR-0008 table; stored draft.1 fixtures retained, memory codec mixed-version roundtrip added, feedback inactive/expired checks split onto separate new fixtures instead of reactivating a chat.
- Original #163 dirty worktree remains preserved. Next is exact-head CI/review/merge, then main CI and issue/parent evidence; #164 follows.

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
| `backend/message/**, backend/cj_api/message_routes.py, backend/memory_jobs/cj_memory_jobs/codec.py` | Resume frozen send-permit candidate; split write/stored parsing, CAS and locked status. Restore ordinary query active/generation guard to preserve existing consumers. |
| `backend/migrations/0012_message_active_one_way.sql, backend/migrations/down/0012_message_active_one_way.down.sql, backend/migrations/manifest.json` | Renumber preserved new trigger after applied0011; applied migrations untouched. |
| `contracts/api/openapi.json, backend/cj_api/generated.py, ios/Sources/CJAPI/Generated/**` | Frozen SEND-PERMIT wire schema and generated consumers. |
| `backend/cj_api/tests/test_message_wire.py, backend/cj_api/tests/test_history_wire.py, backend/message/tests/**` | Adapt send fixtures and add actual PG CAS/status/closed/legacy tests; nine-invariant and wire coverage completed. |
| `docs/handoff.json, HANDOFF.md` | Record #185 completed evidence and #163 resumption. |
| `backend/agent/tests/e2e_local.py, backend/feedback/tests/test_sources.py, backend/memory_jobs/tests/test_jobs.py, scripts/check_ios_trip_confirm.py, scripts/check_run_stream.py` | ADR-0008 write consumers, closed-chat fixture discipline, stored-version codec and real accept-crash recovery. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `PR #192 exact-head CI and independent review` | All five CI jobs plus pr-lint green; reviewer audited every removed check and only deleted internal-defense test, no boundary/security removal. Independent targeted tests passed. | https://github.com/JTCAO515/G2C/pull/192#issuecomment-6463561304 |
| pass | `Post-merge main CI40652241654` | All five jobs completed/success on958e157. | https://github.com/JTCAO515/G2C/actions/runs/40652241654 |
| fail | `Initial #163 restored candidate scripts/test.py` | 53/57: write fixtures still draft.1; old candidate query change bypassed original active/generation guard. Restored guard and adapted only send consumers; no safety test removed. | — |
| pass | `uv run --locked python -B scripts/test.py` | 57/57, including new send-status/parser wire negatives and mixed stored-version memory codec. | — |
| pass | `uv run --locked python -B scripts/pg_suites.py` | 11/11 groups; migrations1..12 up/down/up, nine SEND-PERMIT invariant coverage and original safety suites. | — |
| pass | `uv run --locked python -B scripts/pg_suites.py e2e (additional crash/status coverage)` | 16/16; accept subprocess os._exit after real commit before dispatch, new app recovers exact receipt, replay and one original RUN; API cross-account status null/null. | — |
| pass | `MESSAGE PG group and HTTP wire regression` | MESSAGE12+history7+auth2 plus real restart readback; HTTP wire24. Deterministic PG blocking observed in both commit/status orders. Initial generated-null strict-envelope failure fixed without weakening strict receipt/head validation. | — |
| pass | `Generated Python/Swift reproduction and frozen migration check` | Regenerated into scratch and byte-compared; Swift generator reused from identical Package.resolved. Applied migration entries1..11 and local runtime role/RLS/binding unchanged. | — |
| not-run | `Real cloud/OTP/provider/device/production` | Outside local authorized M1 scope. Native script fixture adaptations syntax-checked only; App send activation remains #164. | — |

## Blockers

- #159 copy, L2/cloud/OTP/real model/device resources, branch protection and production keys remain JT-owned.

## Risks

- DEBUG 开发组装仅限 Simulator、显式 loopback 和开发 token；不是生产认证/存储激活。Release 和真机保持未连接。
- 确认/未知恢复使用现有冻结语义；不代表真实服务、设备、备份恢复或长期数据生命周期验收。
- 原动作/模拟器 Keychain key 留在隔离开发命名空间，不删除无关数据；临时 API/PG 在脚本结束关闭。
- 证据在仓库外及 PR 描述；运行脚本会构建并安装目标 Simulator App，不能据此发布或安装真机。
- #144 独立 V2 范围继续保持不动；完整 P2c 仍缺 MESSAGE 发送许可及真实身份等阶段。

## Operator Actions

- JT 决定：是否启用 main 分支保护（仓库已 public，可免费启用）。
- JT 确认 #159 帮助/隐私/支持文案。
- JT 按需在 docs/authorizations/M1.md 批准 L2 外部资源；目前为空。
- Claude 负责 #162 MESSAGE 发送许可方案。
- 生产签名 key 来源/轮换、真实模型费用、真机/发布、许可证继续由 JT 决定。

## Next Smallest Action

- Action: Publish #163 PR with nine-invariant and ADR-0008 consumer matrices; require exact-head all CI and independent red-line APPROVE, merge locked head, verify main, backfill #163 and parent#10, then #164.
- Expected observation: All L1 send-permit evidence maps to actual private PG/API behavior; no production activation.
- Resume command: `gh issue view 163 --repo JTCAO515/G2C --comments`

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
