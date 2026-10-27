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
| Phase | M1：#157 四 Tab 结构与语言验收候选完成，本地原生 iOS 17.5 四项 UI 检查通过，待 PR CI 与独立审查。#156 挂起待范围授权。 |
| Accepted Issue | #7 CJ-006 / #157：iOS 17.5 四 Tab、记忆入口、语言保留和插件占位；#156 获授权后优先恢复。 |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-27T15:53:56+00:00 |

## Active Work

- #151 已关闭（PR #174），#155 与父票 #20 经独立核验关闭；main 56c7153 CI 全绿。
- #157：新增外部 XCTest 验收入口，普通 App 验证中英四 Tab、语言/导航/草稿与重启；标记为 synthetic 的 readonly Memory 宿主覆盖未配置/空/失败入口、标识保留和插件无额外请求。4 个原生测试全部通过。
- #156 缺 TripPendingStore 中央登记，目标文件超出允许范围；待 JT 授权仅补登记或 Claude 安排，父票 #5 挂起。首次冷环境求解器超时保留为 #176，独立及串行完整复跑通过。
- #162 owner Claude，PR #173 待 JT；#159 文案待 JT；#175 为旧 README 暂停文案。

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

## Architecture Contracts

- contracts/api/openapi.json unchanged in P1.
- backend/migrations/manifest.json: versions 1-10, sha256-checked up/down; applied versions must never be edited.
- Single business authority and recovery semantics per ADR-0003 (proposed) remain the target for P2.

## Changed Files

| Path | Reason |
| --- | --- |
| `ios/App/Acceptance/ShellStructureUITests.swift` | 四个原生 UI 测试：普通 App、双语记忆状态入口、语言/标识保留、插件无请求与权限弹窗。 |
| `ios/App/Acceptance/ShellFixtureApp.swift, ios/App/Acceptance/check_shell_structure.py, ios/App/Acceptance/README.md` | 外部测试工程复用真实 Shell 和只读客户端；隔离 bundle、loopback 合成响应、请求审计与外部证据目录；不进入正式 App target。 |
| `ios/App/Package.swift` | 验收目录与 macOS 开发配置 target 分离；原 4 个配置测试完整保留。 |
| `docs/handoff.json, HANDOFF.md` | 同步已关闭 #151/#155/#20、#156 挂起及 #157 验证和下一步。 |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `uv run --locked python -B scripts/test.py` | 56/56 groups。 | — |
| pass | `uv run --locked python -B scripts/pg_suites.py` | 私有 PG16/17，11/11 groups，含迁移 up/down/up。 | — |
| pass | `swift test --package-path ios/Modules/CJShell` | 204 tests。 | — |
| pass | `swift test --package-path ios/App; swift test --package-path ios/App -c release` | Debug/Release 各 4 tests，验收宿主不进入该包的正式 target。 | — |
| pass | `python3 -B ios/App/Acceptance/check_shell_structure.py --simulator <iOS-17.5-UDID> --output <external-directory>` | 普通 App 1 test + 标记合成宿主 3 tests，全通过无跳过；截图与 xcresult 在仓库外。实际原生点击、输入、语言重启、6 种状态/语言入口、标识不变与请求审计。 | — |
| not-run | `PR exact-head CI + independent Codex review` | 待 PR 全部 CI 与独立审查；无自批。 | — |
| not-run | `Real services / device / VoiceOver / final privacy-support wording` | 本票只关闭 #157 结构与语言，未代替 #158/#159、真实认证/存储或 L2/L3 验收。 | — |

## Blockers

- #156：中央存储登记缺 TripPendingStore；backend/storage-registry.json 不在允许修改范围，待 JT 授权仅补现状登记（不改政策/行为）或 Claude 安排。父票 #5 挂起，先继续 #157。
- #162 OPEN：Claude PR #173 待 JT 批准；#163 等 #162，#164 等 #163，#167 等 #164 与 #165（子票级停点，跳过继续）。
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

- Action: 为 #157 提交 PR，等待精确 head 全部 CI 与独立 Codex APPROVE 后正常合并并核验 main、回写 #7；然后 #158。若 JT 先解除 #156 范围阻塞，优先恢复 #156。
- Expected observation: #157 四框有 L1 证据且通过交付门禁；#156/#159/#162 相关阻塞保持明确。
- Resume command: `gh issue view 157 --repo JTCAO515/G2C --comments`

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
