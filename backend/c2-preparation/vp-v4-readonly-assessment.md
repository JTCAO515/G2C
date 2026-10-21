# VP-V4 优先只读评估：共享可行性与对象处置门槛

最新JT方向：优先评估旧 VP-V4，次选收费新项目；“旧函数表无用可删”是方向，不替代精确对象/影响/恢复清单的不可逆动作确认。本轮只准备/只读，不 DROP/DELETE/TRUNCATE，不删 Edge/Auth/Storage，不改RLS/provider/JWT/网络/安全配置，不恢复旧VP开发。

## 当前事实和缺口

支持线程官方只读盘点已复用：[原始metadata](</Users/jtsm5p/Documents/Codex/2026-10-21/task-6/vpv4-readonly-inventory.json>)，时间 `2026-10-21T13:54:00Z`，SHA256 `8195bcc9821c97d287d4f336f0a6a8e8937f7b183cbd01ef477f897af9ecf57c`。文件确认 `VP - V4 / dzqdzetcctkhbrhlxxgn`，organization显示 `Go2China`、plan `pro`（Main称Go2China Pro），region `ap-southeast-1`、`ACTIVE_HEALTHY`。本owner只读取这份本地metadata，不重复远端扫描、不读业务行/函数正文/密钥。

真实数量：123表/视图，其中80业务清理审查候选；263函数，其中160应用函数候选；67非内部触发器、7事件触发器、134FK、71策略；EdgeFunctions=0、buckets=0不能推出Auth为空。runtime metadata有PostgREST14.5、pg_cron、pg_net等连接；public有61个authenticated可执行函数。Main另转交当日12:58UTC多旧表扫描和近1h活动，调用方UNKNOWN（原JSON未列逐表扫描时间，本owner不补造映射）。不能称旧业务已停止。

精确静态风险：启用的 `auth.users.hide_text_on_user_delete` 调用 `turn_private.hide_text_content`，不能盲删其函数/依赖或清Auth；`ensure_rls`调用`public.rls_auto_enable`，与平台event triggers/扩展保留。backup/recovery/外部消费者/动态依赖未解决，Pro资格不证明实际可恢复。

[对象级派生分类](vp-v4-object-assessment.json)列出80关系及160精确函数签名，并复用原metadata中的FK/trigger/policy关联；所有删除许可false。系统对象/事件触发器/扩展保护清单与已配置Auth关联单列。**“清理审查候选”不等于“已确认候删”**：当前可执行候删清单为空，候选多数保持UNKNOWN，需对象owner与动态消费者/恢复证据补齐。函数正文未读，函数内动态依赖不能凭metadata认定完整。

## 不删除就开发：可以做什么、不能证明什么

- **现在可做**：原CJ隔离克隆中的本地Auth/iOS/API代码、synthetic契约/错误、迁移提案；不接旧真实用户/数据。当前基础工程C1无鉴权且loopback-only，不得公网开放。
- **获精确后续授权才可做**：在经核VP项目内新增独立非暴露CJ schema、专用非owner runtime/migration角色和逐表权限；默认不访问旧schema/旧账号，不修改旧对象。旧项目里该schema/角色是否已存在/冲突先由盘点确认，不能直接create。
- **不能用schema隔开**：同一个Supabase项目的Auth用户池、issuer/JWKS/签名轮换、provider设置、SMTP/模板/redirect Site URL、注册/会话策略/创建前hook、DB实例资源/恢复与部分网关配置。CJ邀请逻辑只应授权CJ业务，不应把旧VP用户全认作CJ，也不能让项目级signup hook拒绝旧VP原本合法的新用户。
- **当前明确阻断**：同项目CJ新用户通常也获得Supabase `authenticated`会话；已见61个public函数对该role可执行。CJ Python API的邀请/私有schema门禁不会阻止用户拿同一JWT直调旧PostgREST/RPC。函数正文、旧策略和动态消费者未审，无法证明这些新用户不会触达旧能力；隐藏publishable key也不是权限隔离。当前不能向真实CJ游客开放共享Auth。若需要改旧grants/RLS/token hook或provider消除风险，必须另列影响、owner及旧服务回归后批准，不能本轮执行。
- **拟命名空间**：`cj_private`仅提案，metadata没有已验可写lease或权限；先核存在/空schema冲突、命名和新角色授权，再review迁移。它能限定CJ自身表的访问，不能修补上述旧RPC、共享Auth/provider或资源竞争。
- **可接受门槛**：确认哪些旧服务仍在用、现有Auth行为与配置的兼容范围；实现按CJ应用/主体资格隔离且不损伤旧业务的验证；权限与资源配额可满足；恢复范围可接受。若需全局改变Auth/provider/SMTP/JWT或旧客户端不能区分，不“为了省钱”强行共用，明确旧项目不适合该C2部分，再审收费新项目。
- Google/Apple旧provider即便已启用，也不代表CJ bundle/audience/callback可用；不能复制旧secret到代码，不能替换第一client ID或旧callback。旧账号不自动迁移/继承，新增CJ账号及provider绑定也须确认不会触发旧消费端或清理任务。

因此，“独立schema可以写本地代码”与“在旧项目真实联调可放行”分开。目前后者未证实，C2仍UNRUN。API HTTPS入口A/B与这一数据库/身份选择正交；Supabase Auth URL不是CJ API URL。

