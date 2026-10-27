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
| Objective | Deliver G2C (foreign-visitor China travel assistant, iOS + CJ Agent backend) to invited beta via one real end-to-end path first; P0 makes the repository self-sufficient for takeover and makes CI the only source of green. |
| Status | active |
| Phase | P2c：#147 已按 JT 本轮替代审查授权合并；CJ-015 服务端确认凭证切片待审 |
| Accepted Issue | CJ-015 / GitHub #20：服务端确认凭证、准备接口与原 TRIP 事务校验 |
| Owner | JT (operator); Claude architecture/review; Codex implementation |
| Last updated | 2026-10-27T06:54:44Z |

## Active Work

- PR #147 head 2dade43da693510e0a0aad5935cf02e25bbf8d46：JT 明确跳过 Claude、指定 Codex 审查后继续；Standards 0 / Spec 0，四 CI 全绿，已正常合并为 d74e9fcf7b4c857524edf29a0c3f4c3bf6c175e7。不冒认独立审查。
- feat/p2c-trip-confirmation 从最新 main 开始，新增签名确认准备接口，保留原动作与正式 TRIP 写入边界。
- PR #144 保持独立 V2 文档范围，未处理。

## Accepted Assumptions

- P2b 本地和真实 provider 结果为原作者报告，本轮未重复调用模型。
- ADR-0002 组合候选状态不因壳构建通过而改变。

## Frozen Decisions

- ADR-0001 产品与用户控制边界继续有效。
- qwen3.8-flash 与北京端点已选定；P2b 原作者报告真实 smoke 4/4，本轮未重跑。
- ADR-0004 已接受；单一 Python 发行包 cj，保留领域 import 名，不恢复同仓 hash pin 或 Git 导出依赖。
- 当前 GitHub 实况为 PRIVATE；早先 PUBLIC 状态已过期，去本机路径和秘密规则继续有效；ADR 修订由 #144 单独处理。
- P2：北京、邮箱 OTP、最低 iOS 17。
- JT 当前指令：Codex 实现/测试/交付，Claude 架构/规划/审查，JT 决策与外部资源。
- JT 当前指令：python、postgres、swift、ios-app 四 job 均阻塞；合并还需 Claude 独立审查或 JT 明确同意。
- 历史证据归档 tag evidence-archive-2026-10-27；不改写历史。
- JT 2026-10-27: PR #147 only uses Codex review instead of Claude; continue subsequent P2c work. This is not independent review and not blanket approval for later PRs.

## Architecture Contracts

- contracts/api/openapi.json unchanged in P1.
- backend/migrations/manifest.json: versions 1-10, sha256-checked up/down; applied versions must never be edited.
- Single business authority and recovery semantics per ADR-0003 (proposed) remain the target for P2.

## Changed Files

| Path | Reason |
| --- | --- |
| `backend/trip/cj_trip/confirmation.py, backend/trip/cj_trip/postgres.py` | 签名绑定原动作/内容/作用域/版本/有效期，现有事务最后使用 DB 时间重新校验；不新增迁移。 |
| `backend/cj_api/trip_confirmation_routes.py, backend/cj_api/app.py, backend/cj_api/composition.py, backend/cj_api/local_app.py` | 新增认证准备接口，显式同一 issuer/validator；默认新接口关闭，旧本地路径保留。 |
| `contracts/api/openapi.json, backend/cj_api/generated.py, ios/Sources/CJAPI/Generated/*` | 两个新增 envelope 与准备操作；正式来源重新生成 SDK，包含之前遗漏的既有 P2a 操作声明，旧 schema/操作不变。 |
| `backend/cj_api/tests/test_trip_confirmation.py, backend/trip/tests/test_confirmation.py, backend/agent/tests/e2e_local.py, contracts/api/check_trip_content_v2_schema_proposal.py` | 签名、原动作并发/重放、提交前过期、授权撤回、API/PG 集成；精确登记两新增 schema，保留原 V1 与 V2 禁止注册断言。 |
| `backend/README.md, README.md, docs/dispatch/P2-walking-skeleton.md, docs/handoff.json, HANDOFF.md` | 记录原审查授权、确认准备语义、配置与兼容退出条件、实际验证和剩余 P2c 边界。 |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `#147 固定 base/head 审查 + 四 job CI` | Standards 0、Spec 0；按 JT 最新指令由同一 Codex 替代 Claude 审查后正常合并。该例外仅 #147，不扩展到此新 PR。 | https://github.com/JTCAO515/G2C/pull/147 |
| pass | `uv run --locked python -B scripts/test.py` | 56/56 组通过；其后补充 issuer/validator 配置替换拒绝检查，6 个确认单测定向通过。最终 head 全量由 CI 复核。 | — |
| pass | `uv run --locked python -B scripts/pg_suites.py trip` | 79 项私有 PG 测试通过，含同原动作并发一次提交、拒绝不写 Trip、末次 AUTH guard 后凭证过期回滚、原回执跨 key 轮换重放。 | — |
| pass | `uv run --locked python -B scripts/pg_suites.py e2e` | 7 项本地真实 API/PG 测试通过；签发不写入、接受/拒绝/重放/篡改/跨用户拒绝及签发期间授权撤回。使用 FakeProvider 和临时开发身份。 | — |
| pass | `Swift 根包测试 / arm64 Simulator App 构建` | 根包 4 项测试通过，Xcode 27.1 App 构建通过；不代表 iOS 写入 UI/真实登录已接通。 | — |
| pass | `正式 API 生成与 exact-base 兼容比较` | Python/Swift 生成产物与生成目录相同；对 d74e9fc 的所有既有 schema/操作逐项比较无修改。初次历史测试因新增 Trip 名称失败，已精确登记两 envelope；原 V1 和 V2 禁止注册断言保留。 | — |
| pass | `python3 -B scripts/handoff.py check; git diff --check` | JSON render/check and git diff --check passed. | — |
| unknown | `本新 PR 最终 head 四 job CI / 独立审查` | 截至提交准备时未运行；通过分支 feat/p2c-trip-confirmation 的 PR 读取最终结果，不沿用 #147 的绿。 | — |
| not-run | `真实确认 key 配置、云/OTP、iOS 写入 UI、真实模型、真机` | 未配置真实 key 或外部资源，未开放 iOS 写入门禁；没有云写入、付费调用、部署。 | — |

