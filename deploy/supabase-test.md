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
`postgres.rls_auto_enable() RETURNS event_trigger` 平台函数，不创建、禁用或修改任何平台 SECURITY DEFINER/事件触发器。
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
  不能据此宣称完整 Auth→CJ API→云 RLS 或整套 pooler 已通过。
- `pg_stat_ssl=false` 是已观测的 pooler→PG 边界；客户端→pooler verify-full 通过不能代称内部也有 TLS。
- 实际账单无法读取时为 UNKNOWN；任何新资源、平台/地域选择、域名、备份方案或生产仍等 #495。

本机回归 `scripts/test_supabase_m4.py` 与 `scripts/supabase_m4_pg_check.py` 已登记到原 test/PG Harness，
不会读取真实钥匙串、连接云或产生账户。真实操作独立执行，报告不进入源码仓库。
