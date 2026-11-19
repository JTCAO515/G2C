# 香港应用发布后的 API 冒烟

每次香港 API/worker 切换成功后立即执行。B 在同一个已登记的闲时维护段内操作，按 [JT 决定](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6972695033) 处理结果。调用许可限北京时间 08:00–23:00、M4 的既有香港测试环境和一名既有 C 合成账号。正式基础 8、全国 16 和 JT 本人真机复测另记。

1. 切换前确认 ECS 免费试用资格、现役和回退镜像、在途及原账。用原 C 合成账号的合法短期会话做脚本 `preflight`。这一步校验签名、受邀范围、会话覆盖整个窗口和既有 C 子额，业务请求数为零。会话被拒绝或期限不足时登记 UNRUN。
2. 应用单次切换并独立读回现役 source/image。锁定该版本和空闲维护段，使用现有 `probes/application-deploy.lock` 串行执行脚本。使用运行角色内的 `python -B -m deploy.hk.server_smoke run`，stdin 只接来自私有提供方的 `access_token`、`starts_at`、`ends_at` 三字段 JSON。运行输出放 0600 文件。已有版本可用独审通过的两文件原字节启动同一入口，不换应用运行镜像或启动配置。
3. 运行先把既有 C standing 的可用占用限制为本轮基线加 ¥5，保留原 C cap、归属和历史 hold。中英各单次提交身份、能力、北京三日游。每项用 `/v2/lio/messages` 在原 C 账号内显式创建新会话，收到原默认会话的回执时记 UNKNOWN。每轮从发送阶段开始约每秒读取 `/v2/lio/timeline`，收到回执后按新会话读。每项核原 MESSAGE 回执、用户可见答案和行程每天的地点与安排。最后用保留历史 `/v5/message-history` 分页读回原消息。首个 FAIL/UNKNOWN 后只保留原件，不重发。
4. 用 `verify` 读取 `events`（上述 JSONL 转数组）和同一现役 worker 同一窗口的无正文 `M4_MODEL_WIRE_TIMING` 行数组 `wire_logs`。RUN 与财务日志通过原 MESSAGE 绑定后的 attempt SHA 关联。要求一个原回答调用发出到供应商首包之间的连续区间在完整的读取记录内，该时长必须长于可避开完整 200 读取的最大间隔。没有重叠证据记 UNKNOWN。退出 0 为 PASS、1 为 FAIL、2 为 UNKNOWN、3 为 UNRUN。
5. 停止新请求、只读查原动作和全局在途。收尾同时报告保守占用、可计算 token/工具估算与实际实付。实付未核记 UNKNOWN，未结算原调用保留 hold。空闲和原账读回后，通过同锁执行 `restore`，stdin 接原 `restricted` 回执中的 `before`、`restricted`，加只读取得的 `drained_ledger`。归还仅恢复原 C standing，并保持全部尝试及 hold。收到不明确的状态先读原 cap 与账本。
6. PASS 登记现役和证据，再放行 JT 指定构建的真机复测。真实 FAIL 或 UNKNOWN 按已经确认兼容的回退包执行一次并独立读回。UNRUN 保持现役并记录原因。

预检、执行和收尾使用同一个合成账号。禁止把 bearer、邀请码、回答正文或完整 worker 日志放入票评论或 Git。费用字段以 10^-7 元为单位，现金账单列为实付。
