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
| Objective | 完成本轮 #149/#150 审查合并与 DEBUG App 开发会话、iOS 17.5 行程确认端到端；保留正式写入、原动作恢复及外部资源授权边界。 |
| Status | active |
| Phase | M1 主链路闭环（模拟器 L1）：Issue 按 ADR-0007 重新规划（docs/plan/issue-plan.md）；#154 已关闭（PR #172），下一张为 #151 S0 Part 2/2。 |
| Accepted Issue | M1 队列：#151 S0 Part 2/2 → #20 CJ-015 剩余 #155 → #5 → #7 → #8 → #10 → #11 → #19；见 docs/plan/issue-plan.md |
| Owner | JT operator；Claude 架构/任务 B 抽查；Codex 任务 A 审查返修、任务 B 开发验收 |
| Last updated | 2026-10-27T12:30:00Z |

## Active Work

- #154 已关闭：PR #172 合并为 715fd00，main CI 全绿；#20 框 4 已勾，框 1、7 的 App 部分已附证据，服务端部分待 #155。
- #151 S0 Part 2/2（iOS 测试全部进 CI、pr-lint）未开始，为下一张。
- #162（CJ-009 子票）：MESSAGE 发送许可方案，owner Claude，未开始；#163、#164 依赖它。

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
- JT current dispatch: Codex reviews/repairs and merges #149 then #150; task B remains subject to Claude review. No #144 or MESSAGE write implementation in this slice.
- GitHub visibility read-back 2026-10-27: PUBLIC. Secret/local-path prohibitions remain. No repository settings were changed in this task.
- JT latest instruction: finish this round, submit/review/merge its PR into main, verify main CI and then PAUSE. This supersedes the earlier task-B Claude-before-merge requirement; independent Codex review under ADR-0007 remains required. No automatic continuation.
- JT 2026-10-27：仓库可见性当天先改为 PRIVATE，随后又改回 PUBLIC（gh 读回 PUBLIC）；去本机路径和秘密规则继续有效，许可证仍待定。ADR-0005/0006 的 V2 商业决策因此公开可见。
- accepted (JT 2026-10-27): ADR-0005 proactive fulfillment is V2 scope (backend JT Agent, signals -> cases -> AI execution with human confirmation); V1/P2 scope unchanged. Architecture and model choice remain proposed until the V2a shadow mode (docs/v2/shadow-mode.md).
- accepted (JT 2026-10-27): ADR-0006 V2 membership Free / Plus / Guardian via Apple IAP; human service bundled; memory never deleted by the system, user-requested deletion always honoured; prices pending.

## Architecture Contracts

- contracts/api/openapi.json unchanged in P1.
- backend/migrations/manifest.json: versions 1-10, sha256-checked up/down; applied versions must never be edited.
- Single business authority and recovery semantics per ADR-0003 (proposed) remain the target for P2.

## Changed Files

| Path | Reason |
| --- | --- |
| `docs/plan/issue-plan.md` | 新增：里程碑 M0–M5、M1 队列与子票、依赖、停点与跳过、M2 拆分预案。 |
| `docs/adr/0007-issue-closure-workflow.md` | 第 2 条队列改指规划文档、框数 2–6、挂起父票不占在制名额；第 7 条停点分子票级与仓库级。 |
| `AGENTS.md, .github/ISSUE_TEMPLATE/slice.md` | 阅读顺序加入规划文档；框数 2–6；停点分级。 |
| `docs/handoff.json, HANDOFF.md` | 切换到 M1 队列状态。 |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `python3 -B scripts/handoff.py check` | handoff 结构与阅读顺序一致。 | — |
| pass | `GitHub Issue 规划核对` | M0–M5 里程碑；#155–#170 为 M1 子票并已挂到父票；父票验收框均标明 → #子票 / → L2 #32；L2 转记已登记到 #32。 | https://github.com/JTCAO515/G2C/pull/171 |
| not-run | `GitHub Actions ci.yml` | 以 PR #171 精确 head 检查为准（文档改动）。 | — |

## Blockers

- #162 未关闭前，#163、#164 不能开工；#167 依赖 #164（子票级停点，跳过继续）。
- #159 帮助/隐私/支持文案需 JT 确认（子票级停点）。
- L2/L3：真实 OTP、真实模型 App 联调、真机均需 docs/authorizations/M1.md 中 JT 批准的条目；目前清单为空。

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

- Action: 开始 #151 S0 Part 2/2：iOS 测试全部进 CI（ios/Modules/**/Package.swift 全覆盖并检查遗漏）、新增 pr-lint；合并后按 docs/plan/issue-plan.md 从 #155 继续。
- Expected observation: #151 关闭；main CI 包含全部 iOS 模块测试与 pr-lint 且全绿。
- Resume command: `gh issue view 151 --repo JTCAO515/G2C`

## Rollback

revert PR #171 合并提交即可恢复原队列写法；GitHub 上的子票、里程碑与父票规划块需另行手工回退（原正文备份在 Claude 会话 scratchpad，非仓库）。无代码、迁移或配置变更。

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
