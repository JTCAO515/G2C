# MESSAGE-draft.1 — CJ009 / Issue #10

协议无关草案，目标 MESSAGE@1.0 **未冻结**。仅 `contracts/message/**`，
基线 `59ea8aa46fed3738063b8031250367370c628cf8`；输入为本地 CJ-DOC-36
Issue #10/#5 r3 快照、docs/contracts.md、该基线 AUTH-draft.1。
独立执行 owner 为 CJ009；Review/Testing/Publish 与作者分离。

本目录不是 API/数据库实现。`schema.json` 仅描述草案消息输入；`model.py`
是标准库内存状态机，不能导入正式服务。唯一正式 wire 来源仍是
`contracts/api/openapi.json`；消费确认后由 CJ005 纳入并生成，下游届时移除
本草案语法依赖，不长期维护第二套 wire schema。没有 endpoint、迁移、凭据或云配置。

## 输入与原回执

- 客户端在首次发送前固定原 message_id 与完整 UTF-8 输入字节，持久保留待恢复
  动作。作用域是可信 principal + receive + message_id，跨聊天复用 ID 仍冲突。
  conversation_id、text、nullable trip_id、creation_intent 及版本均在原字节内。
- 不修剪/Unicode 规范化/重新序列化后冒原输入；相同 JSON 不同空白也冲突。
  hash 用于校验，不替代原字节等值比较。拒绝重复 JSON key、未知字段/版本。
  schema 的字符串类型之外，运行校验还拒绝纯空白 ID/正文。
- receipt 字段：version、conversation_id、message_id、run_id、sequence、accepted、
  input_sha256。它是不可变**接收回执**；同字节重复返回同回执，即使运行已结束。
  query 的动态运行状态独立返回，不把接收回执改成“已完成”或“记忆已保存”。
- request_id 是 BASE 请求追踪标识，不参与幂等键；真实错误需由 CJ005 映射，
  此处 Rejected 字符串仅测试断言，不新增正式错误码或 HTTP 状态。
- Trip 为空时可完整聊天；creation_intent `none/consider_trip` 只是草案意图，
  不授权创建/选择/改动 Trip。非空 Trip 需要真实归属/版本检查，此模型明确拒绝，
  等 CJ015/016 确认字段与绑定行为；不使用假 Trip 作为验收。
- 语言是显示偏好，不新建聊天、不更改已固定动作。未发送草稿按身份/聊天隔离，
  不自动把旧草稿覆盖新输入；保存草稿不是发送、结束或记忆保存。

## 状态与崩溃窗口

| 起点/事件 | 原子结果/恢复方式 |
|---|---|
| 未提交，接收前崩溃 | 客户端 UNKNOWN；向权威原动作查询，完整账本明确未接收后才可用原字节原 ID 重试 |
| 接收提交 | 同一事务写消息、原始输入、原回执、稳定 run_id、待投递义务；提交成功后才能 ACK |
| 提交后、投递前崩溃 | 查询 accepted_pending；恢复扫描待投递义务，投递原 run_id |
| RUN 已接受、投递 ACK 丢失 | RUN 先以原 run_id 去重；恢复仍投递原 ID，不生成第二运行 |
| 已运行 | query running；断线不改状态，不补发新消息 |
| 有原运行终态/结果 | query result_available；终态不可改写，失败/取消也不是成功正文 |
| 账本/游标超留存 | recovery_expired / resync_required；不等于未接收，不盲重发 |

真实事务、锁、唯一约束、跨进程 dispatcher 和 RUN 去重由正式实现验证。
本模型一次函数转换视为原子；deepcopy image 只模拟“已提交快照重建”，
**没有测试真实进程崩溃、磁盘持久性或分布式 exactly-once**。
没有付费调用；RUN 去重不自动解决 provider 未知扣费问题。
同聊天以接收 sequence 顺序投递，前一运行终态前不派发下一运行；不同聊天可独立。
这个串行策略尚待 CJ010 消费确认。RUN 结果在本模型为 opaque 合成终态对象，
具体取消/单一终态枚举与上下文失效由 RUN 提供，不能把本模型当 RUN 实现。

