# #30：指定 Supabase 测试项目

仅 `G2C / sajkhvjpllldfyfryalx / ap-southeast-1`，至 2026-11-30；合成数据。
M1 条目2及 JT 本轮付费测试授权、两个合成 Auth 账号的服务端 key 授权均记在 #495。
不部署托管 API/worker、不操作域名、不升级套餐或买备份、不写真实用户数据。

脚本 `scripts/supabase_m4.py` 的固定目标不能从命令行改写。DB URI来自钥匙串 `g2c-supabase-db`，
服务端 Secret key 来自 `g2c-supabase-auth-test`；两个账号按固定的本机授权账本分配，换工作区不会增加名额。
密码、access/refresh token 和 key 只在进程内；恢复只按原合成邮箱查询原动作，不能换主体盲重建。
客户端验证使用公开 publishable key，经显式配置文件注入，不能用服务端 key 代替用户权限测试。

DB 只接受指定项目 pooler 的 URI及普通数据库名；拒绝 conninfo/hostaddr/service 等别名。
使用 `verify-full` 和指纹固定的 Supabase Root 2021 CA（从可信官方来源下载，脚本校验后复制到独立临时文件）。
不关闭证书校验、不修改系统信任。Auth HTTPS 使用默认公开 CA、固定项目 endpoint、零重试/不跟随重定向。

```text
supabase_m4.py inspect --ca-file CA
supabase_m4.py pool --ca-file CA
supabase_m4.py auth --ca-file CA --public-key-file PUBLIC_KEY
supabase_m4.py migrate --ca-file CA             # 只读计划
supabase_m4.py migrate --ca-file CA --apply     # 仅已获准目标
```

迁移只消费已 fetch 的 main 中同字节 manifest 与 SQL，不改已应用文件。
首次 target 准入要求 public 无关系对象、无自有函数；允许原样保留 Supabase 已有的
`public.rls_auto_enable() RETURNS event_trigger`（owner postgres）平台函数，不创建、禁用或修改任何平台 SECURITY DEFINER/事件触发器。
在导入任何 CJ public 对象前，撤去 PUBLIC/anon/authenticated/service_role 的 public schema USAGE，
避免托管项目默认表/函数授权直接暴露内部 CJ 存储。自家运行角色按原迁移获得显式最小权限。
Auth 自有 schema、Auth/计费设置和平台函数保持；此操作本身是明确的数据库 schema ACL 收紧，不能描述成“没有权限变更”。

该准入只适用于此专用私有 CJ API 测试空间；发现其他 public 对象立即拒绝，不能覆盖旧应用。
未来若决定让客户端使用 Data API，须按接受的架构另给明确对象权限，不能自动恢复宽泛默认授权。
迁移中断只核原台账与本机意图后续接，保持 namespace 关闭，不回退到更宽身份或默认权限。

测试级别分开报告：

- Auth：仅管理员确认的两个合成邮箱账号，公开客户端密码登录、project JWK 验签、篡改/越权拒绝、退出/旧刷新令牌、原账号删除。
  真实邮件投递、iOS SDK 和 CJ 云端 admission/注销组合均 UNRUN。
- Pooler：两模式的事务 LOCAL 过期、相同物理会话正常断连后的 SESSION 状态观测；单次观测不证明全部 reset 行为。
  测试使用初始化身份，不是 runtime 密码登录；异常断连及全部12表的真实云负例门禁尚未完成，产品激活 HOLD。
- RLS：真实非 BYPASS 运行角色的一张 MESSAGE scope 表正例/跨 scope SELECT、UPDATE、INSERT 负例；外层事务完全回滚，无持久测试行。
  只有既有已批准执行身份可合法进入该角色时才执行；权限拒绝记 HOLD，不自动 GRANT、改角色密码或换身份绕过。
  不能据此宣称完整 Auth→CJ API→云 RLS 或整套 pooler 已通过。
- `pg_stat_ssl=false` 是已观测的 pooler→PG 边界；客户端→pooler verify-full 通过不能代称内部也有 TLS。
- 实际账单无法读取时为 UNKNOWN；任何新资源、平台/地域选择、域名、备份方案或生产仍等 #495。

本机回归 `scripts/test_supabase_m4.py` 与 `scripts/supabase_m4_pg_check.py` 已登记到原 test/PG Harness，
不会读取真实钥匙串、连接云或产生账户。真实操作独立执行，报告不进入源码仓库。

2026-11-04 安全 advisor 保留：33 项函数 search_path WARN，以及既有平台事件函数的 anon/authenticated EXECUTE 两项 WARN。
namespace USAGE 已实际拒绝；没有据此把 advisor 标成清零，也不改已应用 SQL 或平台函数凑绿。
生产前的受控运行身份、完整12表门禁、搜索路径/平台 advisory 处理需另按 #30/#495 收口。

