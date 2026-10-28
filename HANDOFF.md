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
| Phase | M1 #161 local/native acceptance passed; preparing exact-head CI and independent review. JT queue: #161 -> #176 -> #182 -> #163. |
| Accepted Issue | #8 / #161: two local development identities, Keychain restore/logout/switch, bilingual failure and stale-response isolation. |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-28T04:45:05.783169+00:00 |

## Active Work

- #160 completed by PR #181 at d28dd21, main CI 40628471012 all five jobs passed; #160 and matching parent #8 boxes updated.
- #161 implemented DEBUG simulator account flow in Memory: protected API verification, Keychain persistence, explicit restore/logout, stale-response and foreground fences. Legacy direct Trip fixture preserved; Release stays disconnected.
- #161 native first run failed 6/6 because successful login left Shell messageBindingBlocked=true and Trip binding failed. Fixed only after current verified identity; rejected/unknown/expired identities remain fenced. English diagnostic then full native run passed.
- JT 2026-10-28 queue insertion explicitly authorized docs/plan/issue-plan.md change in this first PR: #161 -> #176 -> #182 -> #163, then original queue. #8 includes #182 and must remain open after #161.
- #176 next: read Claude comment 6460752372; measure cold/hot import/preparation/model/search before fixing startup preload. Keep budget values/TIMEOUT/UNKNOWN/assertions; fresh checkout three consecutive full PG 11/11.
- #182 after #176: transaction-level scope, reject existing nonempty cj.* scope before binding, reused physical connection tests across 12 tables and C2 pooler activation gate; preserve existing RLS/role limits and migrations 1..11.
- #163 WIP preserved on issue-163-message-send-permit in its separate worktree; do not resume until #182 completes. Rebase on latest main and renumber provisional migration after 0011/latest manifest.
- #159 copy, L2 authorization, branch protection and production keys remain JT-owned; do not handle them in this insertion sequence.

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
| `ios/Modules/CJShell/Sources/CJShell/DevelopmentAccountHost.swift, DevelopmentAccountView.swift, ShellView.swift, MemoryShell.swift` | Local development account state, stale-response and foreground fences, and memory/account UI injection. |
| `ios/Modules/CJShell/Tests/CJShellTests/DevelopmentAccountHostTests.swift` | Three controlled async tests for switching, logout/restore uncertainty, and foreground revalidation. |
| `ios/App/CJProbeApp.swift, DevelopmentTripHost.swift, DevelopmentSessionConfiguration.swift` | Explicit DEBUG simulator account/Keychain root, protected GET verification, borrowed Trip session lease, metadata-only expiry and namespaces. |
| `docs/handoff.json, HANDOFF.md` | Record #160 closure and unfinished #161 acceptance. |
| `ios/App/Acceptance/DevelopmentAccountUITests.swift, check_development_accounts.py, ios/App/README.md` | Seven native bilingual/debug/release cases with real local signed API/private PG/Keychain and credential-byte scans; documented reproduction. |
| `docs/plan/issue-plan.md` | JT explicitly authorized insertion of #176 and #182 after #161 and before #163, including dependencies and parent #8 closure rule. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `swift test --package-path ios/Modules/CJAuth` | 100 Swift Testing tests across four runners (19+27+8+46); no empty XCTest wrapper counted as evidence. | — |
| pass | `swift test --package-path ios/Modules/CJShell` | 207 tests / 29 suites after verified-binding fence fix; includes three new controlled async account tests. | — |
| pass | `swift test --package-path ios/App` | 4/4 development configuration tests. | — |
| fail | `check_development_accounts.py (initial full native run)` | 6 Debug cases failed to sign in; UI reported secure storage unavailable because TripContainerHost refused the still-blocked Shell identity. Original xcresult retained; no test assertions weakened. | — |
| pass | `check_development_accounts.py --diagnostic-test testLifecycleEnglish` | Partial only: English two-account Keychain login/logout/relaunch passed after fence fix; other cases explicitly UNRUN in that report. | — |
| pass | `check_development_accounts.py (full native acceptance)` | iOS17.5: 6 Debug cases (English/Chinese lifecycle, rejected/expired/actual offline, delayed A response after B switch) + 1 Release-disconnected case, 0 failed/0 skipped. Relaunch omits tokens and restores from actual simulator Keychain. App-file and artifact raw-token scans pass; screenshots inspected. | — |
| pass | `uv run --locked python -B scripts/test.py` | 57/57 groups. | — |
| pass | `uv run --locked python -B scripts/pg_suites.py` | 11/11 groups, migrations 1..11 up/down/up. This run does not establish #176 cold-start repair; historical failures remain and #176 is now next in queue. | — |
| pass | `git diff --check; handoff render/check; App README relative links` | Formatting, generated handoff and links checked. | — |
| not-run | `Real OTP/cloud/model/device/release` | No L2/L3 resources or production activation used. | — |

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

- Action: Create #161 PR including the explicitly authorized M1 queue update, wait exact-head CI and independent review, merge only approved head, verify main CI and update #161/#8. Keep #8 open for #182. The unique next ticket is #176, then #182, then restore #163 WIP; do not skip ahead to #163.
- Expected observation: #161 L0/L1 acceptance complete with fixed-head gates, and nextAction points to #176 measurement first; frozen budgets/RLS/migrations/contracts/CI remain unchanged.
- Resume command: `gh issue view 161 --repo JTCAO515/G2C --comments`

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
