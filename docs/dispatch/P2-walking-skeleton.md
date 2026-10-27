# 派工单：P2 主线打通（walking skeleton）

- 状态：**P2a #143、P2b #145、P2c 壳 #146 已合并**；#146 由 JT 明确同意后合并。当前推进 **CJ-010 / #11 的 P2c SSE 读取切片**；发送、确认凭证、OTP 和真机完整链路未完成。
- 依据：[ADR-0004](../adr/0004-delivery-flow-and-repo-hygiene.md)（accepted）、[ADR-0003](../adr/0003-state-and-recovery.md)、[scope](../scope.md)、[handoff](../handoff.json)
- base：main `9ac8e1b`（P1 合并后）

## 目标（Objective）

让一条真实链路跑通：受邀用户登录 → 在助手里发一条中文或英文消息 → 单主 Agent 调模型流式回答 → 生成一份可审阅的北京行程草稿 → 用户接受 → 写入正式行程并能读回。每一步都使用已有领域模块和迁移链，不另开第二套权威。

## 范围（Scope）与切片

| 切片 | 内容 | 对应 Issue | 本单状态 |
|---|---|---|---|
| **P2a** | 模型 provider adapter（Fake 与 DashScope 兼容接口）；RUN worker 消费 MESSAGE pending 并写 RUN 事件；SSE 流式端点 `GET /v1/run-events`；本地组合 app（真实 PG、本地开发签名密钥）；端到端测试 | CJ-009、CJ-010、CJ-002（真实调用除外） | **已合并 #143** |
| P2b | 草稿：模型输出结构化北京行程 → 校验 → TRIP proposal；接受或拒绝走既有 `/v1/trip-actions`；正式行程读回 | CJ-014、CJ-015 | **已合并 #145** |
| P2c | 真实身份：Supabase 邮箱 OTP（`SUPABASE_ACCESS_RC1` profile）；iOS 17 App 主 target 接入 `ShellView` 四 Tab，调通 P2a/P2b；真机中英各跑一遍 | CJ-007、CJ-006、CJ-026 局部 | **#146 仅交付 CJ-006 壳接入切片**；其余未验收 |

## 反目标（Anti-goals）

- 不做多模型、多框架抽象；只有一个 `ModelProvider` 接口和两个实现。
- 不在 P2a 引入 AgentScope 或 DBOS 运行时：RUN 已有持久状态机和恢复语义，P2a 用它做持久化；框架是否引入，等 P2b 的工具调用需求出现时再按 ADR-0002 评估。
- 不盲重试模型调用：进行中的 run 在 worker 重启后标为 `unknown`，不重新发送（ADR-0003：费用和结果未知时先对账）。
- 不让客户端或模型直接写正式行程；草稿只能经 TRIP proposal 和用户接受写入。
- 不在仓库、日志、聊天或 PR 中出现任何真实 key 或 token。

## 负责人（Owner）

JT（operator，决策和外部资源）；Codex（实现、测试、交付；JT 于 2026-10-27 明确移交 #146 写权）；Claude（架构、规划和独立审查）。原“Codex 暂停期间”安排已被本轮指令替代。

## 已确认事实与用户决策

- 产品边界见 ADR-0001；P2 范围值：北京、邮箱 OTP、iOS 17（JT，2026-10-27）。
- 模型：`qwen3.8-flash`，北京 DashScope 兼容端点（`spikes/runtime/REPORT.md`）；JT 已授权百炼测试费用（不设上限，由余额控制）。
- JT 指明模型 key 已存入钥匙串 `g2c-dashscope`。P2b 原作者记录真实 provider smoke 4/4；本轮未读取 key 或重复调用。历史费用授权不作为本轮新增调用依据。

## 待验证假设

- DashScope 兼容端点的流式响应符合 OpenAI chat completions SSE 格式（`data: {...}` / `data: [DONE]`）。P2a 用 MockTransport 验证解析，真实格式等 operator 注入 key 后再验证。
- 用轮询 RUN 快照（run-display 已审读取路径）生成 SSE，延迟可接受（P2a 用 200ms 间隔）。

## 架构（P2a）

```
POST /v1/messages ──► MESSAGE.receive（事务内入 pending） 
                                │
            scripts/run_worker.py（host 进程）
                                ▼
   RunWorker.process(scope)：pending receipt → RUN.accept → started
        → ModelProvider.stream(...) 每段 → text_delta → completed | failed
        → 重启时发现 running 且无终态 → unknown（不重发）
                                │
GET /v1/run-events?message_id=  ◄── DisplaySnapshotReader.read（同一 MESSAGE 鉴权）
   SSE：event: delta / status，id: 文本偏移；终态后关闭；支持 Last-Event-ID 续读
```

- 新包 `backend/agent/cj_agent`：`provider.py`（`ModelProvider`、`FakeProvider`、`DashScopeProvider`）、`worker.py`（`RunWorker`）。
- `backend/cj_api/run_events_routes.py`：SSE 端点；`backend/cj_api/local_app.py`：本地组合（`CJ_ENV=local`，PG 连接来自显式 JSON 文件，开发签名密钥来自 `.local/dev-auth/`）。
- `scripts/dev_auth.py`：生成本地开发密钥对、签发短期开发 token（仅本机，仅 `CJ_ENV=local`）。