## 身份与恢复

Authority 是合成可信裁决，不接受真实 token，不是认证器。真实 principal
只从服务端 AUTH 取得；每次读写/投递/摘要 ACK 都重查当前有效会话、资格和归属。
客户端在 await 后、显示/缓存/派生任务前核环境、principal、会话版本、实例和
client generation；本模型只覆盖服务端语义，UI 晚到屏障需 CJ006/007 接入。
他人聊天与不存在聊天相同 unavailable；原动作查询按当前身份分区，不枚举他人 ID。
身份失效/资格未知不能当“未接收”；网络失败保留 UNKNOWN，恢复只查询原动作。

最新任务包已确认邮箱密码、自助注册、邮箱验证找回及 JT 邀请名单；未经邀请
不得调用模型。本草案不实现登录。基线 AUTH 对受限业务更保守的门禁仍沿用作
合成前置，未邀请用户是否可读既有历史等精确产品范围待 AUTH owner/消费者确认。
AUTH@1.0 尚未冻结，不以此宣称已完成消费确认或真实账号隔离。

## 分页与结束摘要

聊天列表/消息分页使用固定快照、单调序号和 next_cursor；追加消息不插入已有
快照。重复页面安全去重，重启后用原游标继续；新快照才看到新增内容。
游标绑定身份/会话版本/查询种类/聊天/数据代次；跨作用域、过期、未知均显式重同步。
fixture-cursor 是内存索引，不是生产 token；正式实现须不可伪造且校验权限，
清理/撤回使旧快照失效。分页 limit 草案范围 1..100，非已接受产品限额。

本草案选择**显式结束聊天**作为摘要触发：持久写唯一 end_id 和 through_sequence
边界，并持久保留处理义务。关闭 App/断网/切 Tab 不算结束，也不依赖回调一次性执行。
结束后新输入须显式新聊天；旧消息重复仍查原回执。是否支持空闲结束/继续原聊天
需 CJ020/产品确认，不能由后台超时推断用户意图。

摘要批次以 end_id + after + through 为稳定消费标识，来源保留原消息字节、
message_id、run_id、sequence；RUN 终态未齐先等待，结果由原 run_id 查询。
CJ020 先幂等提交派生结果和自身 durable receipt，再推进 MESSAGE checkpoint。
崩溃在处理后、checkpoint 前会重投**同一批次**，由 CJ020 去重；不能认为已保存两次。
ACK 丢失先读 checkpoint；旧批次 ACK 返回 checkpoint_conflict，不盲重做提取。
checkpoint 只能比对完整原批次顺序推进，不能跳过来源。达到 end boundary 才完成，
空聊天为显式空来源。这里 durable_receipt 仅合成标志，真实持久回执核验待集成。
消息接收、摘要处理、记忆条目保存是三种不同事实。

## 留存、清理与冻结缺口

不承诺无限幂等/恢复。具体账本/原字节/草稿/快照/结束标记/处理游标/派生引用的
留存期限尚未定，生产实现前必须明确查询窗口、过期标记及 ID 不复用策略。
本模型仅注入 expired/epoch 表达过期反例，不实施删除或备份恢复。
消息正文、草稿、原字节、关联身份/旅程均为私有数据；诊断不能记录正文/凭据。
CJ009 提供全域清理清单与 hook，CJ024 协调整体清理；删除/撤回与备份恢复须使
旧投递/摘要/游标失效，不能靠前端隐藏冒物理删除。正式存储清单由 CJ005 登记。

待确认消费者：CJ005 唯一来源/事务机制/错误，CJ007 AUTH 身份与资格，CJ010
原 run 去重及串行投递，CJ011/020 稳定来源和摘要 checkpoint，CJ016 Trip 上下文，
CJ023 诊断引用，CJ024 清理。均为 PENDING；独立 Review/Testing 尚未进行。
真实 API/数据库/账号、模型调用、真机、CI、部署均 UNRUN，Issue #10 不关闭。

运行：`python3 -B contracts/message/check.py`。全部使用明确 fixture 身份，无网络/安装。