## 后续 #30 修复 profile（代码与实际云结果分开）

新 `SupabaseTestDatabase` 只接受指定 G2C 项目、5432 session 模式与独立
`cj_m1_runtime` 连接。旧本机 Unix-socket 校验、scope/owner 与交易 LOCAL binder 保留。
6543 transaction 模式不允许作为应用连接：对某一物理后端做 RESET，不能清空将来借用的其他后端。
应用每次 checkout 验 `current_user=session_user=cj_m1_runtime` 与 `pg_stat_ssl.ssl=true`，
然后在其独占 session 后端执行 `DISCARD ALL`，复核重置后实际身份、TLS及既有权限 GUC 为空，
才进入原 LOCAL scope 绑定；构造后新出现的PG/LIBPQ/SSLKEYLOGFILE环境污染同样拒绝。
未加密、错角色、未重置或无法证明，均拒绝业务查询；不以客户端 TLS 代称内部加密。

云端 SSL 强制设置应在指定项目 Database Settings 的 SSL configuration 中启用，随后实测两段。
该设置可能短暂重启数据库，按官方说明执行；不改计费、网络安全组或购买 IPv4/其他资源。
当前授权的目的只含测试修复，没有生产放行。

JT 在本轮已批准仅为既有运行角色设置随机密码，记录在 #495。
`scripts/supabase_runtime_credential.py apply --ca-file CA`：固定项目与角色、要求空闲且最小权限，
确认数据库侧 TLS 后，将原凭据存 Keychain `g2c-supabase-runtime-db`；使用 libpq
`encrypt_password(..., scram-sha-256)` 构造密码变更，不在 SQL 里传明文密码、不 GRANT 或新建角色。
变更意图先持久；再次执行只验证原凭据，不重置密码，不把未知提交当没执行。
创建/变更前验证成员资格、对象所有权与完整限制，读回仍要求独立登录和数据库侧TLS；
Mac仅对这个新批准条目使用系统Keychain API，密码不进入进程argv，不解锁/修改ACL或自动批准系统弹窗。
如系统要求用户交互，拒绝并保留原意图；旧模型Key的系统交接不由此绕过。
服务器只消费后续600环境文件，脚本与报告不输出连接串、密码、SCRAM verifier。

`scripts/supabase_pool_gate.py run --ca-file CA` 先在私有PG用原签名 API/Fake/确认生成两个
随机合成 scope 的完整12表正例，再复制到固定云项目。真实运行角色须逐表验证双方非空正例，
绑定A/B时逐表直接检验对方SELECT/UPDATE/INSERT被拒绝，并核原表写权限存在，
不能用WHERE own掩盖跨主体可见性；同物理后端 commit/rollback 后的无scope负例也继续核对。
还覆盖正常/异常断开，再借用时应用强制重置与完整12表负例。异常只切断本脚本自己的客户端，
不对任意服务器PID执行 terminate。供应商是否复用了同一后端按实测列出，不能把换PID称reset证明。
本探针的下一次借用已经由应用清理，因此供应商reset结果始终记UNKNOWN；同PID空值不能倒推供应商已清理。
负向写入均置于强制回滚交易；只清理由本批次签名源生成且完整hash未变的自有合成数据。
原 run 已存在时只读查询云端原两组scope，区分EMPTY_CONFIRMED、OWNED_SEED_MATCH、
HOLD_CHANGED_OR_PARTIAL，不凭本机JSON证明COMMIT；不另开新scope或重发写入。
显式 `cleanup` 仅在原完整hash仍吻合时清理，内容改变则保持不可用；所有管理员清理连接也先验身份/TLS。
SQL timestamptz比较按UTC瞬间规范化，避免Mac的+08显示与云UTC显示造成假差异；普通date/naive timestamp不改语义。
原旧hash只能用显式 `upgrade-hash` 升级：完整原行数及按已知源时区Asia/Shanghai的旧整体hash必须精确吻合，
备份原state/保留旧hash后才更新本机比较格式，云数据写入0；不能仅凭数量或时区猜测采纳变化。
`resume` 只在云端原完整seed已读回吻合后复验原scope的矩阵/断线并按原hash清理，不生成新scope或重发seed。

本地 `supabase_pool_reset` 组只验证真实 Unix PG 的12表/重置机制，明确没有云或TLS证明；
实际云测试、运行角色、双段TLS与费用必须另在 #30/PR 记录 PASS/FAIL/UNRUN/UNKNOWN。
计数为被仪表化的 execute 调用，内部交易/重置等总SQL数无法完整计数时保持 UNKNOWN。
