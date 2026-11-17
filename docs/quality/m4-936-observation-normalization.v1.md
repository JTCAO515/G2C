# #936：真实观测与值归一化接口设计 v1

状态：**设计提案；新适配器、值词表和真实调用均 UNRUN**。讨论与交付记在
[#936](https://github.com/JTCAO515/G2C/issues/936)，规格保持
[#922](https://github.com/JTCAO515/G2C/issues/922) §0.7 / G2 / G3。
本设计不改 G2=零重复追问、G3≥80%、20画像×3次、840因子分母，也不重写旧结果。

## 1. 已有接口和当前缺口

- 现有数据版本为 LIO-simulated-users.1，轨迹为 LIO-simulated-user-trace.1。
  [core.py](../../eval/lio_simulated_user/core.py) 的 _same 只对 interests、
  must_see、avoid 三个字符串数组做无序比较；其他值严格同 JSON 类型、同值。
  布尔值与整数不同，数组重复项不被去除。目前没有城市/产品枚举别名比较器。
- [已有宿主接口](../../eval/lio_simulated_user/README.md#observation-boundary-and-host-integration)
  要求原回答 text、实际问题 factor/start/end、明确问题清单完整性、实际 accepted_context
  画像、原生探索结束和独立注入 Memory 观察。评分程序不认证原件或提供读权限。
- [native4 展示适配器](../../eval/lio_simulated_user/native4_observations.py)
  读取冻结 LIO-timeline.4，保留默认不完整的问题清单及不可用画像。
  public profile.display_text、model.lio_intake.9 建议值不能成为 G3 画像。
- B 当前 SimulatorEpisode.read 保留 questions_complete=False、
  profile_complete=False、exploration_complete=False。现有 observe 拒绝 draft_outcome，
  只接 completed consultation。没有真实结束边界时，不能凭固定轮数或正文“好了”完成轨迹。

B 先保留同原 MESSAGE 接受的 lio_planning_context.2、来源和实际选中动作原件。
在 C 的公开、版本化归一化实现完成前，缺证字段继续不可用，不开不可评分的60条实呼。

## 2. 新增观测封装的范围

拟新增 **LIO-simulated-user-observer.1**；不修改旧 trace.1、冻结 MESSAGE/Trip wire。
封装承载原件引用和归一化版本，并输出现有 DialogueHost 字段。版本名是本设计的拟议名，
尚无可执行解析器或已冻结 JSON schema；B/C 实现 PR 必须明确最终版本与正反例。

| 内容 | 证据和约束 |
| --- | --- |
| 身份、来源 | 实际 candidate source/image/schema、model/prompt、owner scope、CID/MID/RUN、原输入摘要及受保护读取引用；由 B 原读桥认证 |
| 原画像 | 同轮实际被接受的 context.2 原字节及摘要；每个 fact 的原 value/state/sources 保留，来源可引用此前同会话的真实 MESSAGE |
| 问题 | 同一回答原文及逐问题 Unicode 字符区间、因子、独立依据和覆盖范围；不能从隐藏画像反推 |
| 探索结束 | 同一身份与原动作中实际被选 PlanNow/PREVIEW receipt、选择链及当时画像的引用；由 B 专用、有版本的读接缝提供 |
| Memory | 首轮实际模型输入中 accepted_injected 原件、完整性、文本、规范化 facts 和原 ref；与 context 内 memory 标签分开 |
| 输出 | 原回答、问题、画像和完整性等现有 turn_fields；observation_ref 回指完整封装，缺证不能补造 true |

每次覆盖读取仍受既有 owner、lease、时限、source 和只读规则约束。
新封装不授予账号、原件、模型或工具权限；不会通过读取器选择动作、制造 receipt 或补数据。

### 探索结束

B 保留原 observe 的通用 draft 拒绝。新增接缝只允许读取实际被选中的结束动作及其
原 receipt，并核对同 owner/CID/MID/RUN、真实选择、实际结果和当时 context。
用户说“直接出方案”只是原请求，不能单独代替实际选择链；普通 MESSAGE completed、
UI completed、Trip 存在、固定轮数和计划按钮可见也不能代替结束原件。

已知失败、拒绝或 UNKNOWN 按实际结果保留。缺结束证据时 exploration_complete=False，
不为算 G3 把失败/拒绝伪装成成功结束。计划执行结果与探索边界分别记录，
由 B/C 在实现 PR 中列出可证明的原生状态及反例。

## 3. 公开值归一化

C 拟新增独立的 LIO-profile-value-map.1 和适配器，保持 core._same 与旧轨迹不变。
词表必须在真实运行前公开、审查并固定摘要；从公开产品语义、批准名称及原件建立，
实现不导入 profiles.v1.json、hidden_answers 或 persona ID，不按期望答案选映射。
B 保留原值和 provenance，C 做比较前的表示转换；未知、多义或信息不足显式留缺口。

公开产品语义来源是
[因子目录](../../backend/cj_api/lio_exploration_factors.py) 和
[context.2 / canonical aliases](../../backend/cj_api/lio_exploration_profile.py)；
C 的适配器不把它们的私有函数作为隐式稳定 API。

| 因子 | 转换原则 |
| --- | --- |
| city | 完整、无歧义城市名称与公开稳定城市 key 对应，如北京 / Beijing / beijing；需要城市身份时使用实际批准名称/城市原件，不做子串、模糊匹配或按画像选城市 |
| duration_days / first_visit | 保留原整数 / 布尔类型；不把 True 变1，不从显示文案猜取值 |
| season / pace | 公布同义词和产品域枚举的精确等价表；原值已同规范时保持，未列值不猜 |
| party_type / lodging_tier | 不同枚举须先公布语义对应，例：产品 family 的“带孩子”与规范 family_with_child；simple 的“经济型/budget-friendly”与 budget。不能按目标画像补人数、价格或儿童年龄 |
| interests / must_see / avoid | 逐项做有来源的一对一名称转换，保留原数组及重复项；只沿用 core 对三数组的无序比较，不把博物馆泛类推成某座具体博物馆 |
| dietary / mobility | 公布形状与语义对应；不把未填/默认 null 当作明确“无约束”，不丢掉多项限制以匹配某个标量 |
| arrival / departure | 只转换原件明确给出的天序号、交通方式和精确时间。只有“上午”不能造出第1天/飞机/09:00；更精确的独立原生 slot 需同轮来源绑定 |
| null / 缺项 | 保留原 null 与缺项区别，不补隐藏值；不从计划默认值推成用户已知事实 |

这是转换规则设计，表中例子不构成完整可执行词表。公开词表未覆盖的值必须保留原值与
无法转换的原因；不能声称已归一化完整。部分 accepted profile、值转换完整性和真实
探索结束分别记录，由适配器保守输出既有 profile_complete；诊断匹配不计正式 G3 得分。

### 状态与 Memory

known、not_needed、inferred、default 保留原状态，不相互替代。context.2 的 memory
只在真实 Memory provenance 对齐后对应 trace 的 from_memory：
原 slot/source ID/source version/item version/text 以及当前被接纳注入的引用须可核。

G2 的 memory_observation 仍单独取实际模型输入，不能用存储 context 的 memory 标签、
公开卡片或隐藏画像代替。实际观察到空注入才可 complete=True 且 facts=[]；
非空但无法规范化时保持不完整，缺读件不等于空。
G2 仍以实际释放的用户话语与接纳注入为已知事实，推断不能覆盖用户原有明确回答/拒绝。

## 4. 所有因子问题的实际覆盖

G2 覆盖原回答里所有14因子的追问，包含 question_groups、segments、notices 等位置。
普通社交/控制问句不计因子追问，但其分类也需独立依据。
factor/start/end 必须绑定原回答的 Python Unicode 字符 [start,end)，不是字节、
UTF-16 或任意第一次文本匹配；native4 的冻结投影顺序保持。

只有结构化原件加独立完整清单，或明确的 independent_annotation，才能声明 census 完整。
不从一个问号猜因子，不用“只有 groups”、没有问号或模型自评证明完整。
目前 native4 适配器发现未覆盖问号会继续 withholding completeness；这是原门槛，
本设计不删除。需要其他证据形式时另写版本和负例，不暗改旧适配器。

已证实的重复问题可以使 G2 FAIL；没有重复但清单/注入/结束缺证时是 UNKNOWN。
不让“能算费用”“服务端已完成”替代可评分原件。

## 5. 分工与交付状态

- **C**：公开规范值词表与新适配版本、实际 span/值/状态的正反例、保留旧 scorer，
  验证中英名称、枚举形状、未解析值、Memory 和未完整 census 不能误 PASS。
- **B**：原读桥、同源/同身份 custody、原 context/MESSAGE/注入、结构化问题、
  实际被选边界 receipt；保留原拒绝路径并给新接缝追加版本及独立红线审查。
- **联合**：新输入/输出正反例、签名私有 PG 组合后，再核真实 source/image、
  actor/DUT 原件、完整原账、现有 C 子额度与新窗口。当前无新实呼许可。

本 PR 仅文档设计；实现、签名组合、真实60条和新系统回归入口资格仍 UNRUN。
真实执行仍逐项报告 PASS/FAIL/UNKNOWN/UNRUN 和保守/token估算/实付三栏；
保留原失败、未知和费用。额外计费评审 producer 需原授权与完整计费覆盖，
不由这份设计引入或扩大额度。
