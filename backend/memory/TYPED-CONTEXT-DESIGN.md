# C：MEMORY typed-context 契约与迁移详细草案（未执行）

关联#227；JT已批准跨线方向，授权按owner细化契约和迁移设计。本文只定义C建议，
不冻结B的TRAVEL-CONTEXT/MESSAGE，也不授权新增DDL或运行权限。旧MEMORY与
MESSAGE已冻结版本、已应用迁移和原回执不改。B表/lease未冻结前不实现其消费。

## C契约候选：MEMORY-manual.2

新写入仍沿用同一个MEMORY Service/原操作账本。新版本请求使用新版本endpoint，
不在manual.1中加入可选字段。字段集合如下，禁止额外/重复字段：

```json
{
  "version":"MEMORY-manual.2",
  "operation_id":"operation-1",
  "item_id":"item-1",
  "subject":"self",
  "slot":"pace",
  "kind":"preference",
  "text":"本次以慢节奏为主",
  "extent":"current",
  "context":{"kind":"travel","id":"context-A","expected_version":1},
  "occurred_at":"user reported; exact date unknown"
}
```

- subject/slot/kind/text/occurred_at、事实/经历/偏好/inference、candidate与正式值、
  source生成、保存中/失败/ACK未知、原字节重放/冲突与manual.1共用领域规则。
- long_term的context必须null；current的context必须严格为上述三字段，kind必须
  travel，id为非空有界UTF-8 opaque ID，expected_version为真正int且≥1。
- owner/scope/source_id/source approval/最终status/version不可由请求提供。
- context.expected_version只约束这次保存的原接受时点。服务器必须经B的canonical
  principal-bound上下文接口核owner、存在、active及实际version；不能只比传入版本。
  读/发布时上下文是否当前由B判断，单条记忆是否授权/有效由原MEMORY判断。
- 记忆source_version与旅行上下文version是不同领域，不借用其中一个表示另一个。
  推进B上下文版本不改写历史保存回执；停用/重启能否恢复其原条目须依B冻结的
  生命周期语义，不能越过MEMORY自己的withdrawn/disabled/source授权状态。

候选V2 list/detail投影含明确context类型；旧条目可表示为conversation引用或长期
null。旧原输入/来源/version/receipt字节保留，不以新投影回写或自动“迁移旅行”。
V1 list/detail面对V2条目必须明确版本不支持或由已核实的旧字段兼容投影处理，
不得把旅行ID当旧conversation。实施前核A现有解码器；不假定忽略新字段就兼容。

## 单一canonical选择/消费

新增内部不可变ContextRef(kind,id)，只由可信resolver构造。旧字符串参数仍明确
表示legacy conversation；不把相同字符串自动解释成travel。无选择为None。

current_context仍只做一次选择：long_term基础＋匹配context类型/ID的current覆盖
同slot。require_current重读同一选择及来源有效性，不另建优先级/版本引擎。
新runtime输入来自B原MESSAGE接受的引用；旧runtime候选仅保留legacy模式。

发布持锁顺序建议为原RUN→既有NEEDS保护→B上下文lease→MEMORY scope→原USAGE
短事务；manual保存为B上下文lease→MEMORY。B必须对照真实锁图确认这一顺序，
不能仅凭文档宣布无死锁。选取上下文/策略/来源回调在最终fresh AUTH与currentness
前完成；全部相关lease保持到真正副作用提交。已提交proposal/未知RUN ACK仍按原
动作对账，不用返回错误掩盖已发生的副作用。

## C追加迁移：具体变更建议

编号待执行前按最新manifest分配，**不是预占0018或其他编号**。

`cj_memory_item`新增：

| 项 | 设计 |
|---|---|
| context_kind text NOT NULL DEFAULT 'legacy' | legacy用于原conversation current及原long_term；travel仅允许current |
| CHECK | context_kind IN ('legacy','travel') AND (context_kind='legacy' OR extent='current') |
| active slot唯一性 | 新唯一索引(scope,subject,slot,extent,context_kind,context_id)，条件status='active' |
| 旧唯一索引 | 在新索引已成功建立后，用这条新迁移替换旧(scope,subject,slot,extent,context_id) active索引；不编辑0009 |

