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
| Status | paused |
| Phase | M1：#158 已经 PR #178 合并，main 6dba3a5 CI 全绿；JT 要求本轮做完后暂停，尚未领取下一张票。 |
| Accepted Issue | #7 CJ-006 / #158 已完成 L0/L1；#7 尚余 #159 等 JT 文案，实际 VoiceOver 转记 L3 #29。 |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-28T02:01:42.903740+00:00 |

## Active Work

- #151（PR #174）、#155（核验关票）及父票 #20、#157（PR #177）、#158（PR #178）已关闭；#7 对应 #157/#158 框已同步，#159 未完成，父票保持挂起。
- #178 head 1a8e310f8ca75676f2ec9cac338952113ac94429 经独立 APPROVE 与六项 CI SUCCESS 正常合并为 6dba3a51a89f4e538af23f2f6eb7b799120923eb；main CI 40617700900 五 jobs SUCCESS。
- #158 本地：Python57/57、PG11/11、CJShell204、iOS17.5结构4+无障碍/状态5测试全过；早期失败保留于PR证据表，未过滤审计或放宽断言。
- #156 缺中央 TripPendingStore 登记，超出原票允许文件，待 JT 范围授权；#159 待 JT 文案。#175旧README、#176冷环境求解器预算失败已另票记录，未扩大本轮范围。
- #162 已由 Claude PR #173 关闭，ADR-0008 accepted、MESSAGE-SEND@1 冻结，#163 的该前置已解除；#164/#167 仍需各自后续前置。
- 按 JT 当前指令暂停。M1 尚未全部完成，不自动取下一张票；实际 VoiceOver/真实外部服务/真机仍未验收。

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
| `docs/handoff.json, HANDOFF.md` | #158 合并后记录精确审查/CI、Issue回写、已解除及剩余阻塞，并按JT明确指令暂停；仅交接状态，无产品或门禁改动。 |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `PR #178 / main CI` | 精确 head 独立 APPROVE；PR六检查全绿；main合并6dba3a5五jobs全绿；#158 L1三框和#7对应框已回写。 | https://github.com/JTCAO515/G2C/actions/runs/40617700900 |
| pass | `uv run --locked python -B scripts/test.py` | 同步 main #173 后57/57 passed，包含新增 MESSAGE-SEND 契约检查。 | — |
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

- Action: 暂停，等待 JT 明确恢复。恢复后的第一步：fetch/status 并确认最新 main CI 全绿，读 #156/#159/#162 的正文及全部评论核对阻塞；已解除的 #163 优先核其父票 #8、前置与全部评论，再按 issue-plan 队列执行。若 #156 获范围授权则优先收尾 #156。本次不启动任何后续子票。
- Expected observation: 暂停指令解除前不写代码、不认领新票；恢复时以Git/Issue/CI实况为准，#162已关闭不再作为阻塞。
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
