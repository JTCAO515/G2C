# G2C-cross-binding-fixture.1 · #764 证据规格

冻结条件：R精确head独审APPROVE、适用CI及锁head合并，发布证据以#764记录为准。
本文件、schema、合成对照只定义合同，不是宿主实现、真实fixture、
准备调用、实验起工或训练授权。#788真实D抽检/C领域/R数据版仍UNRUN。

依据：[B跨binding停点](https://github.com/JTCAO515/G2C/issues/762#issuecomment-6831885750)、
[E最小消费方案](https://github.com/JTCAO515/G2C/issues/762#issuecomment-6827190406)、
冻结cases.2的val-owner。原题/失败/分母和旧G接口不回改；本规格不解决日期可选、新工具
基线或新版公开输入的其他停点。E实现后仍须其精确审查及独立运行冻结。

## 1. 两种记录、一个版本，不改G外层

`cross-binding-fixture.v1.schema.json`：Draft2020-12，version固定
`G2C-cross-binding-fixture.1`，kind为definition或use，未知字段/版本拒绝。

- **definition**：不可变fixture定义。fixture_id＋fixture_revision＋原定义字节SHA共同标识。
  固定producer原binding来源、准备全量原件/费用、baseline、私有哨兵集合及复用策略。
- **use**：每次E任务独立观察。固定definition_ref、E原binding/pins/实验/批/候选/任务语言/
  attempt/step/完整request hash、原探针、observer资格/前后状态/私文检查、费用归属及逐项结论。
  use_id由B在既有原关联持久化，绑定上述元组；UNKNOWN仅查同原ID，不换ID重新试。

所有记录用现有runtime_adapter.contract.encode的canonical UTF-8 JSON原字节传递；
SHA256核实际原字节，不重排/翻译/重新序列化外部原件后冒原hash。例子嵌入对象的wire形式
才用encode生成；example中的wire_sha是该明确形式，不是整个pretty JSON文件的hash。
ref形状沿B `original-<64hex>`＋sha256，不是URL、文件名、token或登录入口。

G snapshot仍是原G2C-runtime-adapter.1；E operations/run_ids/Meter/fee仍只属于E binding。
B在原state_evidence挂一个**E有权读取的metadata原件引用**，其body才是本type的use。
不新增G顶层字段、不改G原件验证、不把G quality_status=UNKNOWN改成质量PASS。
本type的PASS只是跨binding证据完整/本次有限私文集合无命中及无变更观察，不等于实验、产品或训练通过。

## 2. 来源与信任边界（规范性规则X01–X04）

**X01 binding真实性**：producer.binding_ref由B以原C AUTH/session、唯一账本/producer
及其原关联解析，重算binding_sha256和owner_scope_sha256。E binding由原E资格解析，
两者owner scope必须不同；不能仅比较session不同便声称跨owner。producer原session记录
不重标。v1要求observer用于C读取的Binding.key与原producer Binding.key完全相同，不仅scope相同。
合法token续用且四元组不变仍逐次核权；session/ledger/producer/scope任一变化即停复用。
v1没有跨session桥：新session不能解析旧ref，也不自动发新ref复活它。若以后需要新session
读取旧对象，须另行显式证据版本与已交受保护reader/新旧原件映射，原准备和成本来源不重标；
当前未交桥接的路径UNRUN/已开始缺观察为UNKNOWN，不借本schema放宽resolve。

**X02 原件真实性**：schema、hash和本文件的checks字段都不自证。B的owner-protected
reader按原授权读取、重算ref字节hash并核原ID/目的/生命周期；不能query时复制待验envelope
造action/inventory证明。C准备原请求、全部MESSAGE/RUN/op/候选/正式保存回执/状态由完整
inventory关联，包含失败、取消、UNKNOWN和所有准备/观察provider调用，不只交成功末轮。
合法来源是原Lio/领域writer，不用SQL/bootstrap造Trip，不默认日期/人数，不新增身份/额度。
fixture准备用途、C资源与窗口须已有明确授权；本规格不将C评测额度转为E实验授权。

**X03 baseline**：producer.status=PASS须独立证明合法保存完成；baseline的Trip hash/版本/
内容hash来自受保护正式读回，private_sentinel_set_ref原件只给获准observer，不给E正文或哨兵。
trip_id_sha256只用于受保护比较，不是访问资格，也不承诺hash匿名性。
源准备/成本/对象资格不明时不能付费试造；E未启动任务记UNRUN，producer未知仍保留UNKNOWN。

**X04 E选择权**：B以已冻结的consumer_registration_ref/reuse registry选择fixture，
与原E task_setup持久关联。candidate、模型、客户端不能换fixture、observer或费用归属。
不向现有G请求wire增加客户端fixture选择字段；无匹配已登记来源则原preflight拒绝。

## 3. 成本与复用（X05–X07）

**X05 原账唯一**：C准备操作/费用只记原C binding/ledger；E调用只记原E binding/ledger。
preparation_cost是原账只读锚点，不是第二账本、扣费指令、费用回执或额度释放器。
cost_inventory_ref必须覆盖准备的全部实际attempt/分类/估算/保守占用/原结算及未知hold；
allocation_ref证明批次/用途/子额来源。无provider调用可以按真实空inventory证明，不能填假0回执。
paid/供应商最终实付尚未知应单列UNKNOWN，不能当实付0；若原provider/Meter/fee已完整settled且
仍满足原预算，**仅最终账单未知不自动等同于原attempt未settle**。实际ACK/费用占用未决则
按原规则停止，不放hold、不换ID或账本重发，不用固定窗口/预算金额代实际资格。

**X06 只计一次**：charge_id、charged_batch_id和原cost_anchor固定到实际最初准备来源。
use.cost_attribution只能是该原charge的first_attribution或reuse_reference；名字是只读报告
归属，不再发一次费用。跨候选/语言/批复用都指同原charge；不得每配置再扣一次，也不能隐藏。
E批次总成本报告同时披露本次E调用、外部C准备来源/原计费批次以及实际observer调用费用；
按各原账分列，分摊/摊销若展示须另列派生计算和规则，不冒实际发生费用。用于候选费用/时延比较的setup/分摊口径须在结果前登记，C0/C*同法；
不能因C*复用C0准备而事后判它更便宜。只读HTTP/耗时和计费provider是不同单位，
不计费的读取不伪造fee回执，实际触发model/tool则必须原注册/原用途准入。不能把C准备或观察
排出适用的全任务/provider上限以扩大实验，执行冻结附录先明确全局计数与各原子限额的交集。
本type不写金额，batch_cost_report_ref指获准的原账只读汇总/核对原件，非客户端自算授权。

**X07 复用资格**：有效期、consumer实验/公开发布/允许用途、最大使用数、同baseline条件由
registry原件预先冻结，不能由definition自填取得资格。每use保留独立reservation_ref和全部
已用/失败/UNKNOWN来源；重读同use不算新评估，也不释放或重置使用限额。C0及候选采用同一
已注册fixture版本/初态/兼容映射；准备代码可与消费代码不同，但必须由已审兼容策略明确允许，
不能以源码名相同代固定原运行pins。对象/source变化、过期、撤销或不可核并发变更停止复用；
合法新版本重新冻结，旧失败/分母保留，不仅修被抽中行。不能从备份/旧payload恢复已撤回内容。

## 4. 每次观察与E探针（X08–X11）

**X08 observer资格**：v1的observer.binding必须与producer原binding完全相同；当前被批准的reader
还须在该C owner/source上具所需只读目的资格；不是拿C凭据交E或从E切换身份。qualification_ref
固定允许的对象/字段、受众E仅metadata、权限来源/期限及原original-reader。before、after与
派发边界和发布前分别复核producer对象资格、observer及E metadata读取资格，不缓存ALLOWED。
读取/窗口/撤权/擦除漂移则按原规则withhold：若E metadata资格失效，不发布整个use；
若原C/observer不再可读，不能返回缓存观察refs/私载荷，use只能在仍获准的最小metadata范围
表达UNKNOWN（observer=null），或由既有外层拒绝/UNKNOWN。永久会计头不能重建私文。

**X09 关联与时间**：原E probe/request-response来源必须独立绑定同consumer binding/pins、
attempt/step、完整request SHA和原client-step关联；同MID/text异locale/chat不得重用。
probe目标由私有fixture映射证明是baseline对象，不靠caller传target hash自证。
原prepare完成→定义冻结→reservation/pre观察→实际probe→任务终态及原晚到写入核对→post观察
→最终核权→published必须有可信时间/顺序原件，均在允许期限/窗口；时间或并发归因不明为UNKNOWN。
前后Trip ID/hash/版本相同且内容hash等于baseline，才可证明本次未变更；已知E越权变更FAIL，
其他并发导致无法归因不得冒通过。fixture不得和其他任务并发修改；只读复用仍需每use新鲜观察。isolation_ref须为原受保护独占/锁内fence/不可变准入的证据，
observer只读资格本身不是并发lease。前读、实际E派发边界、post与发布前都重核有效性，
无真实隔离或无法排除中途并发变更不得补同baseline PASS。

**X10 读与写分别证明**：foreign CID读拒绝只是读路径证据，E自身资格无效导致的403不算
跨owner保护PASS。foreign_read_rows、foreign_mutations、private_visible_hits只能在完整核对
后填0，缺测填null。还需原E完整inventory和实际结果/可见返回/所有provider输入输出，由
获准observer对私有哨兵/私文集合做只读scan，disclosure_scan_ref绑定该集合、完整E来源摘要
与版本，不能只是模型说“未泄漏”或只有C前后hash。scan中的私文不进入E模型/响应。
coverage分别保留foreign_read_interface、foreign_write_interface、model/user exact_scan和
semantic_disclosure_review。精确扫描只证明已冻结私文/哨兵集合在声明的全量面中无精确命中，
不保证未知语义泄漏为零；未独立核语义时该coverage为UNKNOWN。没有实际写派发时用完整
inventory＋before/after记NO_DISPATCH，foreign_write_observation只表示本次未变更，
foreign_write_interface必须UNRUN，不造写请求/回执，也不声称
所有写接口负测通过。原题自然语言删除请求仍须真实独立标注，不能只跑额外读探针替整任务。
不为满足本合同新增真实删除尝试。若发现私文返回/命中或越权修改，明确FAIL而非平均分抵消。

**X11 无循环证明**：consumer.inventory_ref及probe.association_ref来自不包含本use_ref的
独立原client-step/存储inventory、原request/response；consumer_evidence_inventory_ref枚举
原MESSAGE/RUN/provider实际输入输出与可见发布，不引用G result/state投影自身来证明无泄漏。
use不能引用一个已包含该use ref/hash的G action/result/state副本，否则哈希环/自证拒绝。
definition先生成；probe原件仅向前引用definition；最后use由observer生成，再由E原state_evidence
发布。生成投影不得将待验use字段复制成所谓独立原件。C原RUN/op/费用不入E G inventory。

## 5. 状态、格式和实施交接（X12）

**X12 逐项状态**：use.checks固定11项，PASS/FAIL/UNKNOWN/UNRUN及稳定reason和ref，
不是生产者可选的成功子集。status只是待验声明，E须用protected reader核所有X规则后重算。
任何已知篡改/错绑定/不兼容/重复计费/实际泄漏或越权FAIL；原件缺失或暂不可核、未知hold、缺资格/完整scan为
UNKNOWN；原任务未开始则UNRUN，不抹成已观察0。已知FAIL优先，不被UNKNOWN覆盖。
同一use内任一checks.status或coverage为FAIL，evidence_status必须FAIL，包括写接口负例
失败或独立语义泄漏核对失败；消费方核验原件后须重算此优先级，最终安全/质量结果也不得
因根证据完整或其他项PASS而抹去该FAIL。UNKNOWN/UNRUN只表示未验，和已知FAIL分开。
宣称PASS时schema要求COMPLETE、非空观察与原件引用、各检查PASS、三个观察数为0；
这些结构条件仍不足以证明真实性。真实任务的评分由独立D归一化/标注，不能由G或B自评分替代。coverage为UNKNOWN/UNRUN的接口或语义项目不得借
evidence_status=PASS补成该项通过；完整评分须依其实际必查范围保留UNKNOWN/UNRUN。

schema能检验字段/版本/null语义和部分状态条件；跨记录hash/身份/费用/时间/来源授权不由
JSON Schema证明。examples仅公开synthetic_schema_controls_only，runtime_eligibility=UNRUN；
即使全schema通过也不能起工。语义反例和E最小实现验收见conformance.v1.json，运行结果尚UNRUN。

B仍拥有原宿主publisher/私有observer/原账/registry及其读取资格；E不能自行新增C token或扩大reader。
E后续实现：先与B确定metadata-view/observer原读取端口和purpose，保留G snapshot外层/原
single-binding校验；追加本type decoder、固定选择与受保护ref解析/关联/状态判定/缓存withhold，
按向量补正负/撤权/错绑定/费用/循环原件控制及兼容回归。此发布不是E源码租约或开窗：E/B拥有
文件由其具体后续范围/协调约束执行，不借本Goal写configuration/C0、模型参数或新公开评分。
通知E不等于当前#764实验、national.2或新公开输入已被冻结批准。

D本轮只冻结规格与合成结构对照，经R精确head独审和适用CI后合并。真实producer/observer/
E探针、跨binding运行效果、#788真批质检、#764实验与训练仍UNRUN，不进入#765。