## 接口（冻结于本 PR）

- `GET /v1/run-events?message_id=<id>`，`Authorization: Bearer <token>`，可选 `Last-Event-ID: <已收文本字节数>`。
  - 200 `text/event-stream`。事件：`event: delta` + `data: {"text": "..."}` + `id: <累计文本 UTF-8 字节数>`；`event: status` + `data: {"status": "<queued|running|completed|failed|cancelled|context_invalid|unknown>"}`。到达终态后发一条 status 并关闭。
  - 错误沿用现有错误体：401/403（鉴权）、404（无此消息）、503（依赖不可用）。
- `PUT /v1/conversations?conversation_id=<id>`（实施中新增）：幂等地创建当前用户的会话，返回 `{request_id, conversation_id, generation, last_sequence}`。已停用的会话不会被重新激活（503）。原因：MESSAGE 规定"会话不存在时拒绝"（有意设计，防止写错的 id 隐式生成会话），但原来没有任何创建会话的入口。
- MESSAGE 领域新增 `Service.open_conversation` 和 `Service.acknowledge(receipt)`（worker 在 RUN 到达终态后确认投递；幂等，不删除数据）；表结构不变，迁移 hash 不变。
- `ModelProvider.stream(messages: list[dict]) -> Iterator[str]`；异常：`ProviderFailed`（确定未计费或已明确失败）、`ProviderUnknown`（结果或费用未知）。
- 环境变量（沿用 engineering.md 拟议名）：`CJ_MODEL_API_BASE_URL`、`CJ_MODEL_ID`、`CJ_MODEL_API_KEY`（仅服务端；缺任何一项时 worker 拒绝使用真实 provider）。

## 验收（Acceptance）

1. `scripts/test.py`：provider 单测（Fake；DashScope 流式解析、超时、非 200、截断、`[DONE]`，全部用 MockTransport）。
2. `scripts/pg_suites.py e2e`：空库 → 迁移 1–10 → 本地 app（真实 PG、开发 token）→ POST 中英消息 → worker（FakeProvider）→ SSE 收到完整文本和 `completed`；断线后带 `Last-Event-ID` 续读不重复；第二个用户看不到第一个用户的消息（404）；worker 在 running 中途"崩溃"后重启，run 变为 `unknown`，provider 调用次数不增加。
3. 当前 CI 的 python、postgres、swift、ios-app 四个 job 全绿；合并还需 Claude 独立审查或 JT 明确同意。
4. 真实 provider：P2b 原作者报告 smoke 4/4；本轮 **UNRUN**，不等同 App 真实端到端。

## 验证命令

```bash
uv run --locked python -B scripts/test.py
uv run --locked python -B scripts/pg_suites.py e2e migrations
```

## 风险

- 轮询式 SSE 在高并发时会放大数据库读取；内测规模可以接受，公开首发前改为 LISTEN/NOTIFY 或事件推送。
- 本地开发 token 只用于 `CJ_ENV=local`；P2c 之前不存在真实用户鉴权。
- 模型输出不可信：P2a 只保存和展示文本，不执行工具；P2b 加结构化校验后才能生成 proposal。

## 回滚

revert 本 PR 的合并提交。不涉及迁移变更（P2a 不新增表），不涉及外部资源。

## Operator 事项（JT）

1. **DashScope key 已由 JT 指明配置在钥匙串。以下仅为历史设置/撤销说明，不要求重建或覆盖。** 不要把 key 发到聊天、写进仓库或任何文档。
   - 前置：百炼控制台已有北京地域 workspace，账户余额充足。
   - 步骤：在百炼控制台新建一个专用 API Key，名称写 `g2c-local-test`；在本机终端执行 `security add-generic-password -a "$USER" -s g2c-dashscope -w`，回车后粘贴 key。
   - 预期结果：钥匙串中出现 `g2c-dashscope` 条目；之后由 `scripts/run_worker.py --real` 在运行时读取，不落盘。
   - 验证：`security find-generic-password -s g2c-dashscope >/dev/null && echo ok` 输出 `ok`（不会显示 key 本身）。
   - 回滚：在百炼控制台删除该 key；`security delete-generic-password -s g2c-dashscope`。
   - 常见错误：key 建在了非北京地域；复制时多了空格或换行。
2. **Supabase 测试项目已由 JT 提供**（ap-southeast-1，PG17），不再要求新建。只读信息不代表配置、RLS 或 OTP 验收；任何云写操作先列目标、操作、验证、回滚并等 JT 确认，不在聊天中索取秘密。

## 强制阅读顺序

1. `HANDOFF.md`
2. 本派工单
3. `docs/adr/0003-state-and-recovery.md`
4. `backend/run/cj_run/core.py`、`backend/message/cj_message/domain.py`、`backend/run/cj_run/display_snapshot.py`
5. `backend/README.md`

