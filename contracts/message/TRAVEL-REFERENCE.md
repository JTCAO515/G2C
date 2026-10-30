# MESSAGE-TRAVEL-REFERENCE@1 — frozen

JT 2026-10-30 批准 #273 r1。原引用只在 message 被接受时固定。
私有 OriginalMessageContextRef 字段为：owner_scope、conversation_id、generation、
message_id、run_id、sequence、input_sha256、message_version、context_kind、
context_id、context_version、selection_epoch。仓储在 DB 读边界一次验证原
receipt/raw hash/复制列，不接受客户端上传该对象作证明。

context_kind=travel 时 C 消费 `ContextRef(kind="travel",id=context_id)`；
none 时只给长期值；legacy 显式使用 conversation namespace，不回退或猜测。
C typed FK 目标固定 `public.cj_travel_context(scope,context_id) ON DELETE RESTRICT`，
不 FK 到可变 version；MESSAGE/MEMORY canonical scope 使用同一 scope_for。

原 message ref 永不 UPDATE/DELETE。选择历史复用唯一键
`(scope,conversation_id,generation,sequence)`，不另建 mutable selector。
最新 ref 必须与 chat head 对应；effect 必须核原 epoch 仍为当前 epoch。
历史 read_original 不是 live permit。wire 投影不暴露私有 owner_scope，不能凭
wire 的 ID/hash/版本调用内部 lease。所有示例为合成，实际 C/A 集成另在 #227/#228 验收。