## Blockers

- 此新确认凭证 PR 尚需四 job CI 与独立审查或 JT 明确同意。
- iOS 原动作持久化、确认 UI 和写入 transport 尚未接入；TripClient 的生产写入门禁保持关闭。
- MESSAGE 发送许可/不可回退原动作证据尚未完成；OTP、真实模型 App 联调、真机亦未验收。

## Risks

- 新接口只签发审阅绑定，不证明用户已确认，不改正式行程；客户端必须保留原动作字节并显式确认后提交。
- 旧 P2b 本地 permissive 确认路径为兼容保留，不是签名 P2c 激活路径；消费者迁移和回滚验证后再移除。
- 签名 key 需独立、每环境至少 32 字节，稳定保留到预期凭证过期；本轮只使用测试 key，不从 JWT/模型凭据派生。
- 未提交旧凭证在 key 轮换后被拒绝；原已提交精确动作可以返回原回执，未知结果不得重新签发来重试。
- 生成客户端补齐正式来源里已有的 openConversation/streamRunEvents 声明；没有改变原业务接口或额外开放客户端权限。
- 本地 API 测试使用 TestClient、真实私有 PG 和 FakeProvider，不是云或真机证据。

## Operator Actions

- 审查 feat/p2c-trip-confirmation 的精确 base/head；#147 的审查替代授权不视为本新 PR 自动批准。
- 启用真实签名路径前须明确目标环境及独立 key 的安全注入/轮换清单并由 JT 授权；当前未执行凭据变更，也不要求把秘密贴入聊天。
- 云 OTP/数据库、真实模型调用和真机操作按具体后续清单单独授权。

## Next Smallest Action

- Action: 完成 feat/p2c-trip-confirmation 的精确 head 四 job CI 与审查；通过后从最新 main 接入 iOS 原动作持久化、准备响应校验和显式确认 UI，随后处理 MESSAGE 发送许可。
- Expected observation: 确认准备/原动作事务有 CI 与审查证据，客户端保持旧回执兼容；真实 key/外部写入不因代码合并自动获准。
- Resume command: `gh pr checks feat/p2c-trip-confirmation --repo JTCAO515/G2C`

## Rollback

revert 本确认凭证切片合并提交；没有迁移、云配置或数据变更。已有 Trip/actions 回执格式未变；默认旧本地入口继续兼容。

## Mandatory Reading Order

1. [HANDOFF.md](HANDOFF.md)
2. [docs/dispatch/P2-walking-skeleton.md](docs/dispatch/P2-walking-skeleton.md)
3. [docs/adr/0004-delivery-flow-and-repo-hygiene.md](docs/adr/0004-delivery-flow-and-repo-hygiene.md)
4. [backend/README.md](backend/README.md)
5. [README.md](README.md)
6. [AGENTS.md](AGENTS.md)

## Integrity Check

```bash
python3 -B scripts/handoff.py check
```
