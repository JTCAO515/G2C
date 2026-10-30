# #273：旅行上下文身份与 MESSAGE 引用详细草案 r1

状态：**DRAFT / 等 JT 冻结及具体 DDL、权限批准；未实施、未执行。**

JT 2026-10-30已批准跨线方向并将本B票插在#243之后、#13之前，不重问方向。运行代码基线为main `e2d01529c80f135f44317476fec3e6c78b5897aa`（C #227 Part1已合入，main40972422603五job成功），本稿从仅追加C规划的`54cd5b3cd76e5c638621c17c31f5a477785b6d6f`接续。C输入设计固定为[方向稿](https://github.com/JTCAO515/G2C/blob/3b1c0df12c8262e1b0e9260d1f5900f5113987f2/backend/memory/TRAVEL-CONTEXT-PROPOSAL.md)与[typed详细稿](https://github.com/JTCAO515/G2C/blob/3b1c0df12c8262e1b0e9260d1f5900f5113987f2/backend/memory/TYPED-CONTEXT-DESIGN.md)。旧迁移1–17及冻结合同不改。

配套：[具体up草案](travel-context-ddl-draft.sql)、[具体down草案](travel-context-down-draft.sql)、[正负例](travel-context-message-examples.json)。SQL放在docs/plan，不加入manifest或迁移runner；**批准前连私有PG up/down也不执行**。本稿提出的版本/表/接口均未发布。

## 1. 范围与审批对象

本票提供身份和原引用，不保存旅行日期、预算、偏好、Trip内容或NEEDS事实，不做语义推断。`cj_message_scope`只是canonical owner的命名空间根；其存在不要求任何conversation或正式Trip。`cj_needs_record`已有需求内容/修订含义且#14尚未冻结，不能为纯聊天/记忆制造需求记录来代替旅行身份。

本次请JT审阅的**具体**增量：

1. `TRAVEL-CONTEXT@1`、`MESSAGE-send.2`、`MESSAGE-TRAVEL-REFERENCE@1`、`MESSAGE-TRAVEL-LEASE@1`。计量继续复用`USAGE-REGISTERED-EXIT@1`既有可信guard注入点与唯一MeteredExitCore，不另发布计量协议或复制算法。
2. 四张新元数据表、receipt新增一个nullable协议标记列/约束、八张既有MESSAGE/RUN表追加restrictive RLS；新增的精确权限见第8节。**方向批准不包含这些变更。**
3. 本票需按现有registry归组登记四张表及message新标记/敏感字段，不机械创建四个同义domain store。`backend/storage-registry.json`不在原B文件清单，申请仅添加本票对应登记的写权；未批准前不修改。A生成/消费所有ios产物，C实现typed-memory，不由B代改。

这不是云/真实账号/真实模型/外部服务/密钥/生产迁移授权。合同只冻结不批准DDL时，本票停在producer实现之前，所有新L0/L1保持UNRUN。

## 2. 身份和生命周期

身份键为`(owner_scope, context_id)`。owner_scope只由canonical AUTH的issuer/subject/environment及既有`scope_for`映射产生，任何请求不能传scope/owner。context_id由服务器生成32位小写UUID hex；ID和版本本身不是授权证明。

- create：显式原action，生成owned身份，version=1、active=true。无conversation/Trip/NEEDS也可创建；不自动创建这些业务记录。
- advance：显式CAS，版本+1、保持active。含义是失效旧运行引用，不代表新旅行、不改任何Memory/NEEDS事实。
- deactivate：显式CAS，版本+1、active=false；本版单向，无reactivate、改owner或物理delete。新的旅行显式create新ID。
- 版本不回绕、不减小；停用不等于删除。历史动作/回执保持原字节，不自动把旧current条目搬到新旅行。
- C的memory item/source版本与scope epoch、B context版本、conversation选择epoch是三个不同领域。advance不重写C值；同一identity仍是同一次旅行，C自己判断条目授权/到期/撤回。

拟议API：