## 对象分类规则（待真实盘点填充，不是实际删除表）

| 分类 | 判定所需证据 / 处置 |
|---|---|
| 保留 | 平台/产品仍需、备份恢复依赖、或明确owner保留；记录用途/调用/约束/恢复关系，不改 |
| 候删 | 用户标为废弃，且已拿到准确对象身份、全部静态与动态消费者核查、依赖/副作用和可恢复证据；只是候选，仍不执行 |
| 系统不可动 | 平台管理对象、系统schema/扩展内部结构、Auth/Storage/Realtime等系统关系；不可把业务“没用”结论外推至系统对象。实际对象必须按盘点归类，不编造系统表列表 |
| 仍连接旧服务 | 旧部署/原生/Web/Edge/外部任务或cron/hook/trigger/publicRPC仍引用；不得删除、改签名/策略或占用回调；先owner确认消费者退役/解绑与结果读回 |
| UNKNOWN | 身份、用途、权限、动态调用、对象owner、备份或恢复任一未知；保持不动，不因row_count=0/近期无日志/函数名看似旧而升级为候删 |

同一对象可带多项理由，但最终处置取保护性结论：系统/仍连接/未知不能成为可执行删除。没有对象级盘点时，当前所有未列对象的处置为UNKNOWN，而不是0风险。

## 每个候删对象必须补齐的可审查记录

1. **身份**：官方project ref、schema、对象类型/完整名称；函数含参数签名，Edge含部署版本/入口；表含关键约束/依赖及权限。不要只给label或模糊前缀。
2. **静态依赖**：FK/views/materialized views/functions/triggers/policies/grants/extensions、cron/数据库webhooks/发布订阅及存储引用；平台目录与业务对象分开。仅pg_depend不足以证明所有文本/dynamic SQL/RPC/HTTP消费者已列全。
3. **动态/外部消费者**：已知旧服务部署与配置归属、实际代码动态/字符串调用、Edge/function入口、异步任务/移动端缓存与旧App版本；安全读取脱敏证据，由对应owner确认；未拿到consumer源/真实路由就留UNKNOWN。不得发测试写请求给旧服务验证“在不在用”。
4. **备份/恢复**：实际backup ID/时间/region/类型/范围、可恢复权限/限制、匹配的schema/functions/grants、Auth/Storage/Edge资产及secret管理来源。不能以Pro计划有daily backup推断该对象已备份；DB备份不自动包含所有外部对象/Edge代码/secret。需独立隔离恢复或等价可核对恢复演练及校验结果；没有则UNKNOWN。
5. **影响与操作**：精确将删对象、受影响消费者/数据/授权、停机与回退顺序、不可恢复部分、清理/留存批准，给具体拟执行动作以供JT确认。不要使用CASCADE兜底、批量按前缀删除或先删后看报错。
6. **确认边界**：只对确认的project+对象+方法+时间窗有效；未列的旧数据/系统对象/权限保持不动。删除后需实际读回与适用旧服务回归；本lease没有该执行权，写准备材料不等于拿到确认。

## 备选分支与新建项目

Supabase分支官方描述为独立实例/凭据、默认不带业务数据，但会继承部分Auth/API等配置、Edge及迁移来源；不能称为“空白CJ”或“免费旧项目隔离”。未批准创建分支，不自动绑定GitHub/部署/merge至旧项目；如果纳入选项，需单独报价和依赖/敏感配置评估。[分支官方说明](https://supabase.com/docs/guides/deployment/branching)。

收费新项目是优先旧项目评估不满足时的备选。Main提供官方get_cost假设报价monthly USD10，本owner未读原回执、未confirm_cost/创建，实际组织credit/计费周期/税/额外用量未核；SMTP、Cloud Run、域与Apple账户费用没有因此获批。先把旧项目的准确共享风险与收费备选的实际费用并排交JT，不以未确认报价决定架构或执行收费。

## 具体待决（交 Main / JT，不等待时继续独立代码准备）

1. 是否接受先保留全部旧对象，只评估 `cj_private` 与显式CJ成员/邀请门禁；当前本lease仅准备，新增schema/角色/迁移仍未获应用权限。
2. 谁负责61个public authenticated函数及相关策略/旧消费者的定向语义审计，是否能在不改坏旧服务的前提证明CJ新身份无旧能力；未证明前不开放游客账号。
3. Google/Apple/SMTP/redirect/创建前hook若需全局配置，是否可与旧VP现行行为共存；若不可共存，旧项目不能满足这部分C2。用户不在电脑的登录/2FA/签名/域控制台步骤保持跳过。
4. 真实备份/恢复范围、恢复点及隔离演练由谁取得；无证据不删。以后任何删除另交精确对象/影响/恢复记录审批。
5. 若旧项目隔离门槛无法满足，是否批准新CJ项目的具体monthly USD10报价回执/组织/地域及额外SMTP/API托管费用；目前没有费用确认或资源创建权。

## 本段结论

官方身份与精确静态metadata已复用；80/160候选已生成保守分类及依赖索引。外部/动态消费者、恢复实证与共享Auth兼容性仍 **UNKNOWN**；没有可执行删除许可。未删除对象、未改配置、未复制凭据。此未知只阻旧资源真实操作/放行，不阻前述本地代码与准备；不可将“支持盘点进行中”计为旧库隔离PASS。
