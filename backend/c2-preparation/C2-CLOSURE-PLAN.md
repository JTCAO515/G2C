# CJ-005 最短 C2 收口方案（2026-10-23，仍 BLOCKED）

核对基线 `dc29bb3634e63d8f065c38d39a7a0059f76cfa53`。本轮只做资源/源码只读核对与具体准备；没有创建资源、试发邮件、修改数据库/权限/证书、启动服务或安装 App。机器可读提案见 [c2-approval-packet.json](c2-approval-packet.json)，当前事实见 [只读记录](evidence/2026-10-23-readonly-state.json)。这些文件不是运行配置或执行许可。

## 1. 原门槛和实际授权

[Issue5](https://github.com/JTCAO515/G2C/issues/5)要求新 Auth/数据空间、手机可达 HTTPS、配置隔离、版本化初始化及私有存储约定；不依赖模型调用。本方案选择已有 NEEDS 作为首个真实持久化对象，不另建演示业务表，也不把 /probe 当 C2。

[PR62](https://github.com/JTCAO515/G2C/pull/62)已合并 `c181b7fc22b37605c2bd7b629a337a54105c6fb8`，明确只接受离线计划/准入/登记，**组合 apply 仍 BLOCKED**。原 `initialization-plan.json` 的 apply_enabled=false/apply_order=null，MESSAGE/RUN/USAGE不是登记迁移；本轮不更改。原准入 checker 只识别本机指定私有 Unix 空 PG。新 Supabase 包含平台 auth/schema/扩展，也不是这个 checker 的可接收目标；不能改参数跳过门槛或把平台对象误判为旧业务。

现有可见连接中，Go2China 组织 `ppfsagymaozpbkbarhes` live plan=pro，只有旧 VP-V4（Singapore）；另一连接 JT-C 只有旧 VP-Final-V2（Tokyo）。没有列出新 CJ 项目；未连接的其他账户仍 UNKNOWN。当前派工/HANDOFF/resource-request 中未见获准的新 ref、DB、云 project、预算、HTTPS origin、发信域或指定设备范围。资源存在不等于获准使用。本轮不读取旧业务行/账号/密钥、不扫描旧库，也不以旧 metadata 数量作当前运行证明。

最新禁止旧库/旧账号迁移覆盖2026-10-21“先评估旧 VP”的顺序。旧材料保留为历史；当前推荐全新独立目标，既有 VP 继续不动。C2不得解除 BLOCKED。

## 2. 一个具体技术推荐

**全新 Go2China-org Supabase `cj-c2-dev` + Singapore Cloud Run `cj-c2-api` + Resend Free SMTP + 一个 C2 签名 App 配置。** 名称都是候选标签，实际项目/ref/域/账单对象未分配。

| 层 | 推荐与理由 | 当前真实状态 |
|---|---|---|
| Auth/DB | 在已可见 Go2China 组织新建标准 PostgreSQL/Micro 项目；选精确 `ap-southeast-1`。独立 Auth，不 branch/restore/import VP；只需 Auth+PG，先不开 Realtime/Storage/Edge/model | 创建/费用/目标授权均缺失 |
| Python API | 新 CJ-only GCP project，Cloud Run `asia-southeast1`，独立 runtime identity/secret 权限。初始候选1CPU/512MiB、min0、service max1、并发8、30秒 JSON 请求 | GCP project、billing、部署/入口/secret权限未知 |
| 手机 HTTPS | 平台实际 service URL 和标准 TLS；不买 API 域、不装实验 CA、不改 ATS、不跟随 API redirect。实际 origin 从已批准部署读回，绝不拼接一个 run.app 地址 | Wi-Fi/蜂窝/中国境内可达性 UNKNOWN |
| DB连接 | 先选 session-mode pooler，显式新 runtime role/host/port，TLS verify-full。保留 canonical fresh idle connection/事务语义；小规模并发，不先引 transaction-pooler/session-state 兼容改造 | endpoint/角色/namespace策略未批准 |
| 邮件 | Resend Free，已验证 JT 自有 `auth` 子域，SMTP465隐式TLS，只有A/B测试收件人；不自动升级付费 | 供应商账号/实际域/DNS/试发范围未授权 |
| 手机配置 | 现有项目的 C2 build configuration，候选 bundle `space.go2china.c2.dev`，新的专用安全存储 namespace；不复用旧账号/会话 | 当前 tracked bundle是local、unsigned，无已批准C2签名/设备 |

这是现有 Python/原生/PostgreSQL 方案的运行目标推荐，平台选择仍须 Main/JT 批准后才成为执行目标。Cloud Run有平台稳定HTTPS；两家都提供Singapore地域，但这不证明具体手机网络可达。[Cloud Run HTTPS](https://docs.cloud.google.com/run/docs/triggering/https-request)、[地域](https://docs.cloud.google.com/run/docs/locations)、[Supabase地域](https://supabase.com/docs/guides/platform/regions)。跨云延迟/出网费用也需实测与报价，不能因为同城称零成本。

session pooler可避免先买IPv4附加项；实际host必须从新项目Connect页读回，不能由region推算。官方同时说明verify-full才校验证书身份；本计划不把require当完整服务端验证。[连接方式](https://supabase.com/docs/guides/database/connecting-to-postgres)。

Cloud Run对公网invocation的基础设施设置需要明确批准；业务路径仍先走canonical JWT/当前资格/归属检查，不因基础设施公开而匿名放行业务。只向指定测试者发放 App/账号。max1和账单告警都不是保证不会超额的财务硬上限。

## 3. 准确需要的数据与权威对象

1. 新 Supabase 自己的 `auth.users` / `auth.sessions` 权威，两个全新用户；不复制 VP subject/session。新 ref 的 issuer/audience/JWKS/实际 ES256 或 RS256 算法明确绑定，不能从 token header 反推信任目标。
2. **一个**经原 AUTH owner 接受的 CJ membership/invitation/稳定 scope 映射来源。建议放新非暴露 `cj_private` namespace；具体表名/列仍是待审 DDL，不在此冻结第二权限契约。映射按可信环境+issuer+subject，不按邮箱/客户端owner/token时间分库。名单变更只由批准维护身份执行。
3. 已有 `cj_needs_scope`、`cj_needs_record`、`cj_needs_revision`，只装已接受的最小 NEEDS 版本化切片；同 needs_id 在 A/B 两个真实scope中各自保存。原 `/v1/needs-actions`、`/v1/needs`、`/v1/needs-action-receipts` 已有正式生成类型。此选择验证环境，不替代 NEEDS/旅行产品验收。
4. 已登记 `cj.schema_migrations` 与**另审**的新 C2 managed-target迁移 manifest：核新 ref 与空的应用namespace，接受明确的平台对象清单；不修改PR62 checker为通用云 apply，不自动应用其四份候选清单。
5. 迁移身份和 API runtime 身份分开。候选 runtime 必须 NOSUPERUSER/NOBYPASSRLS、无DDL、无私有业务schema的 anon/authenticated Data API 直通；精确usage/DML与RLS由已接受的scope权威决定，不能假定直连PG有 auth.uid()。迁移/权限本轮均不执行。

先做 NEEDS 切片能避开无关模型、RUN/USAGE派发和费用出口；不把其他域未注册迁移变成已可apply。私有记录只用经批准的合成规划声明；真实游客内容、生产留存/清理/备份权限不因此获准。

## 4. 当前可复用源与仍需代码（技术决定交 Main/原 owner）

| 部分 | 已有实际代码/证据 | 还缺的最小实施 |
|---|---|---|
| API/生成客户端 | BASE request_id/错误/no-store、官方CJAPI、原NEEDS wire和私有PG/HTTP/Swift证据 | 显式C2 target manifest/校验与factory；现 `create_app` 只许local，不能仅替换URL |
| JWT/JWKS | AUTH8b支持显式 `SUPABASE_ACCESS_RC1`、ES256/RS256；JWKS provider与有界HTTPS transport已存在 | root当前factory强制STRICT；C2要消费原owner认可的Supabase profile与固定JWKS，不编辑真实token添加nbf |
| 当前事实/撤销 | 原CJAccessProvider只有principal→member/email_verified/invited，source明确无默认provider | 新目标真实facts/稳定scope provisioning；session_id现只检查形状并从TrustedPrincipal丢弃，不能宣称当前会话撤销。请CJ007原owner提供可信verified-session绑定/验证公开seam，root不自解JWT或造第二authority |
| DB部署 | 版本化foundation、PR62准入与域candidate SQL；已有大量单域新私有PG证明 | managed namespace/migrator/runtime/RLS的最小可审迁移与rollback协议，原空库私有checker仍BLOCKED；锁定Linux实际DB driver，不能把保留测试driver目录装进产品镜像 |
| 原生Auth | SupabaseSDKAdapter、SessionBridge、账号代次/安全存储组件已存在；SDK fetch默认拒绝网络 | 真实安全材料/transport/存储host；emailVerify/emailReset当前hostCapabilityRequired；callback/PKCE/purpose/state/nonce仍须原AUTH owner接通 |
| 手机业务路径 | CJAPI生成类型可复用，原ProbeConnection只接受HTTP literal loopback | C2签名配置、精确HTTPS origin与拒绝redirect的正式transport、现NEEDS最小表单/回执持久化host；不能把ProbeConnection放宽当整链 |

这些是源码差额，不是资源审批问题。Main应沿原CJ007、CJ005、CJ006/数据owner的现有写权接续；不要求JT选择JWT算法、SQL策略、pool模式或代码接口。当前没有写这些实现，也不计作新增产品编码。资源批准前仍可准备/审查上述非秘密配置与本地实现；不能据此开启真实出口。

### 手机回调具体安排

候选 `space.go2china.c2.dev://auth/callback` 只注册在新C2 bundle及新Auth redirect allowlist，采用原SDK的PKCE/当前attempt绑定；不加通配scheme/任意URL。Google/Apple native材料由实际平台流程产生，不能以URL或AuthAttempt UUID假造nonce/token。

**现adapter把emailRedirect也交给https-only validator，且确认/重置能力未提供，所以上述custom scheme目前不能直接填进去。** 原AUTH owner需要把Auth HTTPS endpoint与精确native callback验证分开并固定公开host契约，同时实现一次性code/PKCE、purpose和账号代次fence；不降低API TLS验证。这个实现缺口先由Main派原owner，不让JT作技术选择。

确认邮件/找回邮件先经过新Supabase Auth，随后回当前App；API origin独立且一直HTTPS。先跑邮箱核心链，再并行核Google iOS+server client IDs、Apple原生App ID/能力与签名；这些产品要求保留，未实测仍UNRUN。Google/Apple的实际验收归属由Main对照原#5/#8要求确认，不能用“先邮箱”删掉既有关闭门槛。

## 5. 两账号最小实测顺序（批准后，当前均UNRUN）

1. 读回实际新 ref/region/issuer/JWKS、cloud revision/digest/origin、迁移版本/namespace/runtime身份，与批准清单匹配；缺失/错配/旧VP ref即拒绝，无fallback。按审过的新C2迁移初始化应用namespace并核权限，不向managed库套旧空库apply。
2. 指定iPhone经真实App访问该HTTPS origin；先Wi-Fi后蜂窝，核TLS/redirect拒绝/BASE trace。probe仅传输初检。若中国目标网络任一必需段失败，保留FAIL；不改DNS/VPN或私自换平台/region。
3. A/B都通过真实邮箱注册→收到确认→当前App/PKCE确认→登录；注册/验证/找回不受邀请资格阻断。A初始受邀、B初始未受邀；B受限业务403。确认与找回要真实收件/回跳，不用SMTP ACK冒投递。
4. A用原NEEDS API保存一份合成记录，保留原action bytes/ID与正式回执。A读回；B即便给相同needs_id/action_id也不读到A数据。坏签名/错环境/过期/依赖UNKNOWN分别拒绝，不取旧VP token做负例。
5. 在**仅A/B测试名单维护授权**下临时给予B业务资格；两人用相同needs_id分别存不同声明，读取各自内容/版本/原回执。篡改owner/source/资格字段拒绝。受控重启API/App后重新登录再读，证明新真实PG持久化，而非内存fixture。
6. 撤邀B验证新受限请求拒绝，但账号流程继续可用；退出会话后旧session按原owner公开seam拒绝。新请求/在途private返回/提交未知分别记录；不宣称跨Auth/DB全局原子撤销。真实网络丢ACK只查原action，不能换ID重发。
7. 邮件找回、过期/重复/错purpose/账号切换后的晚到callback拒绝；再做批准的Google/Apple与私密邮箱绑定反例。最后按原#5逐项汇总PASS/FAIL/UNKNOWN/UNRUN交独立Testing，不自动关闭Issue。

## 6. 给 JT 的具体授权包（还未批准）

推荐新增测试支出包 **USD50/月**，不是已报价或账单硬cap：Supabase公开页附加项目从USD10/月；实际Go2China组织get_cost尚未读取，工具要求先由人明确organization。Resend公开Free为0美元、3000封/月、100封/日；Cloud Run、镜像/secret/log/出网及税费仍需实际报价。不得借“免费额度”默认建资源。[Supabase价格](https://supabase.com/pricing)、[Resend价格](https://resend.com/pricing)、[SMTP条件](https://resend.com/docs/send-with-smtp)。

Main可把这一个包交JT，而不让其选平台技术：

- 明确同意Go2China组织 `ppfsagymaozpbkbarhes` 新建独立 `cj-c2-dev`/Singapore，先读该组织实际报价，只有费用被确认后创建；不动旧VP项目/账号/数据。
- 同意在JT拥有并选择的GCP结算账号中新建CJ专用测试project，Cloud Run Singapore、指定新服务的公网invocation、最小运行/secret/日志权限；不改现有服务。origin由真实部署读回。
- 同意实际增量费用在审批预算内；先读回价格与账单对象，不自动升级或调用模型。达到异常报价/用量时停止新测试与公开服务流量并交Main；固定compute/storage可能继续收费，不能擅删项目或声称max1/告警保证封顶。[Google预算说明](https://docs.cloud.google.com/billing/docs/how-to/budgets)。
- 允许Resend Free账号/指定自有auth子域的验证，只加实际所需SPF/DKIM记录，不改现有MX/NS；指定A/B两测试邮箱及名单授予/撤销范围，通过官方安全入口提供，不在Git/聊天提交密码、key或完整链接。
- 指定一台iPhone、所属Apple Team/C2 App ID、安装签名与Wi-Fi/蜂窝测试范围；Google/Apple控制台/2FA/域所有权步骤由官方窗口安全交接。新费用/会员条款/额外权限仍单独核对象，不能复制旧key来绕过。

JT给的是资源/财务/设备与账号权限，不是代码算法选择。若Main已有这里未见的新目标批准，先提供**非秘密ref/URL/批准记录**核对，再只在其范围推进；UNKNOWN不是“无”，也不是许可。

## 7. 本轮结果与剩余门槛

PASS：当前两个连接metadata、Go2China Pro、PR62/Issue5官方只读、源码差额、具体单方案/对象/owner/验收顺序/授权包、JSON与diff检查。没有新真实资源动作或业务代码。PR62 apply与C2整体继续BLOCKED；SMTP、真实Auth/回调/sessionfacts、新迁移权限、设备HTTPS/两账号持久隔离及独立验收均UNRUN。

已核官方changelog；2026-10-12的TLS1.2 CBC弃用最早2026-11-10开始，目标设备TLS需实际验证，不能由SDK编译推断。[官方changelog](https://supabase.com/changelog)。新方案无本地CA，也未改设备信任或网络策略。所有原FAIL/保留私有PG证据与candidate gates保持。
