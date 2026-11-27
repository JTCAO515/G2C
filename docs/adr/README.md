# ADR 索引

`accepted` 仅表示明确确认的范围/行为；`proposed` 是待验证建议，不是已实现或不可替换栈。实现状态仍由 Issue 和版本证据说明。新证据改变结论时，以新 ADR 引用并 supersede 原记录，保留历史，不原地把提议伪装成确认。

| ADR | 状态 | 决策 |
|---|---|---|
| [0001 产品与用户控制边界](0001-product-boundaries.md) | accepted | 当前品牌、受众、双语四 Tab、完整长记忆、Muse、全新数据与开工边界 |
| [0002 技术候选与替换条件](0002-runtime-candidates.md) | proposed | SwiftUI / Auth / OpenAPI、Python API、单主 Agent / 持久执行 / 内部记忆与旅行工具 |
| [0003 正式状态、恢复与撤回](0003-state-and-recovery.md) | proposed | 单一业务权威、确认与版本、幂等/未知结果、记忆有效性与撤回 fence |
| [0004 交付流程收敛与仓库卫生](0004-delivery-flow-and-repo-hygiene.md) | accepted | 交接回仓库、CI 为唯一绿、证据出仓、去本机路径、删除同仓 hash pin、流程精简；P2 北京 / 邮箱 OTP / iOS 17（可见性修订见该 ADR） |
| [0005 主动式履约（V2）](0005-proactive-fulfillment.md) | 决策 accepted（第 5 条 2026-11-25 修订；第 10、11 条 2026-11-26 修订） | 后台 JT Agent：监听、理解、决策三层，判断模型按评测选定；P0 全员协助；最小披露；具名真人服务事先明示，陪同按次收费、App 外支付 |
| [0006 V2 会员分档与记忆保留](0006-membership-and-memory-retention.md) | accepted（价格待定） | Free / Plus / Guardian、IAP、会员内人工协助打包（陪同等线下真人服务按次另计，2026-11-26 注记）；系统不主动删除记忆，用户要求删除必须执行 |
| [0007 以关闭 Issue 为中心的交付流程](0007-issue-closure-workflow.md) | accepted | 证据分级 L0–L3、功能票 L1 关闭、子票与在制上限、Codex 自审与 JT 停点、里程碑授权清单、自动续作；替代 ADR-0004 第 6 条的合并条件 |
| [0008 消息发送许可](0008-message-send-permit.md) | accepted | 服务端会话头 CAS 作为不可回退的首次发送证据；原子发送状态读取与结果未知判定表；App 激活条件；`MESSAGE-SEND@1` |
| [0009 JT Agent 契约预留](0009-jt-agent-contract-reservation.md) | accepted | 只预留不实现：事件 outbox（只带引用）、主动助手消息推进同一会话头、服务会话类型、候选记忆来源；JT 存储不占位登记；M3 #23/#26/#27 约束 |
| [0010 本地助手与场景包](0010-local-assistant-and-scene-packs.md) | accepted（以 JT 批准合并为准） | 一个 Lio、按任务分场景（tasks[]）；旅游、商务两份场景包（知识、工具、流程、风险规则、可承诺结果）与开关；第三方平台与真人服务两种履约分开显示；记忆按用途分开 |
| [0011 正式登录与账号池](0011-formal-sign-in.md) | accepted（以统筹审定合并为准） | 香港自建：Apple / Google / 邮箱验证码由香港验证、沿用现有会话签发；预开户账号池加身份绑定；撞邮箱验证码确认后才关联；邀请码不变；新行为默认关 |
| [0012 聊天回答自动保存到行程](0012-chat-autosave-to-trip.md) | accepted（以统筹审定合并为准） | 只写本账号当前对话绑定的 Trip；点按版本带 origin（lio/user，用户动过即永久 user，Lio 不改不删）；每次写入出 24 小时可撤的回执（复用 TRIP-lio-undo.3，只撤当前版本）；审计补提交时间；外部接受仍要确认引用；开关默认关，隐私政策先上线 |

依据是 CJ Planning（官方 `read_thread` 完整分页读取，线程 `01a15d68-fd8d-7473-991e-2d604486ae75`）、JT 本轮补充与 GitHub r3 Issue。较早三 Tab、弱化首批长记忆等建议已被后续明确确认替代。各 ADR 的验证项仅是未来任务，不在本轮试验。
