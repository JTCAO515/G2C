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
| Phase | M1 #165 cancellation implementation and full local verification passed; preparing exact-head CI and independent review. #164 remains blocked on #198 authorization. |
| Accepted Issue | #11 / #165: original-run cancellation API, cooperative worker stop and immutable terminal protection. |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-28T12:02:00.559318+00:00 |

## Active Work

- #164 iOS candidate remains preserved on issue-164-app-message-send. Client/Shell suites and Release native negative passed; Debug L1 is blocked by canonical history503. #198 requests narrowly scoped local backend/key wiring; async JT approval remains pending. No #198 changes made here.
- #165 based on latest accepted main96454bf with green CI40667513064, taken under ADR-0007 child-stop skip rule. PR195/196/197 remained unmerged at last check; no proposed parallel-lane rule used as authority.
- RUN-CANCEL@1 accepts only original MESSAGE id/version. Existing owner context supplies principal/scope/receipt; guarded RUN transaction creates an undispatched original and cancels atomically, preserves existing terminals, and withholds uncertain/postcommit-revoked responses.
- Worker starts model calls/publication under RUN fence, discards late stream output and closes generators; cancellation does not roll back committed text/candidate references. A busy first advance may cause the existing lock timeout and must return unknown, not fake cancelled. Service.dispatch and USAGE gates unchanged.
- Full scripts/test.py57/57 and pg_suites.py11/11 passed; e2e22 includes cancellation before dispatch, in-flight answer/draft, gap before second call, preserved committed candidate/completed terminal, real lost commit ACK, account isolation and busy-step unknown.
- Initial core/worker/guard-reentry failures retained and fixed. HTTP test setup first lacked CJ_ENV; corrected explicit-local setup then baseline main returned404 for all four new API tests, while implementation passes. No failure/skips/CI gate removed.

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
| `backend/run/cj_run/core.py, fixture.py, cancellation.py, backend/run/tests/test_core.py, test_cancel_wire.py, backend/run/README.md` | Atomic original cancel, guarded owner/source mutation, reentrant fixture fence and contract/wire tests. |
| `backend/agent/cj_agent/worker.py, provider.py, backend/agent/tests/test_worker_cancel.py, cancellation_checks.py, e2e_local.py` | Cooperative terminal handling, fenced step starts/publication, generator cleanup and real PG/signed API cancellation tests. |
| `backend/cj_api/run_cancel_routes.py, run_events_routes.py, generated.py, contracts/api/openapi.json, ios/Sources/CJAPI/Generated/**` | New RUN-CANCEL@1 only, strict input/configuration boundaries and generated consumers. |
| `docs/handoff.json, HANDOFF.md` | Record blocked #164/#198 and #165 verified progress under current accepted workflow. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| fail | `New core/worker/reentry regressions on prior behavior` | Core cancel API absent; worker3/4 cancellation cases failed; guard reentry could call provider after nested cancel in synthetic repository. Failures retained and corrected. | — |
| fail | `New HTTP tests on baseline96454bf with explicit CJ_ENV=local` | 4/4 fail404; initial test-setup profile error separately retained, not represented as a product regression. | — |
| pass | `uv run --locked python -B scripts/test.py` | 57/57 groups including new contract examples, input/config/owner/unknown tests. First command-start approval review timed out, single allowed retry ran successfully. | — |
| pass | `uv run --locked python -B scripts/pg_suites.py` | 11/11 groups; e2e22 with actual low-privilege runtime, unchanged migrations1..12, all original RLS/connection reuse/signature tests retained. | — |
| pass | `Generated Python/Swift, frozen scope and diff checks` | Python/Swift regenerated from OpenAPI; identical locked Swift generator reused. No local_app, dev_auth, migrations or CI entry/config changes. | — |
| not-run | `Exact-head CI and independent review` | Pending PR; no merge/closure claim. | — |
| not-run | `Real provider/cloud/physical device/billing settlement` | Local PG, signed synthetic identities and FakeProvider only; cancellation does not claim forced remote abort/refund. | — |

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

- Action: Publish #165 with exact base/head and red-line evidence; require all head CI and independent APPROVE, merge locked head, verify main and backfill #165/#11. If #198 is authorized, implement its local prerequisite then resume preserved #164; otherwise follow the latest accepted queue/owner rules for unblocked work.
- Expected observation: Cancellation proof remains local L1; #164 is not closed or bypassed; pending permission is not assumed by elapsed time.
- Resume command: `gh issue view 165 --repo JTCAO515/G2C --comments`

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
