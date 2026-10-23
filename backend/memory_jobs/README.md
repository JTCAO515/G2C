# CJ020 内部 memory-jobs 候选

本模块仅处理已提交聊天来源的增量整理与会话结束补充摘要的本地队列状态。
不依赖正式 Trip，不调用模型，不检索/生成有效资料，不保存 CJ011 条目，
不创建来源授权。`production_queue()` 无条件拒绝；未注册 API、worker 或部署。

## 运行限定检查

在仓库根目录执行，无第三方依赖、网络或既有数据库：

```sh
PYTHONPATH=backend/memory_jobs:backend/message python3 -m unittest discover -s backend/memory_jobs/tests -v
```

输入直接消费固定 Git 中 `cj_message.domain.Cursor / HistoryMessage / Receipt /
Command` 公共类型。来源绑定包含原 scope、conversation、generation、epoch、
after/through、source_version 与 MEMORY scope epoch；这些值仅供对比，不是授权。
原 MESSAGE bytes/hash/message ID/连续 sequence 全部验证。单批 1–100 条、
单消息最多 32 KiB、编码后最多 256 KiB；候选 UTF-8 最多 16 KiB，
每 scope 本地 ledger 最多 1000 个 job，不自动淘汰旧幂等记录。
这些是内部候选边界，不是已接受的产品留存/费用策略。

## 状态与恢复

- `pending → inflight → completed`；`inflight → unknown → completed`。
- `inflight/unknown` 不可重派或换 attempt。第二次 begin 即使同 ID 也拒绝。
- enqueue 同 job/attempt/原 bytes 返回原状态；任一输入不同冲突。
- 同来源代次、整理模式仅容许一个未完成区间；首区间 after 必须为 0，
  后续 after 必须等于持久处理游标。未知 attempt 不推进游标。
- 增量与会话结束是两种独立处理目的，各有游标；后者只补充候选。
- 完成原候选与游标在同一 SQLite 事务；重复完成只接受相同候选 bytes。
  旧回执重放不倒退游标。完成状态不等于“记住”。
- 显式 `LocalStore(path, create=True)` 只接受不存在的新文件；重开只接受
  本模块 marker 的原文件。不扫描环境、不接 PostgreSQL、不应用共享 schema。
- commit ACK 不确定时关闭连接，报告 CommitUnknown；重开原文件并查原
  job/attempt。若根本没有该记录，absence 不授予重发权。
- 进程重启保留 inflight，显式 recover 原 attempt 转 unknown；没有自动恢复
  worker、租约超时重派、provider retry 或后台线程。即使 peer 仍在途，recover
  也不会发第二次工作；原结果只能在当前 source fence 下完成同一个候选。

## trusted host 尚未接通

`InternalQueue` 是可信服务端代码入口，不能绑定请求 JSON/用户 bool。
内部 `host.guard(source)` 必须核验当前明确启用的原来源区间及归属，并将
MESSAGE/source/MEMORY 生命周期锁保护到本地事务完成；`lease.current()`
在事务首尾提供同一 Source 对比值。guard 退出失败报告 CommitUnknown，
已提交的本地候选可能存在；接口不返回候选内容，更不自动发布有效资料。

当前只有测试 `SyntheticHost`，它不是授权实现。生产入口保持硬关闭，
不能把 Python 对象/持久 Source/同意文字/单条 manual save 当生产 capability。
Python 模块内部结构不是防恶意服务端代码的安全沙箱。

停用后 host 拒绝新 enqueue/begin/complete；source_version、MESSAGE epoch /
generation 或 MEMORY epoch 变化拒绝旧结果。相同 fence 的暂时暂停/重开只允许
原 attempt 核对，已开始的 attempt 不能再次 begin。生命周期恢复若已增加 epoch，
旧绑定连 status 查询也拒绝；跨 epoch/停用状态的只读原账本核对尚需 owner seam，
不降级为跳过 fence。未实现过期时钟、源范围启用 UI、生产撤回锁或真实存储组合。

候选文本属于资料，不能变更权限、账号、工具或正式条目。此模块只存 bytes，
没有 prompt 或 active context 出口；未来消费者必须按 MEMORY 当前版本/撤回
及确认规则重新核对，不能直接注入或 promote。本地候选清理与保留政策未固定，
因此不得在真实个人数据环境启用。精确请求见 contracts/memory-jobs/SEAM.md。
