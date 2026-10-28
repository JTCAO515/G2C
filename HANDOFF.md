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
| Phase | M1 #176: cold-import cause measured; startup preload and regression pass; candidate being fixed for fresh-checkout three consecutive full PG runs. |
| Accepted Issue | #176: process-level solver preload, unchanged request budget/TIMEOUT/UNKNOWN, fresh-process and three full-PG acceptance. |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-28T05:22:02.299304+00:00 |

## Active Work

- #161 merged via PR #183 as 81fd98e, main CI 40635026257 all five jobs green; #161/#8 boxes updated. #8 remains open for #182.
- #176 fresh baseline: original 5s cross-day case timed out; request import 22.139932500s of 22.140946750s total, prepare/model under 1ms, engine UNRUN. Hot request 0.005447875s passed. Measurements posted to #176 before code changes.
- #176 fix: CP-SAT module import at solver initialization; explicit API-factory/worker startup loading; failures escape startup. No budget value, original assertion, request timer or status semantics changed.
- New startup tests failed in four baseline subcases (two missing preloads, two missing-dependency startups incorrectly succeeded). After fix 3/3 tests pass, including unchanged model-budget TIMEOUT guard. Python57/57 passes.
- Next: verify fixed candidate from a separate clean checkout and independent uv environment, three sequential complete PG runs, each 11/11. Do not repeat failures to hide them.
- #182 follows #176; #163 WIP remains preserved separately until #182 closes, then rebase/renumber after migration0011/latest manifest. No #159/L2/branch-protection/production-key work.

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
| `backend/feasibility/cj_feasibility/solver.py, backend/cj_api/app.py, backend/agent/cj_agent/worker.py` | Move one-time native dependency loading to explicit startup, outside unchanged request budget. |
| `backend/feasibility/tests/test_startup.py, backend/feasibility/README.md` | Fresh-process startup/failure and model-budget regression, plus initialization semantics. |
| `docs/handoff.json, HANDOFF.md` | Record measured failure, candidate checks and required fresh-checkout validation. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| fail | `Pre-fix cold/hot timing on clean 81fd98e checkout` | Cold TIMEOUT/MODEL_BUDGET_EXHAUSTED: import22.139932500s, prepare0.000254959s, model0.000733s, solve UNRUN. Hot CONDITIONAL_SOLUTION: total0.005447875s. Original budget5.0 unchanged. | https://github.com/JTCAO515/G2C/issues/176#issuecomment-6461190353 |
| pass | `unittest test_startup.py before/after fix` | Before:3 tests/4 failing subcases. After:3/3 tests passed. Original model-budget exhaustion remains TIMEOUT/MODEL_BUDGET_EXHAUSTED. | https://github.com/JTCAO515/G2C/issues/176#issuecomment-6461305561 |
| pass | `Post-fix timing (same environment, warm filesystem, new process)` | Startup import0.653840875s; first request0.002212250s, hot request0.000675416s, both CONDITIONAL_SOLUTION and request import0. Does not claim startup loading itself became faster. | https://github.com/JTCAO515/G2C/issues/176#issuecomment-6461305561 |
| pass | `uv run --locked python -B scripts/test.py` | 57/57 groups. | — |
| not-run | `Fresh checkout: three consecutive complete scripts/pg_suites.py runs` | Required before PR/closure; pending on the fixed implementation. | — |
| not-run | `Real provider/cloud/OTP/device/deployment` | No external resources used. | — |

## Blockers

- #159 copy remains JT-owned; not handled in this sequence.
- L2/cloud pooler/OTP/real model/physical-device resources remain separately authorized; no approved M1 external entries.
- #163 waits for #182 under JT queue; #164 waits #163, #167 waits #164/#165, #170 waits #168/#165.

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

- Action: Fix candidate commit, create a separate clean checkout with fresh uv environment, then run scripts/pg_suites.py three times consecutively and require 11/11 each. If any fails, preserve and diagnose. After successful evidence, update PR/handoff, exact-head all CI and independent review; merge/main green/update #176. Then #182, then restored #163 WIP.
- Expected observation: Measured import cost excluded only at startup; original budget/status/assertions preserved and all three full PG runs green.
- Resume command: `gh issue view 176 --repo JTCAO515/G2C --comments`

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