| API | 原字节/返回 |
|---|---|
| `POST /v1/travel-context-actions` | `TRAVEL-context-action.1`；同scope action_id+原字节返回原`TRAVEL-context-receipt.1`，不同字节INPUT_CONFLICT；事务只做一次动作 |
| `GET /v1/travel-context-actions/{action_id}` | 当前owner读取原不可变回执；null不证明在途动作从未提交，不授权换ID重发 |
| `GET /v1/travel-contexts/{context_id}` | owned当前id/version/active/created_at；不可用与他人不可枚举。读取不是执行lease |

动作体恰好为version、action_id、operation、travel_context。create的travel_context=null；advance/deactivate为`{"id":"<server-id>","expected_version":1}`。action_id非空ASCII标识、≤96字符；expected_version是真整数≥1，拒绝bool/float。原bytes和原回执在动作账本内持久化，CAS和回执同事务；ACK未知只核原action，不默认重试。恢复后的重提须明确确认且保留原ID/bytes。

## 3. MESSAGE-send.2与不可变原关联

新写路径`POST /v2/messages`，不改变`POST /v1/messages`或send.1解析规则。send.2保留send.1原八字段含义，trip_id仍只能null，额外**必填**：

```json
{
  "travel_context": {"id":"<owned server-id>","expected_version":1},
  "needs_reference": null
}
```

travel_context也可显式null，表示没有选旅行；缺字段不是null。needs_reference在creation_intent=none时必须null，consider_trip时必须显式`{"id":"<owned needs_id>","expected_version":<current>}`。该新字段只引用现有NEEDS记录/版本、复用原NEEDS守卫，不新增需求事实或修改旧NEEDS合同：**避免同conversation改选旅行后默默沿用旧conversation的NEEDS selection**。这是本次MESSAGE冻结需要JT确认的具体字段；send.1仍走原选择方式。

接收事务固定顺序：canonical AUTH → MESSAGE scope `FOR UPDATE` → 原message_id回执优先（同bytes只返回原回执）→原chat/head CAS →真实owned context active/version与显式NEEDS引用核对 →更新选择epoch →同事务写receipt、原bytes、travel_reference、NEEDS/计量requirement及delivery。没有Trip前置；不在MESSAGE锁内拿RUN写锁。needs_reference是本稿相对C方向稿的必要增量：只引用已接受的NEEDS记录/版本，不冻结#14未定的需求内容，也不把它宣称属于某旅行。

### 对话选择epoch防ABA

旅行身份独立于conversation，但原运行的当前性还要知道用户是否切换了该对话的旅行：

- 不建第二个可变“当前选择”表。`cj_message_travel_reference`按原message顺序保存不可变选择，最新一条即当前选择；复用新表 `(scope,conversation_id,generation,sequence)` 唯一键的倒序扫描，不另建同义索引。
- selection_epoch取当前连续相同选择片段的**首个message sequence**：第一条send.2用自己的sequence；相同kind/id/version的新消息沿用前值；引用变化（含travel↔none、A→B→A）取本条新sequence，严格前进且不回绕。
- 在接受时由服务器/DB生成原selection_epoch，同时存原message/run/generation/sequence/input_sha256及travel id/version。以后不更新；新mode每个新receipt强制有ref，因此最新ref的sequence必须等于chat head。
- effect lease要求原epoch仍为当前epoch；A→B→A后旧A引用的epoch不复活。不能只比ID/hash或最新选择与旧值相同。
- 不复用chat.epoch/history cursor或last_sequence当选择epoch，避免把同旅行正常下一条消息当切换。旧send.1不回填此表。

同旅行跨conversation得到同一个travel键、各自选择epoch；同conversation新消息显式选B就只绑定B。旧A结果仍是原A历史数据，不改标签；切换后未提交的新输出拒绝，已显示/已发给provider内容不能撤回。

### 读与恢复

拟议`MESSAGE-accept.2`返回原receipt加`MESSAGE-travel-reference.1`投影；`GET /v2/message-send-status`保留receipt/head证据并返回对应原reference。只有原receipt非null才有对应reference；send.2已存但metadata缺失是unavailable/unknown，不能默认none。

