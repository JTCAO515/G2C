# 全新 Auth / 数据、角色、配置与报价缺口

以下是 C2 准备提案，不是新增 AUTH@1.0 契约或已接受 SQL/权限。具体实现由 Main 给 CJ-007/领域 owner 明确 lease 后固定版本；本轮没有创建/更新项目、名单、会话、DNS或 secret。

## 最小新资源与账号流程

共用依赖是一个**全新** Supabase 项目，Auth + 标准 Postgres + JT 管理的私有邀请名单；不需要为 C2 先开 Realtime、对象 Storage、Edge Functions 或模型服务。新项目不能从 VP backup/branch/账号导入。数据库引擎也须在创建前明确，不能把新的 OrioleDB 选项无声替换标准 Postgres。`cj-dev` 仅候选标签，实际 ref / region / organization 由批准后平台读回。

1. 邮箱密码自助注册：启用 email/password，保留邮箱确认；Swift 默认 PKCE 这一官方行为要与 CJ-004 已锁 SDK 核对后实现。用户验证完成前不得取得 CJ 数据权限。密码直接通过官方客户端→新 Supabase Auth，不进入 CJ API、日志或自建密码表。[密码登录说明](https://supabase.com/docs/guides/auth/passwords)。
2. JT 名单是准入，不是 Supabase 团队邀请。建议在同一新 Postgres 私有域保存允许邮箱/绑定后的 Auth subject、状态、撤销代次及必要审计；规范化/绑定规则由 AUTH owner 冻结，不猜表名或把整域邮箱放行。真实邮箱名单不进 Git/聊天。自助注册可通过 Before User Created **Postgres hook**检验名单并 fail closed；此 hook 当前列为 Free/Pro 可用，无需为它先建单独 HTTP 服务。[hook 能力](https://supabase.com/docs/guides/auth/auth-hooks)、[创建前检查](https://supabase.com/docs/guides/auth/auth-hooks/before-user-created-hook)。这是项目应用方案推导，不是 Supabase 内置“JT名单”功能。
3. 名单检查必须在 CJ 每次访问/提交时重核，注册 hook 只阻新建账号，不能撤销已有账号。用户可编辑 metadata、客户端 email/user_id、旧 JWT 中的资格快照不作权限权威。名单读取不可用则拒绝，不退化成“所有已认证用户”。本轮不写 hook SQL 或权限函数。
4. 独立事务邮件：选定 SMTP 供应商后，批准该发信子域/From 及 SPF/DKIM/DMARC 等精确 DNS 记录、发送范围与额度。SMTP host/port/user/password仅由安全入口交到新 Supabase SMTP 配置，不放 iOS、CJ runtime 或仓库。不开默认自动确认绕过邮件，不加游客进团队，不改已确认的邮箱密码登录为其他产品模式。[SMTP 规则及发信域建议](https://supabase.com/docs/guides/auth/auth-smtp)。
5. 确认/找回只发用户发起的事务消息，测试前批准真实收件人；计费/发信试验单独授权。交付必须演示确认、找回后设置新密码、旧链接/过期/重放/错设备无法完成当前 PKCE 等明确失败；不因一次 send 回执把邮件投递/回跳报 PASS。

## 回调与三个不同地址

| 地址 | 消费方 / 作用 | 不可混用 |
|---|---|---|
| 新 Supabase project URL | 官方 iOS Auth SDK：注册、登录、确认/找回的 Auth 服务；对应新 publishable key | 不是 CJ Python API；不得填进 CJ_API_BASE_URL |
| 新 CJ API HTTPS origin | iOS 生成客户端→Python，A 的明确 LAN TLS 或 B 的实际平台 URL | 不得填写 Supabase Auth URL，也不能从未知 URL/重定向自动发现 |
| 精确原生 Auth callback URI | 官方 Auth 邮件→App 已注册 scheme/host/path，SDK处理 PKCE/恢复状态 | 不是 API 路由，也不是随意公网落地页 |

开发期可按官方文档使用注册的自定义 scheme，把同一精确 URI 配到新项目 Site URL / redirect allowlist，并在每次 signUp/reset 明确传 redirectTo；不留下默认 localhost:3000，不加广泛通配符。URI 的实际值由真实 bundle/原生注册能力确定，当前留空。未来若采用 Universal Links，需另批准专用 HTTPS 域、AASA 与 associated domains；不默默占用旧 VP 域/工程能力。[Redirect URL 文档](https://supabase.com/docs/guides/auth/redirect-urls)、[原生深链](https://supabase.com/docs/guides/auth/native-mobile-deep-linking)。

Auth 邮件中的合法回跳与 CJ API redirect 策略分开：原生 SDK/URL handler 只接受批准的回调及当前待完成的认证事务，账号/环境切换后的晚到回调不能落入新账号。对 callback query/code/token 不输出日志；Auth UI明确显示完成/过期/无匹配事务/取消。CJ 生成 HTTP 客户端继续拒绝重定向，不用它追随 Auth 邮件流程。

## 身份与数据库边界

| 主体 | 最小职责与拟权限 | 禁止混用 |
|---|---|---|
| JT / 指定名单管理员 | 安全提交/撤销邀请；批准费用与资源 | 不把 App 游客变为云/Supabase组织管理员 |
| Supabase组织/项目操作人 | 仅批准的新项目设置、迁移操作；临时权限按实核 | 本轮不扩大权限，不拿默认Owner身份当runtime |
| iOS游客 | 新项目 publishable key + 自己的 Auth 会话 | 无 DB密码、SMTP密码、服务端 secret/service-role、云身份私钥 |
| CJ API运行身份 | 验新Auth签名、当前资格/撤销、业务归属；只读必要身份状态及领域所需最小DML | 不持migration role，不任意读所有 auth.users/auth.sessions，不用 service-role 绕 RLS |
| 新 DB迁移身份 | 审过的版本化 schema/角色/策略变更；批准操作后收回 | 不留在运行镜像/App，不向模型开放 |
| 新 DB运行角色 | 仅新CJ schema/必要受控接口；非owner、非superuser、无BYPASSRLS/DDL | 不假定Postgres连接自动带 auth.uid() |
| 托管部署者与runtime服务身份 | B 分开；runtime仅可读指定secret版本 | 不给游客 Google IAM，不使用项目编辑者作为服务身份 |

Python应固定新项目 issuer、允许算法、JWKS origin及预期 audience，校验签名/exp/sub/会话和邀请状态；不得按未经验证 token 的 `iss`/`jku` 动态请求任意 key URL。新项目若选非对称签名，使用该项目官方 JWKS；HS256项目不能假定JWKS含key，应按官方 Auth服务验证方式或先批准签名模式，不能搬旧共享JWT秘密。[JWT 文档](https://supabase.com/docs/guides/auth/jwts)。

退出/删除用户不保证已发行 access token立即失效。对要求即时撤销的 CJ 访问，校验当前名单/账号代次，且通过最小受控 lookup 核 `session_id` 仍有效；具体 lookup 权限由 AUTH/DB owner设计，不能直接给runtime全表高权。撤销服务暂不可达则fail closed。设备移除/退出清掉本账号会话和可用缓存，晚到请求再验旧代次。注销/物理删除及备份防复活另由 CLEANUP 原验收处理，本方案不声称做完。[会话与 session_id](https://supabase.com/docs/guides/auth/sessions)。

正式业务写入仍只经 CJ API。领域表不直接暴露移动端 Data API；任何暴露 schema 必须显式审 RLS/列权/最小 grants，`authenticated`不是owner隔离。若受控DB调用依赖JWT principal，须由验签后的服务端在事务内安全绑定/重核，禁止接收caller owner；连接池归还不得残留上个用户身份。正式schema/策略及迁移前向/兼容回退须独立审验，不在这里新造通用授权层。[RLS 官方说明](https://supabase.com/docs/guides/database/postgres/row-level-security)、[Postgres角色](https://supabase.com/docs/guides/database/postgres/roles)。

连接方式：从新项目 Connect 面板读实际 host/username/port，不从 region拼 pooler域名。IPv4-only host 可选择 shared pooler session mode；serverless transaction模式需按已选Python驱动验证连接池/事务/预编译限制及总连接上界。TLS严格验证服务器身份和CA；不为连通而买IPv4 add-on或改网络，需费用时另报。[数据库连接说明](https://supabase.com/docs/guides/database/connecting-to-postgres)。

## 配置登记提案（不是新增已实现环境变量）

| 名称 | 所在 / 必需 / 缺失行为 |
|---|---|
| `CJ_ENV` | App/API；当前只实现local。C2候选dev须新实现并绑定精确资源清单，缺失/不匹配拒绝启动 |
| `CJ_API_BASE_URL` | App公开配置；C2仅批准的精确HTTPS origin；缺失拒绝，不回落生产/旧VP |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | App公开元数据；只对应批准新ref，不是用户权限；缺失/环境错配拒绝 |
| `CJ_AUTH_ISSUER`, `CJ_AUTH_AUDIENCE` | 服务端公开校验预期；从新Auth固定，不能从请求反推信任 |
| `CJ_AUTH_JWKS_URL` | 服务端拟名；固定到新issuer对应公钥入口，限制算法/kid缓存与轮换；缺失拒绝 |
| `CJ_AUTH_REDIRECT_URL` | App/新Auth配置；拟名，精确已注册URI；缺失不发确认/找回，不能回默认网页 |
| `CJ_DATABASE_URL` | API秘密；新DB最小runtime身份，经批准安全存储注入；不入App/日志/Git |
| migration connection | 独立短期安全操作输入；不共用runtime变量，不入样例；缺失不运行迁移 |
| SMTP settings | 新Supabase设置；仅安全入口；无已选供应商，值均未分配 |
| A leaf key/cert路径或 B PORT/secret版本 | A私钥仓库外；B按平台注入。不得把A的TLS/网卡参数套进B |

不需要配置模型、旧账号、service-role、工作流或ReMe凭据。env名称不等于受支持配置；未实现项必须先进入后续实现lease。所有诊断只留request_id、非秘密版本/来源状态，不保存密码、会话token、邮件完整链接或DB URL；日志/名单/邮件provider处理的留存与删除时限仍需JT和领域owner定，未定不采集真实游客业务内容。

## 地域与费用：可比较口径，未获实际报价

| 项目 | 官方公开依据 | 本项目尚缺 / 审批口径 |
|---|---|---|
| Supabase组织与计划 | Pro公开基价 $25/月；付费计划含组织每月$10 compute credit，可覆盖一个Micro，不能当每新增项目再给一次 | Go2China Pro组织未批准；已有credit消耗/账期/税币种未知，不承诺增量$0或总额$25。[计划价格](https://supabase.com/pricing) |
| 新数据库compute | Micro公开约$10/月，小时价$0.01344；时长、disk、egress/MAU等额外用量另算 | 新项目若在现有付费组织，常见新增compute需计价，但实际折扣/额度/规格/最终增量须平台估算读回。先报价再创建。[compute计费](https://supabase.com/docs/guides/platform/manage-your-usage/compute) |
| Supabase地域 | Singapore具体AWS region `ap-southeast-1`；general APAC与精确region选择口径不同 | 仅建议，不批准；记录实际选择及处理地域/备份/SMTP地域，不由域名推断中国可达。[地域文档](https://supabase.com/docs/guides/platform/regions) |
| A本地TLS | 已有M5Pro，无新增托管compute这一项 | 不等于总费用0：新Auth/DB/SMTP、设备/证书工具/域及操作仍有成本/授权；用现有网络不承诺额外流量免费 |
| B Cloud Run | 计算按资源/计费模式/region用量收费，免费额度按billing account汇总；镜像registry、secret/log和跨云流量等需另列 | 没有账户、用量、内存/CPU/并发/时长/egress数据，准确增量 UNKNOWN；拿官方calculator与账单账户实际额度做报价，不用free tier做承诺。[Cloud Run价格](https://cloud.google.com/run/pricing) |
| B地域 | Cloud Run Singapore `asia-southeast1`列Tier2 | 它与Supabase AWS `ap-southeast-1`不是同一云网络，跨云连接/出流量仍需实测/报价；不自动选中。[Cloud Run地域](https://docs.cloud.google.com/run/docs/locations) |
| 邮件与域 | SMTP需独立服务，计费随供应商、发信数、域/DNS条件而变 | 供应商/域所有者/From/配额/试发收件人/预算均待批准，不虚构每封费用或把Supabase计划费当邮件额度 |
| 费用停止条件 | Google文档区分 alerts-only 与 spend-cap预算，能力/服务覆盖需实际核 | 不能只设告警或max实例就声称硬封顶；批准总额、执行监控者、超限停用范围及恢复操作。未核账户覆盖则无硬cap保证。[预算文档](https://docs.cloud.google.com/billing/docs/how-to/budgets) |

报价记录需包含UTC/北京时间、来源页/平台估算回执、币种/税、计费周期、规格/region、现有额度是否消耗、按预计运行小时/邮箱验证找回量/请求量/流量的假设、一次性项和每月项、上限与停止措施。缺值保留UNKNOWN；不得为取报价先创建收费资源或添加付款方式。
