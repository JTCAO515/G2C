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
| Phase | M1 #166 worker ownership/recovery implemented; final L1/full-suite verification in progress. #164 remains blocked on #198 authorization. |
| Accepted Issue | #11 / #166: ordered/mutually exclusive worker execution, restart/snapshot recovery and current authorization checks. |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-28T13:31:15.637989+00:00 |

## Active Work

- #165 PR #199 merged at 1d12ce4b82d07ce442c749661f0157c7cf67a052; exact head CI and independent APPROVE passed; main CI40686520940 all five jobs green. Child and parent cancellation evidence backfilled.
- #166: dedicated physical-session per-chat advisory ownership distinguishes a live worker from interrupted execution. Contenders wait; process/session death permits original RUN recovery to unknown without another provider attempt. Existing short RUN cancellation/publication fences remain.
- #166 actual entry rechecks the existing invitation source and original MESSAGE binding before steps/publication. scripts/run_worker.py has the necessary consumer wiring documented in issue comment6470094167; no policy, key, contract, migration or CI changes.
- #166 baseline reproduced active-worker invalidation and late output after invitation revocation/unreadability. Actual private-PG/TCP e2e28/28 and test57/57 now pass. Complete PG gate, exact-head CI and independent review in progress.
- #164 iOS candidate remains preserved, awaiting #198 approval for missing formal history configuration. Native Release negative and module tests passed; Debug L1 remains blocked. No backend/key workaround implemented.
- Pending PR195/196/197 are not accepted main rules; verify latest queue/ownership before the next ticket. #159/L2/cloud/production keys and branch protection remain JT-owned.

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
| `backend/run/cj_run/core.py, fixture.py, postgres.py` | Dedicated per-chat worker ownership, session loss handling and matching synthetic adapter; transaction-local scope and RLS preserved. |
| `backend/agent/cj_agent/worker.py, scripts/run_worker.py` | Fence execution with current worker ownership and recheck original host admission before new steps and publication. |
| `backend/agent/tests/test_worker_ownership.py, ownership_checks.py, e2e_local.py` | Live-worker competition, actual killed process/lost session, current authorization and TCP resume regressions; existing tests retained. |
| `backend/run/README.md` | Document physical-session requirement, recovery and authorization limits. |
| `docs/handoff.json, HANDOFF.md` | Record #166 implementation/evidence and preserved #164/#198 stop point. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `#165 full local checks, exact-head CI and independent review` | test57/57, PG11/11, e2e22; independent review reproduced22/22 PG and68 unit tests/31 subtests; all head CI/pr-lint green. | https://github.com/JTCAO515/G2C/pull/199#issuecomment-6468738476 |
| pass | `#165 post-merge main CI40686520940` | Five jobs success on1d12ce4; #165 and parent cancellation evidence updated. | https://github.com/JTCAO515/G2C/actions/runs/40686520940 |
| fail | `pytest backend/agent/tests/test_worker_ownership.py on #166 baseline` | Second worker returns unknown instead of waiting while the original provider is alive; synthetic storage/thread reproduction only. | — |
| pass | `uv run --locked python -B scripts/test.py` | 57/57 groups passed on #166 working tree. | — |
| pass | `scripts/pg_suites.py e2e (final TCP/ownership/authorization round)` | 28/28 passed, including actual TCP disconnect/resume, repeated offset, expired cursor/fresh snapshot, killed subprocess, lost lease, same-chat order and revoked/unreadable invitation. Existing cancellation/RLS tests retained. | — |
| not-run | `#166 full PG, exact-head CI and independent review` | In progress; merge and closure not established. | — |

## Blockers

- #164 awaits JT authorization for #198: formal local history configuration is missing and returns503. Its iOS-only scope does not authorize backend/key initialization changes.
- #159 copy, L2/cloud/real users/production key and branch protection decisions remain JT-owned.

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

- Action: Finish #166 final local checks, publish PR, obtain exact-head all-green CI and independent review, merge, verify main, then backfill all four child boxes and parent #11. #167 remains dependent on blocked #164; follow accepted queue thereafter. Resume #198/#164 only when required authorization arrives.
- Expected observation: Original RUN/text survive reconnect and crash; a live competitor waits; revoked or unknown authorization cannot publish.
- Resume command: `uv run --locked python -B scripts/pg_suites.py`

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