同ID原bytes重放先读原回执，即使context已变化/停用也返回历史接受事实；不因此获得新执行权。无回执且会话位置仍可用时，send.1原发送许可的原ID/bytes及恢复确认规则继续适用，服务端仍逐次核send.2引用；绝不自动刷新expected_version或换旅行/消息ID。known owned context版本过旧/停用在锁内拒绝，不留receipt/outbox；错owner与不存在一致拒绝。收到非200/ACK未知时不能据null推断从未发生。

V1读接口不能把send.2剥掉引用投成legacy；不支持时明确版本不可用。新兼容消费者可以安全读取旧原bytes/回执，旧pending不迁移、不推测旅行。

## 4. 提供C的键和lease

私有`OriginalMessageContextRef`由B仓储验证原receipt、raw hash及复制列后构造一次，字段固定：

`owner_scope, conversation_id, generation, message_id, run_id, sequence, input_sha256, message_version, context_kind, context_id, context_version, selection_epoch`。

| 原引用 | C选择输入 | 含义 |
|---|---|---|
| send.2 / travel | `ContextRef(kind="travel", id=context_id)` | context_version是原接受版本；B lease核真实当前性，不能由C凭版本相等放行 |
| send.2 / none | `None` | 仅long_term；不回退conversation current |
| draft.1/send.1 / legacy | 显式legacy模式`ContextRef(kind="legacy", id=conversation_id)` | 保留#226旧语义；不解释成travel。新mode没有旧pending执行 |

C `MEMORY-manual.2`的context.id/expected_version对应本travel身份/当前CAS版本；其数据库FK准确目标为`public.cj_travel_context(scope,context_id) ON DELETE RESTRICT`。C.scope与MESSAGE.scope现由同一`scope_for`产生（local_app.resolve_memory）；无需猜prefix或另建owner映射。C新增context_kind/生成的travel_context_id和索引由C另行审批/实现，B不执行其DDL。

拟议B接口（都不是任意caller上传的Context）：

- `MessageContextAuthority.read_original(binding)`：fresh AUTH/真实owner/origin读取，返回不可变数据；允许历史失效引用查询，不给执行许可。
- `MessageContextAuthority.hold_for_effect(binding)`：在host已有RUN事务内进入，取得MESSAGE scope共享锁、选择快照和owned context共享锁，产生活跃`MessageContextLease`；错owner/run/generation/原hash/epoch、停用或版本变化拒绝。
- `lease.reference`供C构造typed选择；`lease.original_message()`复用本租约内已验证的原Stored，不在持锁期间重新调用会另开`MESSAGE FOR UPDATE`事务的`messages.query`。
- `lease.check(binding)`仅在原线程/原binding/with生命周期内有效，每次fresh AUTH；持锁保护的T状态和原不可变对象不层层重校验。C仍通过自己的canonical require_current重读epoch、完整有效条目/来源及expiry，不只比较hash。
- `authority.valid(binding)`可适配现有Service.valid：preflight用短租约验证；effect内**重入同一已持有租约/连接**，不再开第二条MESSAGE scope写锁连接，避免自锁。没有active许可逃逸、默认ALLOWED或新签名key。
- manual.2 current保存可用同一B`hold_current(context_ref)`，先取得M/T再进入MEMORY；无context不能保存current。原Memory操作历史查询/同bytes原回执先按旧规则核，不能因context后来失效就把已提交保存改成失败。

无context的三个不同情况：显式null有效，只给长期值；缺字段/非法ref在请求边界拒绝；已存send.2缺失/损坏关联返回unknown，不猜conversation或None。

## 5. 锁图和最终检查（待实测）

源码复核：现有provider首步的USAGE reserve/claim各自短提交；NEEDS provider前检查会释放。现有draft publication在NEEDS lease内调用check_publication，**实际存在NEEDS→USAGE持锁边**，不能把“RUN→USAGE→NEEDS”当作已成立的全局持锁图。C r1的RUN→NEEDS→B→MEMORY→USAGE建议也需加入MESSAGE scope与重入规则，不能仅据文档宣称无死锁。

