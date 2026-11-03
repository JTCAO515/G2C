# Memory jobs：当前契约与消费者

版本状态以 main 的实际调用为准。新代码使用下表当前入口；保留旧字节、回执和
既有证据，不为无当前消费者的旧模型路径新增测试或适配。版本号不是授权，
读取失败不得换旧入口、重建来源或重发 UNKNOWN。

| 契约 | 当前消费者与选择规则 |
| --- | --- |
| [PG-V1](PG-V1.md) | 当前：C PG consent/job/cursor；A 已合历史整理开关。JOBS1/HISTORY1 未被替换。 |
| [CANDIDATE-V1](CANDIDATE-V1.md) | Action1 确认/拒绝当前仍用，A463/C471 已合消费。文中的未过滤 DATA1/EXTRACT1 已被过滤 DATA2/EXTRACT2 替代，无当前实际后台 writer；只保留旧数据/回执兼容。不能把整个 Action1 一并标废弃。 |
| [PROCESSING-V1](PROCESSING-V1.md) | 旧未过滤模型路径已被 V2 dispatch + V3 publication 替代，无当前实际后台 writer；既有隔离证据保留，新代码不使用。 |
| [PROCESSING-V2](PROCESSING-V2.md) | 当前过滤输入/Data2：MemoryCollectionAdapterV2、GuardedCollectionAdapterV3。其 factory2 publication 已被 V3 提交尾部检查替代，无当前实际 writer 直接安装 factory2。 |
| [PROCESSING-V3](PROCESSING-V3.md) | 当前 publication 提交尾部：上述两个已合 adapter 必须传原 Meter before_commit；不是替换 V2 输入格式，也不新增 Data3。 |
| [PRODUCER-V2](PRODUCER-V2.md) | 当前普通增量/分段结束：C455/459 的 IncrementalProducer/MemoryCollectionAdapterV2，B RUN-BACKGROUND2。旧 EndingCollectionAdapter 无当前安装者，已被 V2 adapter 替代。 |
| [ENDING-JOBS-V1](ENDING-JOBS-V1.md) | 当前长结束段，原真实 end/独立游标；与增量 JOBS1 并存。 |
| [AUTO-ENDING-V1](AUTO-ENDING-V1.md) | 当前 ConversationProducer；C459/C471 原 worker 实际消费。 |
| [SCHEDULING-V1](SCHEDULING-V1.md) | 当前每账号串行 Memory basis 调度；不改变 JOBS1 字节。 |
| [DECISION-JOBS-V1](DECISION-JOBS-V1.md) | 当前完整 accepted Trip 来源，C471 DecisionConversationProducer + B466 RUN-BACKGROUND3。Data3/Output3/Pub3 与普通 Data2/BG2 并存，不取代它们；不接受 scoped/day/item 来源。 |
| [CANDIDATE-DISCOVERY-V1](CANDIDATE-DISCOVERY-V1.md) | 仍有已合 A463 的 V5→V3 消费者，不能标为无消费者。新 App 使用下述 V6 当前投影；A 的 V6 WIP 不能冒充已合消费者。 |

新的候选发现使用 [ERASURE-V1 当前候选投影](../memory-withdrawal/ERASURE-V1.md#c-storagehooks-and-candidate-compatibility)：
`GET /v6/memory-candidates` / `MEMORY-CANDIDATE-projection@2` 直接返回原 review
job/attempt，清除共享 job payload 后仍能审阅其他候选。Action1/原回执不变。
旧 V5/V3 读取继续为已合消费者保留；它不是 V6 失败后的 fallback。

[SEAM](SEAM.md)、INPUTS/VALIDATION 是早期隔离 SQLite 候选的来源快照，
不再是 PG/worker 的当前入口。SQLite production_queue 仍关闭，未迁移或删除旧数据。
只有实际已合消费者被缺陷阻断时才追加版本；PR 必须说明被取代部分和仍存消费者。
