# MESSAGE-TRAVEL-LEASE@1 — frozen

JT 2026-10-30 批准 #273 r1。B 提供 MessageContextAuthority：
read_original(binding)、hold_for_effect(binding)、hold_current(selection)、valid(binding)。
原 binding 必须匹配 canonical owner/message/run/generation/hash/sequence。

hold_for_effect 在原 RUN 临界区按 RUN→MESSAGE→TRAVEL 取得 scope/context FOR SHARE，
核 chat/原 ref/选择 epoch/active/version。lease.reference 为不可变原关联；
lease.original_message() 复用同连接已验证 Stored；不能持锁再另开 Message.query
的 M 写锁连接。lease.check 每次 fresh AUTH，仅原线程/原 binding/with 生命周期可用。
valid preflight 使用短 lease；effect 内重入同 lease/连接，不缓存 ALLOWED 或造签名。

后续持锁顺序 MEMORY→NEEDS→USAGE，USAGE 短事务释放后再执行最终 guard。
组合 B/C live 检查进入既有 PreparedCall.guard，唯一 MeteredExitCore 的最终
finite/单调/max_seconds clock 检查后直接 invoke；不另发计量版本或复制算法。
已存在 NEEDS→USAGE 持锁边，不能声称旧全局图是 RUN→USAGE→NEEDS。

lease 覆盖实际 provider 新步骤、text_delta/completed/proposal/effect 与原 RUN commit。
final 失效拒绝新正文/派发/effect；原 failed/cancelled/context_invalid/unknown/
budget_denied 诊断记账仍以 owner/origin/RUN fence 处理，无须失效 context 重新许可。
started 前依赖未知保留 queued/未 ACK；不加 queued→unknown 转移。
claim 后未知/失效保留原 exposure，不因 provider=0 退款。历史费用核原 attempt/period。

typed Memory 未就绪时不得以当前 conversation-only MEMORY-RUN-CONSUME@1 或
静默关闭 Memory 冒充旅行隔离。B 的无 Memory scope L1 只能证明身份/引用/lease，
不证明 C 的记忆业务。取消、重启、两种锁序、租约逃逸/跨线程均须真实 PG/worker 验证。