本稿按实际代码采用同时持锁顺序`RUN → MESSAGE → TRAVEL → MEMORY → NEEDS → USAGE`，USAGE每次短提交后释放，绝不持USAGE再取前面的锁。M/T以及MEMORY已取得后复核必须重入同一lease/连接，不再形成MEMORY→第二条MESSAGE连接的反向边：

| 路径 | 取得/释放 |
|---|---|
| Travel动作 | M写锁→T写锁→动作回执提交；不取RUN/MEMORY/USAGE |
| send.2接受/升级 | M写锁→T共享/显式NEEDS核对→receipt/ref/selector/outbox提交；升级只普通读RUN检查，不取RUN写锁 |
| C manual.2 | M共享→T共享→MEMORY scope；B锁覆盖C实际commit |
| provider准备/首步 | prepare_input/原operation先持久提交；RUN→M/T→C MEMORY→必要NEEDS，调用现有Core。audit/reserve/claim/materialize后USAGE已释放，现有call.guard组合B/C当前性，再做原clock最后检查并直接推进provider；外层ExitStack让lease保持到RUN commit，不持整个流 |
| delta/completed/proposal | 每次新RUN临界区重新取M/T及C MEMORY，proposal再取NEEDS；元数据/来源准备后最终检查；所有lease覆盖真正副作用和原RUN receipt |

不增加新的计量版本：现有PreparedCall.guard已经调用可信Service.valid，host在effect生命周期把它组合为B origin lease.check和C active memory check，之后由原Core执行最后clock检查。C typed消费者不再用旧provider外套在clock之后追加SQL检查。缺必要active lease时拒绝，不能以cached ALLOWED替代；preflight短检查不是执行许可。guard只能是已审host代码，不能从JSON注入Python函数。

现有prepare_input在最终lease之前；Core内materialize/audit是可信适配器准备/日志，不承担Memory/Travel业务写入。外部合法编辑按lease先后排序：编辑先commit则获取lease时拒绝；publication先持锁则该有限step先完成、编辑随后生效。不能为让测试回调在持锁中再写相同业务行而绕锁；违规重入应有界失败并保留原UNKNOWN。文件撤权或时间到期仍由最终AUTH/require_current/clock检测。

publication时间检查拆成“原ledger/start/clock的短事务准备数据”与“所有lease/准备结束后的纯clock最终检查”；数据不是许可，最终检查保留同一finite/单调/max_seconds语义，不在NEEDS持锁后再回取USAGE。若最终lease拒绝时原claim已持久化，保留原UNKNOWN曝光，不能因provider=0就退款/归零。旧counter/UNKNOWN/limits断言全部保留，加等待/初始化耗时负例；这项内部调序属于本次冻结对象，不提前修改代码。