所有旧行的default legacy只说明原有语义，不改raw/source/item version/epoch或原
operation receipt。long_term继续用原extent/context_id空值约束，context_kind不为其
制造第二范围。新travel使用原context_id存储真实ID，由明确context_kind消除与任意
opaque conversation ID碰撞；不靠前缀避免冲突。

B引用约束：优先为travel建立可验证的(scope,context_id)外键。因legacy行并非旅行
引用，可用数据库生成的nullable travel_context_id（仅context_kind=travel时取
context_id）作为复合FK列；旧行NULL，不回填假context。B目标表/键/删除策略尚未
冻结，因此现在不编造表名或可执行FK SQL。若B采用其他已有权威存储，先评审对应
完整性方案；不能删掉归属/存在负例改称纯caller输入。

B上下文停用是状态变化，不等于删除；物理删除关联的memory/source/operation如何
保留撤回依据由生命周期票处理。建议FK先RESTRICT，不在此新增跨域用户数据级联
删除。任何不同删除语义必须单独批准，并补防复活/误删他人数据反例。

权限：现有MEMORY四表FORCE RLS/scope policy原样保留，运行角色只增加typed保存
真正需要的列/引用读取能力；不授予item原文/version/status任意UPDATE或DELETE。
新列默认不得变成可绕过来源授权的写入口；insert仍由原受保护Service。B上下文表
SELECT由B审定其RLS/运行角色。#17的管理UPDATE权限不混入本次迁移。

### Up/Down与原消费者

- Up在单事务内锁定涉及的表/索引、核旧数据可建立新索引、添加列/约束并替换索引。
  私有空PG执行；生产/云执行不在任何当前授权内。
- 升级前保留旧message/pending/unknown关联。不能通过回填新travel_context让旧
  原动作可执行，B兼容消费者先合并/验证，再启用新生产者。
- Down首先检查不存在任何travel类型行或其他新类型持久引用；非空明确拒绝且
  保持原数据/schema。只有安全空的新类型状态下，才恢复原active索引并移除新增
  约束/列，原raw/source/ledger保持。不能压扁travel为conversation来凑回滚成功。
- 代码回退只能到识别新版本并fail-closed的兼容消费者，保持schema及原状态；
  更早的worker直接读原JSON可能执行未知消息，不能作为已激活后的回退保证。

## 样例/验证设计（typed版本与新增DDL全部UNRUN）

正例：current+owned active context-A/v1；long_term+null；同slot在legacy ID=A与
travel ID=A分别存在；同travel跨conversation取得相同current；同conversation改选
B只得B current和原长期值。原请求bytes重放仍只返回原回执。

反例：布尔/负数/缺失context version、current+null、long_term+travel、未知kind、
额外owner/source批准、重复JSON字段、无效UTF-8、错scope/无context/停用/过期lease。
原保存/发布之后AUTH变化或ACK未知不能被当作重发许可。

迁移测试：1..届时最新链up/down/up；旧数据/source/receipt字节哈希与RLS/ACL保持；
同ID跨类型的索引正例和同类型重复active拒绝；非空down拒绝且数据不变；运行角色
跨owner SELECT/INSERT/UPDATE、无scope及物理连接复用拒绝。仅初始化测试设置环境，
业务写读使用受限角色与真实B上下文/签名API，不用初始化身份冒充已授权保存。

完整组合：正式worker/FakeProvider＋B当前计量套件、#17真实编辑/启停、既有撤回/
到期fence、旧消费者、缺配置、重启/UNKNOWN/两种锁序。App由A单独提供证据。

## 剩余冻结点

B：上下文身份/生命周期与原MESSAGE引用、scope/FK、受保护lease/锁序、原消费者。
C/JT：本typed wire/投影兼容与上述实际DDL、权限/up/down详细实施稿。
上述冻结/审批未完成前，不改B代码、不添加/执行迁移、不把#227标为完成。
