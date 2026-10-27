# ADR 索引

`accepted` 仅表示明确确认的范围/行为；`proposed` 是待验证建议，不是已实现或不可替换栈。实现状态仍由 Issue 和版本证据说明。新证据改变结论时，以新 ADR 引用并 supersede 原记录，保留历史，不原地把提议伪装成确认。

| ADR | 状态 | 决策 |
|---|---|---|
| [0001 产品与用户控制边界](0001-product-boundaries.md) | accepted | 当前品牌、受众、双语四 Tab、完整长记忆、Muse、全新数据与开工边界 |
| [0002 技术候选与替换条件](0002-runtime-candidates.md) | proposed | SwiftUI / Auth / OpenAPI、Python API、单主 Agent / 持久执行 / 内部记忆与旅行工具 |
| [0003 正式状态、恢复与撤回](0003-state-and-recovery.md) | proposed | 单一业务权威、确认与版本、幂等/未知结果、记忆有效性与撤回 fence |
| [0004 交付流程收敛与仓库卫生](0004-delivery-flow-and-repo-hygiene.md) | accepted | 交接回仓库、CI 为唯一绿、证据出仓、去本机路径、删除同仓 hash pin、流程精简；P2 北京 / 邮箱 OTP / iOS 17（可见性修订见该 ADR） |
| [0005 主动式履约（V2）](0005-proactive-fulfillment.md) | 决策 accepted / 架构 proposed | 后台 JT Agent：信号识别、建单、AI 执行与人工确认；P0 全员协助；Jev 判断模型；最小披露 |
| [0006 V2 会员分档与记忆保留](0006-membership-and-memory-retention.md) | accepted（价格待定） | Free / Plus / Guardian、IAP、人工服务打包；系统不主动删除记忆，用户要求删除必须执行 |
| [0007 以关闭 Issue 为中心的交付流程](0007-issue-closure-workflow.md) | accepted | 证据分级 L0–L3、功能票 L1 关闭、子票与在制上限、Codex 自审与 JT 停点、里程碑授权清单、自动续作；替代 ADR-0004 第 6 条的合并条件 |
| [0008 消息发送许可](0008-message-send-permit.md) | proposed（待 JT 批准） | 服务端会话头 CAS 作为不可回退的首次发送证据；原子发送状态读取与结果未知判定表；App 激活条件；`MESSAGE-SEND@1` |

依据是 CJ Planning（官方 `read_thread` 完整分页读取，线程 `01a15d68-fd8d-7473-991e-2d604486ae75`）、JT 本轮补充与 GitHub r3 Issue。较早三 Tab、弱化首批长记忆等建议已被后续明确确认替代。各 ADR 的验证项仅是未来任务，不在本轮试验。
