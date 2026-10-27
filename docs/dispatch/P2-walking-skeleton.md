# 派工单：P2 主线打通（walking skeleton）

- 状态：**P2a 已实现，PR 待合并**（Claude 按 JT 要求执行；Codex 暂停）；P2b / P2c 待开工
- 依据：[ADR-0004](../adr/0004-delivery-flow-and-repo-hygiene.md)（accepted）、[ADR-0003](../adr/0003-state-and-recovery.md)、[scope](../scope.md)、[handoff](../handoff.json)
- base：main `9ac8e1b`（P1 合并后）

## 目标（Objective）

让一条真实链路跑通：受邀用户登录 → 在助手里发一条中文或英文消息 → 单主 Agent 调模型流式回答 → 生成一份可审阅的北京行程草稿 → 用户接受 → 写入正式行程并能读回。每一步都使用已有领域模块和迁移链，不另开第二套权威。

## 范围（Scope）与切片

| 切片 | 内容 | 对应 Issue | 本单状态 |
|---|---|---|---|
| **P2a** | 模型 provider adapter（Fake 与 DashScope 兼容接口）；RUN worker 消费 MESSAGE pending 并写 RUN 事件；SSE 流式端点 `GET /v1/run-events`；本地组合 app（真实 PG、本地开发签名密钥）；端到端测试 | CJ-009、CJ-010、CJ-002（真实调用除外） | **本 PR** |
| P2b | 草稿：模型输出结构化北京行程 → 校验 → TRIP proposal；接受或拒绝走既有 `/v1/trip-actions`；正式行程读回 | CJ-014、CJ-015 | 待开工 |
| P2c | 真实身份：Supabase 邮箱 OTP（`SUPABASE_ACCESS_RC1` profile）；iOS 17 App 主 target 接入 `ShellView` 四 Tab，调通 P2a/P2b；真机中英各跑一遍 | CJ-007、CJ-006、CJ-026 局部 | 待开工，需 operator 资源 |

## 反目标（Anti-goals）

- 不做多模型、多框架抽象；只有一个 `ModelProvider` 接口和两个实现。
- 不在 P2a 引入 AgentScope 或 DBOS 运行时：RUN 已有持久状态机和恢复语义，P2a 用它做持久化；框架是否引入，等 P2b 的工具调用需求出现时再按 ADR-0002 评估。
- 不盲重试模型调用：进行中的 run 在 worker 重启后标为 `unknown`，不重新发送（ADR-0003：费用和结果未知时先对账）。
- 不让客户端或模型直接写正式行程；草稿只能经 TRIP proposal 和用户接受写入。
- 不在仓库、日志、聊天或 PR 中出现任何真实 key 或 token。

## 负责人（Owner）

JT（operator，负责决策和外部资源）；Claude（架构、实施、审查，Codex 暂停期间）。

## 已确认事实与用户决策

- 产品边界见 ADR-0001；P2 范围值：北京、邮箱 OTP、iOS 17（JT，2026-10-27）。
- 模型：`qwen3.8-flash`，北京 DashScope 兼容端点（`spikes/runtime/REPORT.md`）；JT 已授权百炼测试费用（不设上限，由余额控制）。
- 当前未配置任何真实 key；真实 provider 调用为 UNRUN。

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
3. CI 三个 job 全绿。
4. 真实 provider：**UNRUN**，直到 operator 注入 key 后按下方步骤执行：`CJ_ENV=local CJ_MODEL_API_BASE_URL=<北京兼容端点> CJ_MODEL_ID=qwen3.8-flash uv run --locked python -B scripts/run_worker.py --conninfo-json conn.json --once --real`。

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

1. **注入 DashScope 测试 key（P2a 真实调用验收需要）。** 不要把 key 发到聊天、写进仓库或任何文档。
   - 前置：百炼控制台已有北京地域 workspace，账户余额充足。
   - 步骤：在百炼控制台新建一个专用 API Key，名称写 `g2c-local-test`；在本机终端执行 `security add-generic-password -a "$USER" -s g2c-dashscope -w`，回车后粘贴 key。
   - 预期结果：钥匙串中出现 `g2c-dashscope` 条目；之后由 `scripts/run_worker.py --real` 在运行时读取，不落盘。
   - 验证：`security find-generic-password -s g2c-dashscope >/dev/null && echo ok` 输出 `ok`（不会显示 key 本身）。
   - 回滚：在百炼控制台删除该 key；`security delete-generic-password -s g2c-dashscope`。
   - 常见错误：key 建在了非北京地域；复制时多了空格或换行。
2. **P2c 之前：** 决定 Supabase 项目归属和地域，按 CJ-007 新建隔离的测试项目（属于云资源，须单独授权）。

## 强制阅读顺序

1. `HANDOFF.md`
2. 本派工单
3. `docs/adr/0003-state-and-recovery.md`
4. `backend/run/cj_run/core.py`、`backend/message/cj_message/domain.py`、`backend/run/cj_run/display_snapshot.py`
5. `backend/README.md`

## 唯一下一步

P2a 合并后：P2b（草稿到正式行程）。
