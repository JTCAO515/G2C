# CJ020 memory-jobs

## M3 PG 切片（#409）

新版 `cj_memory_jobs.local_app` 提供显式本地宿主，复用原签名身份校验和
MESSAGE-SOURCE@1；历史整理按会话默认关闭。只有明确 enable 动作持久提交后
才允许入队，manual 保存和消息里的启用文字均不改变授权。

PG 版本记录原动作/任务/attempt、精确输入、来源版本、撤回 epoch、原 Memory
epoch 与处理游标。开始和完成重新进入受保护来源，旧 Memory 版本也不能继续；
停用后查询原状态仍可进行，UNKNOWN 不自动派发。completed 只表示派生候选已存，
不表示正式 Memory 已生效。协议和正负例见 [PG-V1](../../contracts/memory-jobs/PG-V1.md)。

本地已验证真实签名 API、受限 PG、进程重建查询、实际 COMMIT ACK 丢失、
新鲜准入及空库往返/有数据 down 拒绝。追加 M34、registry 和清理钩子同 PR
交付；实际 worker/Meter 生产者由后续 #410–#413 接入。

```sh
uv run --locked python -m pytest -q -p no:cacheprovider backend/memory_jobs/tests
uv run --locked python -B scripts/pg_suites.py memory_history
```

清理沿用 CLEANUP@1.1 和 #402 的专用角色/原结果账本；生产者不取得清理权限。
删除后仅保留 scope 的 SHA256 与 erased 屏障，不保留账号 scope 明文。
账号范围钩子不得被当作已完成单条 Memory 的物理删除；条目关联和 #26 仍须交付。
真实模型、云、费用、真实账号和 App/设备验收保持 UNRUN。

本地 M3 API 的显式入口为 `cj_memory_jobs.local_app:app_from_environment`。
它沿用已有 `CJ_LOCAL_CONNINFO` / `CJ_LOCAL_AUTH_DIR`，并保留旧 app 入口。

## 增量发布与候选确认（#410）

协议及可执行正负例见 [CANDIDATE-V1](../../contracts/memory-jobs/CANDIDATE-V1.md)。

`collection_app.create_collection_app` 显式注入服务端提取/保存策略；没有默认
宽松策略，也没有接收模型输出的 HTTP 入口。受保护原来源下的输出检查点、
正式 Memory 原动作、来源关联、任务完成及游标推进使用同一 Memory 事务。
同源 ID 取自原消息版本和 canonical subject/slot/extent/context，不取模型措辞、
语言、job 或输出顺序；同源不同值冲突，不能另造 ID 覆盖用户更正。

事实、经历、偏好经原文本独立判定为直接陈述后才能生效；推断保持候选。
用户确认必须给出候选版本、Memory epoch 和审核后的具体 kind/text；当前范围
还须 B 的真实 Travel 租约。确认产生新来源，原自动操作回执仍是历史候选。
拒绝不生效，过期候选仍可拒绝；重放不重新授权或激活来源/行程。

实际签名 API、受限 PG、输出/发布/确认 COMMIT ACK 丢失、跨账号、过期拒绝、
实例重建、当前 Travel 版本及同域清理在 `tests/publication_pg.py` 验证。
这些测试提供固定输出，不代表实际 worker、FakeProvider 或 Meter 已接通。
自动 current 发布需要 #403 的 MESSAGE→Travel→Memory 联合租约；实际模型出口
和后台任务绑定仍由 #410–#413 后续交付，不能从测试的手工来源关联推导完成。

公开 `CleanupHook` 同时清除输出检查点、用户决策及原消息引用；只保留既有
不含账号明文的擦除屏障。单条删除/旧聊天重提取防复活仍由 #26 交付。

历史和 collection 独立宿主均消费 B 的 `ACCOUNT-ADMISSION@2` 公开工厂，
每次以运行角色重新读取原账号 fence，不取清理角色或回退到旧邀请检查。
原注销确认已提交但权威 Memory 尚未物理删除时，同 token 即被拒绝；
准入查询不确定返回 UNKNOWN。该组件验证不代表完整账号/设备清理完成。

`prepare_model_input` 在原 inflight 任务的当前受保护来源里编码有界请求；
固定 system 不插入历史文本，原文只在单条 user JSON 资料消息内。
结束整理保留 B 的真实稳定 end_id；已存输出、完成或旧 Memory basis
不能重新准备输入。这些 bytes 不保留来源租约，也不授权模型调用或重发；
实际 worker 仍须在唯一 Meter 出口做新鲜准入与来源检查。

新的实际后台生产者显式消费 [PROCESSING-V2](../../contracts/memory-jobs/PROCESSING-V2.md)：在模型前及
阶段提交前按当前来源关联屏蔽暂停/撤回/过期和已明确审核的旧原文，模型只见
opaque ref；V2 输出回映原证据，同源标识不变。全部原文被屏蔽时拒绝进入
claim 回调，不伪造模型输出。V1 留作原独立兼容路径，不作失败后的 fallback。
单条物理删除后的 noncontent tombstone、原聊天防复活与全部清理仍由 #26 交付。

## M3 自动增量与长会话结束段（#410/#411）

显式宿主以 [PRODUCER-V2](../../contracts/memory-jobs/PRODUCER-V2.md) 的
IncrementalProducer / ProducerHost 接原 run_once 和 B RUN-BACKGROUND@2。
默认关闭、实际来源/游标、原 pending bytes 和 UNKNOWN 零自动重派沿用同一队列。
新 writer 安装 MemoryCollectionAdapterV2，以 C factory3 在实际提交前检查原预算。

[ENDING-JOBS-V1](../../contracts/memory-jobs/ENDING-JOBS-V1.md) 用真实不可变
完整结束头核验后读取 1–100 条段；长会话可按 100+1 持久处理，原 end_ref 不变，
增量与结束各自游标，同源仍复用同一 canonical 操作。没有新表/派生索引或清理角色。
[CANDIDATE-DISCOVERY-V1](../../contracts/memory-jobs/CANDIDATE-DISCOVERY-V1.md)
让 App 从受保护聊天发现真实首次 producer 的 job/attempt，再走现有候选读取/确认。

实际签名 API、受限 PG、自动增量/结束段、原 worker/唯一 Meter/Fake、候选确认和
下一轮/新中文会话的真实模型输入分别有组合测试；真实模型质量仍由 #32 承接。
完整结束调度、正式 Trip 决定 intake 与 #26 物理删除/防复活不因此视为全部完成。

## 保留的 SQLite 隔离候选

本模块仅处理已提交聊天来源的增量整理与会话结束补充摘要的本地队列状态。
不依赖正式 Trip，不调用模型，不检索/生成有效资料，不保存 CJ011 条目，
不创建来源授权。`production_queue()` 无条件拒绝；未注册 API、worker 或部署。

M3 C 从 #409–#413 推进 PG 受控路线，设计见 [M3-DESIGN.md](M3-DESIGN.md)。
`history.read_committed_batch` 通过 MESSAGE 公开 `with_history_context` 读取
并编码一个精确的已提交区间，编码在最终 AUTH 检查前完成。它没有新存储，
所得 bytes 不是历史整理授权或派发许可；#402/#403 未接通前生产入口仍关闭。

### 运行限定检查

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

### 状态与恢复

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

### 旧候选的 trusted host 限定

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
