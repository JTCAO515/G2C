# TRAVEL-CONTEXT@1 — frozen

JT 于 2026-10-30 整体批准 #273 r1（PR275 head
`0faa438a5389151735a720d5f08860faaa22ebc4`）。本版本冻结；仅限 local runtime，
不应用到 Supabase/云端。实施证据记 #273，不把冻结当运行 PASS。

旅行身份键为数据库 `(scope, context_id)`；scope 来自 canonical AUTH 的 owner
映射，不能由请求传入。context_id 为服务器生成的 32 位小写 UUID hex。
身份独立于 conversation，无需正式 Trip、NEEDS、Memory 或计量账户；不自动创建这些业务记录。

`POST /v1/travel-context-actions` 接收 `application/octet-stream` 原 UTF8 JSON bytes，
字段恰为 `version="TRAVEL-context-action.1"`、action_id（1–96 个非空白 ASCII
可打印字符）、operation、travel_context。create 的 travel_context 必须 null；
advance/deactivate 必须为 `{id, expected_version}`。版本为 1..int64_max 的真整数，
不接受 bool/float、重复或未知字段。请求受 host 显式 body limit 约束。

create 生成 active/version=1；advance 是同 identity CAS+1，保持 active；
deactivate CAS+1 后永久 inactive。本版没有 reactivate、owner 转移、物理删除。
推进版本失效旧运行引用，不重写 Memory/NEEDS 事实。动作、状态与原回执在 M scope
写锁内同事务提交。原 action_id+原 bytes 优先返回原回执；不同 bytes 为 INPUT_CONFLICT。

回执内层为 `TRAVEL-context-receipt.1`、action_id、operation、
travel_context `{id,version,active}`。`GET /v1/travel-context-actions/{action_id}`
返回该 owner 原回执或 null。null 不证明原动作未提交，不授权换 ID/自动重发。
`GET /v1/travel-contexts/{context_id}` 返回 `TRAVEL-context.1`、当前
`{id,version,active,created_at}`；读取和历史回执都不是执行许可。

错 owner/不存在统一 503 TRAVEL_CONTEXT_UNAVAILABLE，dependency/unknown；写用
reconcile_original、读用 retry_safe_read。已知 owned 版本过旧/停用为
409 TRAVEL_CONTEXT_CONFLICT，conflict/failed/reconcile_original。
commit ACK 未知为 503 TRAVEL_CONTEXT_OUTCOME_UNKNOWN，保留原 ID/bytes 查询。
输入错误 400 INVALID_INPUT；不同 bytes 409 INPUT_CONFLICT，均 failed/do_not_retry。
AUTH 沿现有 ACCESS_DENIED/ACCESS_UNKNOWN，不新增 BASE 枚举。

所有读写使用现有 MESSAGE Boundary 的 fresh entry/transaction/commit/return
同 principal 检查；owner 隔离和新 LOCAL ABI 同时成立，ABI 自身不证明权限。
正负例见 [travel-context-examples.json](travel-context-examples.json)，全部标记合成。
