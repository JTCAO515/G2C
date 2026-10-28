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
| Phase | M1 #166 merged/closed with green main; #168 structural ingress repair in progress, time mapping unresolved. #164/#167 remain blocked. |
| Accepted Issue | #19 / #168: draft structure and travel constraints; current candidate is Part 1/2 (structure only). |
| Owner | JT 决策与外部资源；Codex 按队列实现、自审、合并（ADR-0007 第 3、7 条）；Claude 负责规划、#162 并按需抽查 |
| Last updated | 2026-10-28T13:53:18.747359+00:00 |

## Active Work

- #166 PR #200 merged at96e97af88d71390a9f2609cd0eedbb670762b0be; exact head5abd322 CI/pr-lint and independent APPROVE6470507941 passed. Main CI40698481356 all five jobs green. Four child boxes and parent#11 account/authorization/order/recovery evidence backfilled; parent remains open for#167.
- #167 skipped by accepted prerequisite rule: #164 still waits for#198 authorization. Existing #164 iOS work preserved; no backend/key workaround.
- #168 base96e97af: reproduced duplicate model JSON fields silently replacing earlier values and unpaired Unicode escaping DraftRejected. Part1 rejects ambiguous JSON, parser nesting overflow and invalid Unicode before publishing; existing valid/prose-compatible input and all boundary/security checks remain.
- #168 Part1 unit16/16, full test.py57/57 and pg_suites.py11/11 pass, including e2e29/29 with10 structural rejection subcases and all prior regression checks. Preparing exact-head CI and independent review; #168 remains open.
- #168 time mapping remains unresolved: active Proposal stores title/items/id/text/verification/evidence only, while FEAS requires authentic structured NEEDS inputs. Free-form model text is not such an input; do not fabricate snapshots/history or change frozen contracts to claim travel validation.
- #159/L2/cloud/production keys and branch protection remain JT-owned. Pending PR195/196/197 are not accepted main rules.

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
| `backend/agent/cj_agent/draft.py` | Reject duplicate model JSON keys, excessive nesting and unencodable text as DraftRejected before persistence. |
| `backend/agent/tests/test_draft.py, e2e_local.py` | Model-boundary regressions and real private-PG no-publication negatives; no existing tests removed. |
| `backend/draft/README.md` | Distinguish structure-only repair from unresolved travel/time mapping and failure presentation. |
| `docs/handoff.json, HANDOFF.md` | Record #166 closure, #167 prerequisite skip, #168 partial scope and pending decisions. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `#166 full local checks / independent review / exact-head CI` | test57/57, PG11/11 including e2e28; independent review reproduced e2e28/28, all head jobs green. | https://github.com/JTCAO515/G2C/pull/200#issuecomment-6470507941 |
| pass | `#166 post-merge main CI40698481356` | Five jobs success on96e97af; #166 closed, parent evidence updated. | https://github.com/JTCAO515/G2C/actions/runs/40698481356 |
| fail | `pytest backend/agent/tests/test_draft.py baseline` | 4 failed /12 passed: duplicate fields accepted and Unicode error escaped the draft failure type. Evidence preserved outside repository. | — |
| pass | `pytest backend/agent/tests/test_draft.py after structure repair` | 16/16 passed. Includes duplicate spellings, unpaired surrogate and parser recursion bound. | — |
| pass | `uv run --locked python -B scripts/test.py; uv run --locked python -B scripts/pg_suites.py` | test57/57, PG11/11 including e2e29/29 with10 structural no-publication subcases. CI and independent review still pending. Travel constraints and user-visible draft failure remain unresolved. | — |

## Blockers

- #164 awaits JT authorization for#198: formal local history configuration is missing (503); backend/key initialization is outside its iOS-only scope. #167 depends on#164.
- #168 owning structured draft-time-to-NEEDS mapping is missing; frozen contracts cannot be changed under this ticket. Time conflict acceptance and explicit draft failure presentation remain unproven; #169/#170 depend on#168.
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

- Action: Publish #168 Part1 structure repair with Refs#168 Part1/2; obtain exact-head all-green CI and independent APPROVE, merge, verify main and update evidence. Keep both full #168 boxes open for the missing structured time/NEEDS mapping and failure presentation. Do not change frozen contracts or invent NEEDS provenance. Resume #198/#164 only when required authorization arrives.
- Expected observation: Ambiguous/invalid model structures never create candidates, formal trips or RUN effects; time validation remains explicitly unresolved.
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
