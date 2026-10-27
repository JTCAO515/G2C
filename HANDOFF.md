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
| Phase | M1：#151 PR #174 第三轮候选；前两轮测试全绿但 Swift 调度墙钟超过增幅阈值，改为单 runner 顺序跑全包，待最终 CI 与独立复审。 |
| Accepted Issue | M1 队列：#151 S0 Part 2/2 → #20 CJ-015 剩余 #155 → #5 → #7 → #8 → #10 → #11 → #19；见 docs/plan/issue-plan.md |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-27T14:30:53+00:00 |

## Active Work

- #154 已关闭（PR #172）；#20 剩余 #155。
- #151 PR #174：单个 Swift job 顺序跑 16 包 + App Release；Shell 先构建共享依赖，Cleanup 最后运行避免锁版本切换；强制锁定版本，保留全部检查。
- #174 已连续两轮 REQUEST CHANGES，均因耗时：第一轮 582 秒（+314），第二轮 599 秒（+331），已报告且未合并。第三轮若仍审查不通过，按 ADR-0007 记录子票阻塞并跳过。
- #162 owner Claude，PR #173 待 JT 批准；#159 文案待 JT。
- #175 记录入口 README 旧暂停文案，不属于本 CI 切片。

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
| `.github/workflows/ci.yml, .github/workflows/pr-lint.yml, .github/swift-packages.json, .github/scripts/swift_packages.py, .github/scripts/test_swift_packages.py` | 单个 Swift job 全覆盖 16 包并复用锁定编译；遗漏、完整执行和失败传播检查；独立最小权限 pr-lint。 |
| `ios/Modules/CJShell/Tests/FeasibilityHostHarness` | 历史测试包直接依赖当前模块，失效负例使用真实 Shell 入口；保留所有断言，锁定依赖。 |
| `ios/Modules/CJMessageClient/Package.resolved` | 补齐现有测试图缺失的依赖锁项，版本与既有 CJShell 锁一致，无产品源码修改。 |
| `docs/handoff.json, HANDOFF.md` | #151 当前状态、验证与下一步。 |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `uv run --locked python -B scripts/test.py` | 56/56 suites。 | — |
| pass | `Swift inventory + pr-lint local negative/positive checks` | 完整清单通过；遗漏嵌套包/陈旧项/重复项失败；Issue 引用正负与 shell 字面内容不执行。 | — |
| pass | `uv run --locked python -B scripts/pg_suites.py` | 11/11 groups，PG16/17 私有集群与迁移 up/down/up。 | — |
| pass | `swift test --package-path <.github/swift-packages.json 中每个包>; ios/App -c release` | 16/16 包成功；App Debug/Release 各 4 tests；CJShell 204、独立 FeasibilityHostHarness 10、CJTripClient 63。 | — |
| pass | `GitHub Actions pr-lint（故意缺引用）` | 预期失败：缺少 Issue 关联时 pr-lint exit 1；此失败是负例，不是全 CI 通过。 | https://github.com/JTCAO515/G2C/actions/runs/40514287589/job/122224804417 |
| pass | `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild App generic iOS Simulator arm64` | CJProbeApp build succeeded；本票无产品修改，未重复交互验收。 | — |
| fail | `#174 initial CI / independent review aa006782` | 20/20 测试 job 成功，但 Swift 墙钟 582 秒比 268 秒增加 314 秒；性能要求未通过，不合并。 | https://github.com/JTCAO515/G2C/pull/174#issuecomment-6443908168 |
| pass | `.github/scripts/test_swift_packages.py; swift_packages.py --shard 0/1/2` | 4 个门禁编排测试通过；实际 Swift 三组包含 16 包 + App Release 全通过，使用 --force-resolved-versions 后无锁文件变化。测试替身只用于编排负例，不替代实际 Swift。 | — |
| fail | `#174 second CI / independent review 801211ca` | 7/7 CI + pr-lint 成功，17 次实际 Swift 测试完整；首组启动到完成 599 秒，增幅 331 秒；含首次排队 903 秒，耗时要求仍未通过。 | https://github.com/JTCAO515/G2C/pull/174#issuecomment-6444599873 |
| pass | `.github/scripts/test_swift_packages.py; swift_packages.py --run` | 4 个门禁编排测试通过；单 runner 原型全 17 次运行 109 秒；正式脚本再次全部通过，无锁文件变化。真实 CI 耗时仍待核验。 | — |
| not-run | `GitHub Actions final head; independent review` | 等待 PR #174 最终 head 的全部阻塞检查与独立 Codex 审查；合并后核验 main。Swift 原基线 268 秒，矩阵耗时见 PR。 | https://github.com/JTCAO515/G2C/pull/174 |

## Blockers

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

- Action: 完成 #151 PR #174 第三轮精确 head CI 与独立复审：单 Swift job 相对原 268 秒增幅不超过 300 秒。通过后合并并核验 main、关闭 #151，再做 #155；若连续第三轮审查不通过，评论并记入 blockers，跳过 #151 继续队列。
- Expected observation: #151 全部验收框有 L0 证据，main CI 全绿；随后推进 #155。
- Resume command: `gh issue view 151 --repo JTCAO515/G2C --comments`

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
