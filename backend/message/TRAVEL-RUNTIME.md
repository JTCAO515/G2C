# 本地旅行上下文运行

仅 `CJ_ENV=local`、新私有 PG、既有本地测试身份与 FakeProvider；不应用到云/Supabase。
契约与具体 schema 为 #273 / migration0018。没有真实外部调用或费用许可。

先使用既有本地 M2 `CJ-LOCAL-RUN@2` operator 初始化账户；不改 period、重置 ledger
或将 UNKNOWN 清零。旅行身份 API 可先于聊天/Trip/NEEDS/计量账户创建。
停止旧 worker 并部署支持四新契约的兼容代码后，显式激活一个原 scope：

```sh
uv run --locked python -B scripts/dev_auth.py activate-travel \
  --conninfo-json <local-connection.json> --subject <existing-local-subject> \
  --run-context <M2-context.json> --consumer-abi MESSAGE-TRAVEL-CONSUMER@1
```

该命令不读 key、不创建身份/账户、不初始化预算；校验原账户，M 写锁及 DB trigger
拒绝所有未 ACK delivery（包括 inactive chat）和 queued/running RUN。profile 单向且
runtime 无 INSERT/UPDATE 权。幂等重复已有 profile 不重置任何原状态。

API 组装显式设置 `CJ_LOCAL_TRAVEL_CONTEXT=message-travel.1`；worker 同一变量或
`--travel-context message-travel.1`。只识别此值，缺配置在新 scope 拒绝派发。
标记是兼容能力，不是 AUTH；每个连接仅 LOCAL 绑定，checkout 拒绝残留标签。

`POST /v2/messages` 固定原 travel_context / needs_reference / 选择 epoch；
`GET /v2/message-send-status` 读取 receipt/head/reference。SEND-V2 和原 reference
合同分别见 contracts/message。无旅行是显式 null，不回退 conversation current。
新 RUN 读取为 `/v2/run-display`、`/v3/run-draft-status`，附原 reference；旧读拒绝新消息，
不剥掉引用。历史读取或原回执重放不产生执行许可。

B 内部 MessageContextAuthority 提供 read_original/hold_for_effect/hold_current/valid；
lease.reference、lease.original_message() 在同连接生命周期内使用。实际持锁为
RUN→MESSAGE→TRAVEL→MEMORY→NEEDS→USAGE；U 短事务准备 deadline 数据，最后检查不做 SQL。
启动前依赖 UNKNOWN 保持 queued/未 ACK；已 claim 的 UNKNOWN 曝光不归零或重发。

无 Memory scope 的 L1 可证明 B 引用与真实 worker；既存 Memory 只能在 C typed
consumer 就绪后接入，当前 conversation-only @1 明确拒绝，不静默关 Memory。
C typed FK 键为 `public.cj_travel_context(scope,context_id)`，不引用可变 version。

兼容范围：plain domain Repository 默认 `travel_metadata=False` 保留原 candidate/旧 schema
测试；正式 local composition 显式打开 metadata reader，producer 还须显式 mode/M2。
这不是探测失败后 fallback。所有旧消费者迁移且验证后再讨论退休旧路径，本票不删除。
真实用户 cleanup/restore 仍等 #27；无 DELETE/TRUNCATE 或 destructive down。
