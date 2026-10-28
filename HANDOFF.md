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
| Phase | M1：#158 本地全部必需检查通过，提交 PR 等精确 head CI 与独立审查；完成后按 JT 要求暂停。 |
| Accepted Issue | #7 CJ-006 / #158：模拟器 L1 AX 审计、动态字体、关键状态与 Muse 交互；实际 VoiceOver 已按 ADR-0007 转记 L3 #29。 |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-28T01:43:45.251145+00:00 |

## Active Work

- #151/#155/#20 已完成；#157 经 PR #177 合并为 e36672a，main CI 40537842558 全绿，父票 #7 对应四框已勾。
- #158：修复动态字体、对比度、中文换行与记忆入口点击；普通 App 全量 AX、4 项合成状态/混合输入/键盘/长文、4 项结构回归全部通过；Python56、PG11、CJShell204通过。
- Apple 官方确认 VoiceOver 不在 Simulator 提供。按 ADR-0007 第 1 条，实际设备听读/焦点/激活保留未勾并转记现有 #29，#7/#158/#29 已互相回链；不改里程碑/队列或执行真机操作。
- #156 等 JT 授权仅补 TripPendingStore 中央登记（目标文件超出子票原范围），#5 挂起；#176 保留冷环境求解器预算失败，未提高预算。
- #162 已由 Claude PR #173 关闭，ADR-0008 accepted、MESSAGE-SEND@1 冻结；main 9858a8a CI 40615231118 全绿。#163 的该前置已解除；本轮不启动后续票。#159 文案仍待 JT；#175 为旧 README。
- 本轮完成 #158 后暂停（JT 当前指令）；不自动执行后续队列。实际 VoiceOver 保持 L3 #29 UNRUN。

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
| `ios/App/Acceptance/ShellAccessibilityUITests.swift, ShellFixtureApp.swift, ShellStructureUITests.swift, check_shell_structure.py, README.md` | 新增五项 AX/关键状态/最大字体/混合输入/键盘/长文原生验收；保留四项结构回归；测试工程和证据在仓库外。 |
| `ios/Modules/CJShell/Sources/CJShell/AssistantShell.swift, ShellView.swift, MemoryShell.swift, MemoryContainerViews.swift, TripShell.swift, PublicInformation.swift` | 对比度、标题/状态无障碍语义、固定设置入口动态布局、禁用状态明确可读、大字号助手布局；不改业务权限或原有公开内容字义。 |
| `docs/handoff.json, HANDOFF.md` | 记录 #158 实际验证、早期失败、真实 VoiceOver UNRUN、阻塞子票与本轮完成后暂停的指令。 |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| not-run | `uv run --locked python -B scripts/test.py` | 合入最新 main #173 后新增契约检查，需重跑；合入前56/56通过。 | — |
| pass | `uv run --locked python -B scripts/pg_suites.py` | 全新私有 PG：11/11 suites；未放宽求解器预算或断言。 | — |
| pass | `swift test --package-path ios/Modules/CJShell` | 204 tests / 28 suites；iOS 源码另由原生 App XCTest 构建覆盖。 | — |
| pass | `check_shell_structure.py (structure)` | iOS17.5 普通 App 1 + 合成宿主 3 tests，零失败零跳过；语言/草稿/导航与只读请求回归。 | — |
| pass | `check_shell_structure.py --suite accessibility` | iOS17.5 原生 5 tests 零失败零跳过：四首页/语言页完整 AX；助手6状态双语、Trip/Memory4状态双语、最大字体、中英混合输入/键盘/长文。合成样例明确标识、仅 GET、无写能力。 | — |
| fail | `Prior #158 AX audit runs` | 保留早期 contrast/dynamic type/clipping 和记忆同列表行导航误入的失败；逐项修复，未过滤 audit issue，未删断言。 | — |
| not-run | `Real VoiceOver / real device` | 实际听读、焦点和激活转记 L3 #29；模拟器 AX 不替代。 | https://github.com/JTCAO515/G2C/issues/29#issuecomment-6447261832 |

## Blockers

- #156：中央存储登记缺 TripPendingStore；backend/storage-registry.json 不在允许修改范围，待 JT 授权仅补现状登记（不改政策/行为）或 Claude 安排。父票 #5 挂起，已跳过，恢复执行时优先核对授权。
- #159 帮助/隐私/支持文案需 JT 确认（子票级停点）。
- L2/L3：真实 OTP、真实模型 App 联调、真机均需 docs/authorizations/M1.md 中 JT 批准的条目；目前清单为空。
- #164 等 #163，#167 等 #164 与 #165；#162 已关闭，恢复时先重新核对依赖。

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

- Action: 完成 #158 PR 的精确 head 全 CI 与独立审查后合并，核验 main 并回写 #158/#7，然后按 JT 指令暂停；不领取下一张。恢复时先核 #156 范围授权、#159 JT 文案和 #162 状态，仍阻塞则下一可执行票 #160。
- Expected observation: #158 的 L0/L1 框有实际证据；真实 VoiceOver 仍在 #29 保持 UNRUN，不弱化门禁。
- Resume command: `gh issue view 158 --repo JTCAO515/G2C --comments`

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