## P2b 实施记录

- `cj_agent/draft.py`：模型用第二次调用（`DRAFT_SYSTEM`）返回严格 JSON `{title, items[]}`，服务端规范化成 TRIP 文档。所有条目都是 `pending` 且没有 evidence，模型文本一律不算已核实。不合法就整份拒绝，不做"修复"。
- 只有消息的 `creation_intent` 为 `consider_trip` 时才生成草稿。`proposal_id = p-<run_id>`，客户端从消息回执里的 run_id 就能直接查到；`trip_id = trip-<run_id>`（每份草稿是一个新行程，expected_version 为 0）；有效期 7 天。
- 草稿通过受信的 `publish` 入口写入，并在 RUN 里记一条 `effect_committed: trip_proposal:<id>`，之后才写 `completed`。草稿失败或结果未知不影响回答本身。
- 本地确认校验：在本地环境下，已登录本人发起的接受或拒绝动作即视为确认；候选 hash、有效期和期望版本仍由 TRIP 校验。服务端签发、在 UI 中展示的确认凭证属于 P2c。
- 真实 provider 验收（`scripts/provider_smoke.py`，2026-10-27）：中英文的回答和草稿 4/4 通过，两份草稿都通过 Proposal 校验。

## 唯一下一步

完成本轮 SSE 读取切片的四 job CI 和 Claude 独立审查；Claude 同时明确下述写入激活方案，再由 Codex 接续发送/确认切片。不得以只读链路通过宣布 P2c 完成。

## P2c 壳接入切片（PR #146）

- base：`865f6f33c1b3f813bc71bd96faf8558683dd107b`；最终 head 及检查以 PR 描述为准。
- App 入口持有 `ShellState` 并展示 `ShellView`；包直接依赖同级模块和 `ios/` 根包，App 锁文件随实际依赖图更新。两个 Binding setter 改用闭包。
- 验收范围：App 构建、启动、四 Tab 和双语切换，默认未连接服务状态如实呈现；不能关闭 CJ-006 整票或 P2c。
- #146 原始 head `788b5001d97ec2c03b70a44e20b306fa94352531` 的四 job 已通过；后续 head 须重新读取 CI，最终证据见 PR 与 handoff。
- 首次本地构建因依赖克隆 TLS 失败；改用系统 Git/已有缓存后构建通过。真实 API、OTP、provider 和真机均未在本切片重跑。
- handoff 改由仓库内 `python3 -B scripts/handoff.py render/check` 生成/检查，不再依赖不存在的 npm 入口。

## P2c 流式读取切片（CJ-010 / #11）

- base：`15020fb1630488df243824d64c7e8801e0a14219`（#146 合并提交）。
- 复用 RunDisplayModel、原消息回执、SessionOperation 和 NoRedirectTransport；新增显式 SSE GET/续读，不更改服务端接口或正式数据。
- 按 UTF-8 字节续读；身份失效清空展示，断流保留已验证的部分正文并标未知，终态后必须读回受保护快照。冻结的 MESSAGE/TRIP 写入门禁保持关闭。
- 验收：RUN 模块全套测试、App 构建；本地真实 Swift HTTP → FastAPI → 全新私有 PG 的中英文读取和跨用户拒绝。模型是 FakeProvider，真实 OTP/provider/真机仍 UNRUN。复现入口见 `ios/Modules/CJRunClient/README.md`。

## 写入激活待决（交 Claude，不是已批准方案）

源码与旧模块说明的实际阻塞必须先解决，不能当成普通按钮接线：

1. `ios/Modules/CJMessageClient/ACTIVATION-GATE.md` 明确禁止 live POST；`MessageHTTPClient` 的生产入口和 `NoRedirectTransport` 均拒绝写入。已恢复的 staged、receipt 查询的 null、新 key 或新 ID 都不是首次发送许可。需要 Claude 固定服务端不可回退的原动作/epoch 证据、账号/环境绑定、保留期、首次许可和重启/备份恢复/unknown 对账语义；不得把 live transport 塞进 test interceptor。
2. `TripClient.acceptsUserActions` 仍为 false，`TripPending` 只允许模块内部测试构造。需要 Claude 固定服务端确认凭证的签发、绑定和校验：已认证用户、原 proposal/content hash、expected version、accept/reject、有效期及原 action ID；同事务校验和幂等回执继续由 TRIP 执行。客户端读取草稿不等于确认，不能自行造 confirmation_ref。
3. 建议在既有 PostgreSQL 业务权威内完成，新增版本迁移和必要的增量 API；不引入第二份正式状态，不改已应用迁移。具体字段/接口、迁移范围和兼容策略尚未批准，当前切片不实现这些写入。
4. 方案验收至少覆盖：未知提交先查原动作且不换 ID、旧快照不能恢复发送许可、同动作并发一次提交、错误账号/内容/版本/过期确认拒绝、退出后晚到结果不回填。云数据库、OTP 邮件及真实模型调用另列操作清单取得 JT 授权。
