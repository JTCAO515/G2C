# CJ020 精确缺口与固定输入

实现基线：G2C `8ea1b35756726f60727f10deaf157c40b8df1072`。
Issue：<https://github.com/JTCAO515/G2C/issues/23>，CJ020。
Issue 原 planning 文案不撤销本轮 Main 的有限内部代码授权。

可用公共输入（仅固定 Git，未从其它 owner dirty 树取值）：

- `backend/message/cj_message/domain.py`：Command、Receipt、Stored、Cursor、
  HistoryMessage。scope/conversation/generation/epoch/through/after 与原消息
  sequence/hash 可用于精确绑定；没有历史整理启用权。
- `backend/message/HISTORY-CONTEXT.md`、`CONTEXT-QUERY-MESSAGE.md`：
  `Boundary.with_history_context` 的短生命周期公开受保护读取；没有批量历史整理
  consent/withdrawal issuer，不使用 `_service` 或 SQL 绕过。
- `backend/memory/cj_memory/domain.py`：source_version、candidate/active、
  current_context scope epoch 与发布前 fence；源码只读，没有调用 save/effective。
- `backend/memory/cj_memory/lifecycle.py`：同事务 lifecycle adapter 与原动作
  核对要求；不把 manual source 或暂停动作解释为授权全聊天。
- `docs/memory.md`、原 Issue #23：摘要为派生、推断须确认、停止/撤回防复活。

最小内部 Source 形状仅描述上述原始绑定与 MEMORY epoch 的比对值；它不是
新的公共 source 类型、MEMORY source_id 命名政策、权限或跨域已冻结 schema。
新 SQLite 表只在本模块新建的隔离本地测试文件使用，不注册共享数据库或部署。

## 请求原 owner 固定的最小公开 seam

1. SOURCE/MESSAGE/MEMORY：由 trusted host 验证的**明确启用来源区间**读取能力，
   给出原 principal→scope 绑定、conversation generation/epoch、允许的连续
   message sequence 区间，以及可核对的 source version / withdrawal epoch。
   说明范围启用、停用、重新启用如何改变版本；不可从文本或 manual source 扩权。
2. 该能力在提取/落候选/将来发布各阶段如何持有或重新核对 canonical scope 锁；
   MESSAGE/history 与 MEMORY source 共享撤回时的锁次序/失效语义。
   提供公开 callback/guard，不暴露私有 repo/tx，也不新建第二 authority。
3. 原 attempt 的**只读**核对能力：停用或 epoch 改变后，当前同账号可否查询旧
   job 的状态及必要来源引用；它必须独立于重新提取/恢复派发权限，不能靠旧
   source fence 或假装 active 绕过。当前内部实现仅支持仍被 host 验证的原 fence。
4. RUN/USAGE：原 attempt 的 dispatch/claim/cancel 与预算准入公开类型、绑定及
   unknown 对账回执。未固定前无模型 dispatch；队列 begin 仅本地状态变化。
5. MEMORY/CLEANUP：派生候选到 canonical source 的精确关联/清理与留存边界，
   清理失败恢复和撤回防重提取规则；确认前不 promotion，不写权威条目。

缺口只阻真实启用/dispatch/源组合/跨 epoch 恢复，不阻本地 codec、状态机、
幂等 ledger 与 unknown 恢复。没有正式 Trip 来源字段，不构造旅程决定。
未来已接受 seam 到位时替换测试 host，先核当前原 owner 固定版本及消费证据，
不能直接将测试 host、dataclass 或序列化 bool 用作生产授权。