M/T用`FOR SHARE`而非FOR UPDATE：阻止版本/选择写入，并兼容C typed FK的KEY SHARE；C memory.current_context仍取原MEMORY scope锁。row-lock兼容和一致顺序依据[PostgreSQL17锁文档](https://www.postgresql.org/docs/17/explicit-locking.html#LOCKING-ROWS)。只对已发布正式写入口声明此顺序，不声称防御恶意管理员/任意SQL。真实双顺序barrier测试全部UNRUN。

C当前`MEMORY-RUN-CONSUME@1`明确按conversation选择，保持不改。新mode不得配置它当travel消费者；C应另发布typed版本（建议@2）并使用B原ref/lease。C capture可短持M/T→MEMORY编码后释放，返回数据而非许可；随后每个实际step重新取得final leases。typed版本将check组合进既有Core guard，不沿用旧provider外套在最终clock之后再做额外I/O。`_event`、真实proposal提交及RUN commit均需覆盖，不只管provider起点。

release/cleanup不再获取外层RUN/USAGE/NEEDS锁；若RUN/proposal已提交后读lease cleanup失败，只保留原事实与unknown/query-only，不报已回滚或重做。expiry最后检查发生在实际副作用前，不承诺提交瞬间的绝对时钟原子性。晚到可信费用回执只结算原ledger/attempt，不要求已失效context重新给执行许可。

这里的live lease保护新provider步骤、text_delta、completed及新proposal/effect等可用输出。failed/cancelled/context_invalid/unknown/budget_denied等**原动作终态/诊断记账**沿既有RUN fence与原owner/origin规则处理，不要求已经失效的旅行/记忆重新授权；否则将无法记录拒绝。此豁免不允许新私密正文、计量派发或新业务effect，也不绕过canonical owner。started之前依赖未知的处理见下表，不扩展旧RUN状态机。

## 6. 失效与阶段语义

| 阶段/情况 | 结果 |
|---|---|
| 接受前缺字段/错类型 | 400 INVALID_INPUT；无receipt/outbox/可执行RUN/provider |
| 接受前错owner/不存在/依赖未知 | 相同不可枚举unavailable/unknown；不造None、不接受 |
| owned context停用/版本过旧 | 409 TRAVEL_CONTEXT_CONFLICT（身份动作）/ MESSAGE_CONTEXT_CONFLICT（新消息），category=conflict/outcome=failed/recovery=reconcile_original；同锁内未接受，不刷新版本；原已接收bytes仍优先返回原回执 |
| 接受后、开跑前已知失效 | 同原run_id可记queued→context_invalid，provider/新attempt=0，不新建别的run |
| started前读取/准入未知 | 保持原queued/未ack，报unavailable/unknown并核原动作；不强写冻结规则禁止的queued→unknown，不重绑引用 |
| started/claim后未知或失效 | 既有unknown/context_invalid及原曝光；不重发、不清零，不修改原message ref |
| 同对话A→B→A | selection_epoch永久前进，旧A运行不因ID又相同而复活 |
| 历史读取/晚到原费用 | owner可核原事实；数据/原回执不是新step/发布lease，context失效不阻断原费用对账 |

新增不可枚举资源错误为503 TRAVEL_CONTEXT_UNAVAILABLE / MESSAGE_CONTEXT_UNAVAILABLE，category=dependency、outcome=unknown；写/不确定提交用reconcile_original，纯读用retry_safe_read。动作commit ACK未知为503 TRAVEL_CONTEXT_OUTCOME_UNKNOWN；消息仍沿用MESSAGE_OUTCOME_UNKNOWN。INVALID_INPUT与INPUT_CONFLICT沿原failed/do_not_retry，AUTH沿ACCESS_DENIED/ACCESS_UNKNOWN，不增加或放宽BASE枚举。C manual.2“current+无context”的具体MEMORY错误码由C新版本定义，B不代改。

## 7. 兼容与激活

仅新增parser拒绝未知version不足以证明旧worker安全（旧路径曾直接json.loads text）。本稿用新的持久`cj_message_context_profile`显式升级scope，并增加数据库兼容门：

- 旧producer/profile、MESSAGE-send.1、MEMORY-manual.1、旧原bytes/回执及原M2 Meter profile均保留。不改scope或period，因此不生成第二账户/重置UNKNOWN。
- 先发布并验证兼容consumer：可识别send.2/原reference、缺配置拒绝、final lease、schema与存储边界；A更新ios消费者，B不代写。M2计量配置原格式不变，新travel配置独立显式。有既存MEMORY scope时不得挂接当前conversation-only的MEMORY-RUN-CONSUME@1或静默关闭memory；须C typed版本就绪。无MEMORY scope的B供给验证可只验证引用/lease，不冒称C记忆集成。identity create本身不要求meter或已有chat；MESSAGE新mode激活要求原M2 profile和兼容组合就绪。
- operator在M写锁下核所有未ack delivery（含inactive）为0、RUN无queued/running，再插入单向profile；先停旧worker。新producer后启用。UNKNOWN旧账本不抹掉，原关联不迁移。
- profile scope的新receipt由DB填`travel_reference_version=1`，并通过deferred双向FK强制同事务有原travel ref；旧receipt保持null。旧writer缺ref提交失败，不能回填旧receipt假旅行。
- 八张MESSAGE/RUN core表**追加restrictive** policy：旧scope原规则不变；已升级scope要求新consumer的LOCAL `cj.message_context_abi=MESSAGE-TRAVEL-CONSUMER@1`。profile的owner可见性不靠ABI，避免旧consumer因看不到profile而fail-open；原owner policy仍AND保留。[restrictive policy语义](https://www.postgresql.org/docs/17/sql-createpolicy.html)。
- ABI是已审代码兼容标记，不是认证/权限token；owner仍由canonical AUTH＋原RLS决定。新配置缺失仍拒绝执行，不能因为ABI值就fallback。新LOCAL键加入checkout/物理连接复用清理检查，不作为secret或新key。
- 固定旧main`3caece7`及C旧消费head`3b1c0df`实际跑旧正式入口：新工作0调用/0新ack，旧mode正常；只把新parser拒绝当旧worker证明不合格。旧未知二进制不是激活后的回退版本。

## 8. 具体schema、权限与down

四表：`cj_travel_context`、`cj_travel_context_action`、`cj_message_context_profile`、`cj_message_travel_reference`。receipt只加nullable `travel_reference_version`和关联约束；不重写raw/hash/既有字段。marker由profile产生，双向deferred FK要求原receipt与ref一起存在；不在SQL里重解析旧raw JSON。B读出边界一次核raw SHA、实际wire版本/marker与复制字段；v2缺metadata或旧raw配新marker一律拒绝。具体约束、guard函数和grants见up草案；号在实施前按最新manifest顺延，不预占0018。新索引/约束若不适应既有合法数据，整事务失败后再审，不能截断旧ID或改bytes来凑通过。

| 资源 | cj_m1_runtime新增权限 |
|---|---|
| context | SELECT、INSERT、UPDATE(version,active,head_action_id) |
| action / 原message ref | SELECT、INSERT；无UPDATE/DELETE/TRUNCATE |
| profile | SELECT；INSERT仅operator，runtime不改 |
| 兼容helper | EXECUTE仅M1；SECURITY INVOKER，无BYPASSRLS/新高权role |
| 既有八表 | 不增加原表级GRANT语句；追加restrictive RLS。receipt新列会继承既有表级INSERT/UPDATE，这项能力也在审批内；BEFORE trigger由profile设置marker并拒绝后改，新mode原字段不可变 |

四表ENABLE/FORCE RLS。C只需将自己的nullable travel_context_id复合FK连到B `(scope,context_id)`，不FK到可变version；C旧行仅legacy，不自动转换。C原RLS、item/status管理权限与typed列/索引迁移不在B SQL中。根生成脚本默认同时写ios；B不能借自动生成越过A owner，只可用临时/check模式并由A提供其生成/消费变更。必要消费者未就绪时记录停点，不跳过一致性或CI门禁。

down先排他锁、检查四表和receipt marker全空、无C/其他owner外部FK，再删本次policy/trigger/FK/函数/列/表；不CASCADE、不清空数据、不压travel为conversation。任何新业务行/profile/marker或C依赖存在即整事务拒绝。代码回退保留schema/原记录，只能退到识别新版本且fail-closed的兼容consumer。新增数据域的cleanup/restore登记和#27接入未完成前不进入真实用户/发布验收；本票不加删除权或自动跨域级联。

## 9. 正负例与验收范围（全部UNRUN）

配套JSON列出：同对话A→B→A、同A跨对话、无Trip先建身份、显式none、字段缺失、错owner、版本推进/停用、原bytes重放、ACK未知、重启、伪造/逃逸lease、旧consumer与非空down。每个场景要求实际签名API、受限角色PG及正式worker/FakeProvider；C临时/长期值必须由C真实typed producer保存读取，不种两份假Context来宣称#227完成。

新合同检查、DDL语法/空库往返/非空down、RLS/旧consumer、真实锁序、B实现、新L0/L1、C/A集成全部UNRUN。JSON语法/链接/diff检查仅证明设计文件可读。既有C Part1同conversation证据、B #242/#243 PASS不替代本票新证据。

实现后按本线完整协议：受影响模块/合同及默认test/PG（当前基线增加memory_run，不能固定沿用旧18组计数）、精确head全CI、独立红线APPROVE、锁head合并、main全绿、回写关闭；再在#227/#228通知真正冻结的版本、键和交付head。父#12仍等C/A剩余框，不由B桥接票代闭。
