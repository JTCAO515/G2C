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
| Phase | M1 #182 implementation and full local checks passed; preparing exact-head CI/independent review. Next #185, then #163. |
| Accepted Issue | #8 / #182: LOCAL transaction binding, dirty-checkout refusal, same-physical-connection matrix and C2 pooler gate. |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-28T06:57:47.445671+00:00 |

## Active Work

- #176 merged via PR #184 at da9bd50; main CI40640109983 all five jobs green, original and tightened acceptance boxes updated/closed.
- #182 baseline real private PG retained A scope after commit/rollback and unbound SELECT saw A; dirty checkout overwrote to B. The same physical PID was observed; this is not a claim about a real cloud pooler.
- #182 LocalDatabase now returns IDLE with no scope. Transaction-entry hooks install LOCAL MESSAGE/TRIP scopes after isolation setup; direct host with uses same path. Both known M1 authority GUCs are checked at checkout and binding; contamination closes/refuses without overwrite.
- #181 role checks, RLS policies and applied migrations1..11 remain unchanged. Original12 e2e retained; new commit/rollback A/B reuse matrix covers all12 tables SELECT/UPDATE/INSERT with real PG and simulated lease return only. Expanded e2e15/15 passed.
- C2-CLOSURE-PLAN now requires actual pooler reset evidence and the reuse matrix through the actual target before activation; cloud resources remain unapproved/UNRUN.
- JT new sequence: finish #182, then #185, then preserved #163 WIP. #185 rules/scope/source/callers read only so far. Its PR will update issue-plan and add only two AGENTS entries; do not do that cleanup in #182.
- #163 WIP remains isolated on issue-163-message-send-permit and must be rebased/renumbered after current prerequisites. #159/L2/branch protection/production keys remain JT-owned.

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
| `backend/cj_api/local_app.py, backend/message/cj_message/postgres.py, backend/run/cj_run/postgres.py, backend/trip/cj_trip/postgres.py` | IDLE checkout plus transaction-entry LOCAL binding and dirty-scope refusal; no role/policy changes. |
| `backend/agent/tests/e2e_local.py, backend/agent/tests/transaction_scope_checks.py` | Keep old e2e unchanged and add real-PG same-physical-connection reuse/dirty-state tests. |
| `backend/README.md, backend/c2-preparation/C2-CLOSURE-PLAN.md` | Describe binding contract and require real pooler reset/negative evidence before activation. |
| `docs/handoff.json, HANDOFF.md` | Record #176 closure, #182 evidence and JT #185 insertion. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| fail | `Pre-fix retained physical connection probe at da9bd50` | A setting survived commit and rollback, unbound SELECT returned1; same physical connection was overwritten to B instead of refused. Synthetic scopes and real PG only. | https://github.com/JTCAO515/G2C/issues/182#issuecomment-6462294335 |
| pass | `scripts/pg_suites.py e2e before/after new matrix` | Original12/12 maintained; then15/15 with both directions, commit/rollback,12 tables SELECT/UPDATE/INSERT and dirty checkout/transaction closure. No existing e2e removed or altered. | https://github.com/JTCAO515/G2C/issues/182#issuecomment-6462501267 |
| pass | `uv run --locked python -B scripts/test.py` | 57/57 groups. | — |
| pass | `uv run --locked python -B scripts/pg_suites.py` | 11/11 full groups; e2e15/15 includes original12 unchanged plus reuse/dirty-state matrix; migrations1..11 up/down/up. | — |
| pass | `Frozen paths and syntax/diff checks` | No changes under migrations/contracts/.github or test.py/pg_suites.py; existing role check unchanged. | — |
| not-run | `Real pooler reset/cloud/OTP/model/device/deployment` | Local simulated lease return is not actual C2 pooler evidence; activation gate added. | — |
| pass | `Role/e2e AST comparison; frozen-path diff; handoff/diff checks` | Existing role check and all #181 e2e class ASTs unchanged. No migrations, RLS policy, contracts, CI/test-entry, AGENTS or engineering-rule changes. | — |

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

- Action: Submit #182 PR, require exact-head all CI and independent APPROVE, merge locked head, verify main, update #182 and close #8 only after its child/L0-L1 audit. Then #185: rules first, only two authorized AGENTS entries, three scoped examples, protected boundary/security checks kept, queue synchronized in that PR. Then preserved #163 WIP after rebase/renumbering.
- Expected observation: No pooler/cloud activation; existing security checks preserved and complete 12-table reuse proof accepted.
- Resume command: `gh issue view 182 --repo JTCAO515/G2C --comments`

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
