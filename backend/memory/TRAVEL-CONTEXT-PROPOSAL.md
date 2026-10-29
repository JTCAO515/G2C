# #227 跨旅行上下文版本方案（供 JT 审阅，未冻结）

状态：JT 于 C 线会话授权“起草跨线版本方案再审”；没有授权实施 B-owned 文件、
修改冻结契约或执行新迁移。本文不是发布契约，也不是功能完成证据。
代码观察基线：main `1f960a11a26e596b6913adfa6fdb99312dbbd45d`；
C 本地消费候选 `6a6918338628a2f8f3b17ebfc2809f250c42cec9`。

## 必须补齐的行为

同一 conversation 中旅行 A→B 不带入 A 的临时记忆；同一旅行 A 跨两个 conversation
仍取得 A 的临时记忆及长期值。当前明确文本仅影响本次使用。不能用 conversation
变化证明旅行变化，不能从自然语言猜旅行，不为聊天造一个假 Trip。

现状：MESSAGE-send.1 拒绝非空 trip_id；#226 current context_id 只核对 owned
conversation；canonical current_context 的 context 参数是无类型字符串。
因此现有 worker 候选是同对话/跨会话/重建消费部分，#227 框2仍未满足。

## 建议的最小跨线协议

建议 B 提供 **TravelContext（旅行上下文身份）**，它只有服务器生成的稳定ID、
owner/scope、版本/可用状态，不含行程内容、费用、来源事实或正式写权限。
它可在首次正式Trip前存在；不是伪造Trip，也不是第二份行程/需求事实源。
与正式Trip/NEEDS的关联只在对应契约/owner明确后添加，本片不猜#14的未冻结结构。

这是当前信息中能够同时表达“同旅行跨conversation”和“同conversation换旅行”、
又不要求预先接受正式Trip的最小身份。若B已有能够证明上述性质的权威规划上下文，
应直接复用它，不能因为本文命名再建第二张同义表。当前main只见conversation绑定，
没有可直接消费的上述已冻结身份。

### B：版本化消息接受与原上下文绑定

候选 `TRAVEL-CONTEXT@1`：创建/选取由服务器核owner，context_id不可由调用方自证
归属；状态/版本修改复用既有显式CAS/原动作回执模式，不另写约束求解或版本引擎。
未选择上下文是明确状态，不阻止纯聊天及长期记忆。新建/切换旅行必须是显式用户
意图；不能从语言、日期或新conversation静默推断。A入口属于A，C不代改。

候选 `MESSAGE-send.2` 保留原字段和CAS/幂等规则，新增显式travel_context引用。
trip_id在本版本仍为null，不借本片启用正式Trip编辑。示例均为合成标识：

```json
{
  "version": "MESSAGE-send.2",
  "conversation_id": "chat-1",
  "message_id": "message-1",
  "text": "本次按当前要求规划",
  "trip_id": null,
  "travel_context": {"id":"context-A","expected_version":3},
  "creation_intent": "none",
  "expected_generation": "generation-1",
  "expected_sequence": 0
}
```

- 无选择时travel_context显式为null，不接受缺字段后自动沿用conversation旧选择。
- B从canonical principal/owner和真实上下文仓储核存在、归属、可用状态与版本；
  expected_version只是并发前置条件，不能证明授权。接受时原子核对并写原message，
  失败不能留下可执行outbox。一个conversation中每条消息可显式选A或B。
- 原始message bytes和原receipt继续是原接受来源，不增加第二幂等账本。worker
  从该原始关联读取，不重新使用“现在conversation选了什么”。如果实际事务/RLS
  要求额外持久关联，B须说明必要性和唯一键/FK/ACK未知后再交JT批准，不能先造表。
- B给出原上下文的受保护复核接口、锁序和旧执行消费者拒绝行为；C不复制其版本
  状态机。修改上下文版本/停用后，旧原动作不能继续当作新发布许可。最终检查在
  副作用前完成，不以提交后的拒绝伪装回滚。
- creation_intent旧意义、NEEDS保护、取消/UNKNOWN和计量保持。上下文身份不授予
  正式Trip写权限，不修改TripProposal确认流程。

候选版本/字段、上下文创建与动作回执形状均待B和JT冻结；MESSAGE-send.1保持原样，
历史draft.1/send.1 bytes、原回执和查询恢复不改写、不回填“推测的旅行”。

### C：有类型的记忆范围与同一套选择规则

候选 `MEMORY-manual.2` / 新版本本地收集策略为 current 提供有类型引用：

```json
{"extent":"current","context":{"kind":"travel","id":"context-A"}}
```

长期值明确为 `extent=long_term, context=null`。这是范围字段片段，完整写入仍含
原 operation/item/subject/slot/kind/text/来源/时间字段及原回执规则，不能当独立写入口。
新 API/wire 使用新版本；不向冻结 manual.1 偷加字段或重释其 context_id。

- current_context/require_current 仍是唯一选择和有效性规则，扩展为有类型 context
  选择：同 subject/slot 下，精确旅行上下文引用的 current 覆盖 long_term；无上下文时仅
  long_term。主体、范围、来源、授权/确认/启用/到期及 epoch 检查继续复用。
- 旧 conversation current 与新 travel current 必须可区分。字符串加前缀不够：旧
  conversation ID 是 opaque text，可能正好等于该前缀或 travel context ID。
- 建议追加迁移为 item 增加有类型 context 标记，并同步原活动 slot 唯一性约束，
  使 (subject,slot,extent,context-kind,context-id) 成为精确身份。旧行仅标记原有
  conversation/long_term 语义，原输入/source/version/receipt字节不改；不把旧值
  自动迁入某旅行上下文。迁移编号在执行前按最新 manifest 顺延，不修改1–17或后续
  已应用文件。具体 DDL、运行权限、up/down 数据保护必须另获 JT 批准。
- typed context 的创建/读取必须从服务器验证 owner/真实引用。RLS/scope沿用原主体
  分区；C 没有权限凭客户端“这个上下文属于我”建立来源。
- 同一份真实记忆变化推进原 epoch/版本；RUN仍用当前受保护 lease 复核，不另建
  提取/草稿/回答各自的版本规则。#17/#26的写入与撤回生产者使用同一生命周期。

### 协调文件与其他 owner

| 范围 | 建议 owner | 当前授权状态 |
|---|---|---|
| 旅行上下文身份、MESSAGE新版本/接受事务/原RUN关联 | B | 仅草案，C不得代改message/run其他文件 |
| 正式Trip/NEEDS关联 | 原owner后续契约 | 本片不新增关联，不碰未列目录 |
| MEMORY typed-context、canonical选择、消费lease、来源核对 | C | lease方向已批准；typed-context/迁移未批准 |
| 所有ios、新消息/记忆wire客户端与选择入口 | A | 本C任务不改ios，不冒称App验收 |
| contracts与生成代码、迁移manifest、PG门禁 | 对应owner逐文件排队 | 先读open PR diff，合同与生成代码按一组锁 |

worker.py/provider.py/local_app.py/run_worker.py仍为B协调文件，开工前重新核锁并在
#227和B当前票声明具体函数。新版本不能借C获准的最小记忆接线权限修改B其他文件。

## 兼容、升级与回退

1. 保留MESSAGE-send.1、MEMORY-manual.1和旧conversation范围模式；新模式显式开启，
   不从新客户端安装或一次保存暗中扩大收集/启用范围。
2. **先完成兼容消费检查，再启用新生产者。** 当前旧 worker 直接 json.loads 原
   message text，单纯未知版本不一定阻止执行。B须先让所有正式执行入口对未支持
   的原 message/context 版本 fail-closed，并实跑固定旧消费者。不能只凭新parser
   会拒绝就宣称旧worker安全。尚未具有该防护的二进制不得作为激活后的回退版本。
3. 未解决的 queued/running/UNKNOWN 原动作必须保留原关联；不自动迁成新旅行上下文、
   换attempt或重发。升级前对pending旧工作设明确可验收停点，由B制定操作次序。
4. 保留旧数据读/原回执对账；新增旅行范围非空后，down不得丢失或压扁成旧
   conversation记录。建议down在存在新类型数据时拒绝，兼容代码保留schema和
   原数据、拒绝无法安全消费的新工作；具体回退合同另行批准。
5. #242消费者尚未合并，本草案不复制其注册/账本实现；落地前从最新已验收B版本
   组合，完整跑其原动作/限额/UNKNOWN/旧消费者套件，不能沿用当前候选旧证据。

## 验收与证据（新版本全部 UNRUN）

| 行为 | 必需证据 |
|---|---|
| 同conversation旅行A→B；同旅行A跨conversation | 两份服务器真实创建的owned旅行上下文、签名V2消息、受限PG、正式worker/FakeProvider实际输入和RUN输出；A临时值不进B，长期原文不变 |
| 未选上下文、尚无正式Trip的新聊天 | 长期可用、当前文本优先；可显式创建旅行上下文以保存临时条件，不制造Trip，不读取别的旅行临时值 |
| 跨owner/缺失上下文/错版本/停用或变更/字段冲突 | 接受与新步骤/发布负例，provider/新RUN副作用为0或原动作UNKNOWN，按实际发生阶段报告 |
| 中英来源、候选/未确认/未授权/停用/过期 | 同一条目、来源及typed范围；canonical选择一致，不造翻译或语义引擎 |
| 在途编辑/启停/撤回/到期与两个锁顺序 | #17/生命周期真实生产者＋同一lease；无新有效delta/completed/proposal，已发送与历史内容边界明确 |
| 重启/保存失败/ACK未知/旧消费者/回退 | 原bytes/receipt/run/attempt不变，旧范围不误解释，新旧模式不静默绕过 |
| 迁移及安全 | 新空私有PG往返、非空down拒绝/数据保留、RLS运行角色与物理连接复用、固定旧消费者、未改已应用迁移 |

L0/L1、新head全CI、独立APPROVE、锁head合并、main绿、证据回写均须实际完成。
#227不因本草案或当前同对话部分候选关闭；#12仍等#227和A #228共同完成。

## 请 JT 审阅的具体决定

1. 是否批准由B复用或提供独立于conversation、无需已有正式Trip的旅行上下文身份，
   并冻结TRAVEL-CONTEXT@1及MESSAGE新版本；它只承载owner/身份/当前性，不复制
   Trip内容/NEEDS语义或另写版本约束引擎。
2. 是否同意C提出MEMORY typed-context新版本及追加迁移的详细实施设计；迁移编号
   依届时manifest分配，新增DDL/运行权限/up-down数据保护仍先交JT批准，不能由本草案
   直接执行。B也需为其新增身份存储提交相同级别设计/授权。
3. 兼容消费者先行、新生产者后启用、旧pending不自动迁移和非空down拒绝是否符合
   预期。若JT选择“只用已有正式Trip”，应明确确认它无法在首次Trip前持久表达旅行
   临时范围；C不自行将该较小模型替代本票目标。
