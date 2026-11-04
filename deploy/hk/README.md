# 香港合成测试后端

只用于 M4 条目5已在 main 生效后的指定 ECS、域名和 OSS；合并前不连接主机或桶。
先核实实例仍在免费试用期、实际到期时间和收费提示。试用结束或出现收费提示即停止并向 JT 报告；
不修改安全组、规格、计费，不购买资源。Supabase 仍是指定新加坡测试项目，只有5432 session模式。

## 配置与构建

`*.env.example` 只有占位符。正式配置在服务器 `/srv/g2c-beta/`，目录0700，所有实际环境文件0600；
从指定钥匙串私下交接，不复制到 Git/镜像/日志，不把值放在命令参数或聊天。
Compose仅用 `env_file.format: raw` 传非秘密common配置。秘密文件以只读bind挂载，由各入口按角色校验0600/UID/字段后读入进程；Docker Config.Env不持久保存密钥。
API仅收到运行角色、确认/history密钥和验签公钥；worker另收模型/高德和对应签名私钥；
operator另收既有数据库初始化凭据和恢复签名私钥；OSS凭据只进backup容器。应用和operator均UID10001；相应实际环境文件由10001拥有，宿主父目录保持0700。
worker的旧token供应器通过Linux memfd读取私钥，磁盘上只有指向进程FD的链接。
公钥、邀请名单、RUN配置只写入容器tmpfs。TLS证书由Caddy管理在独立私有目录。

从干净的已提交源码、显式PG17和已核实的服务器架构构建：

```sh
uv sync --locked --group dev
CJ_ENV=local PYTHONPATH=.:scripts uv run --locked python -B -m deploy.hk.build --platform linux/amd64
```

`CJ_PG_BINDIR`/PATH须指向PG17。构建复用 `deploy.build.source_context` 的已提交blob白名单，
不打包工作树日志、私有PG或配置。新的私有PG17只应用原迁移，生成应用专属pre-data/post-data schema，
包括原ACL/RLS/约束/触发器；不从Supabase复制Auth、vault或供应商函数。
schema资产绑定原迁移hash并放进镜像；镜像标签和OCI revision均为源commit。
应用镜像只含PG17 client；另建同commit的operator镜像，加入仅供Unix隔离暂存/恢复的PG17 server，不暴露端口。
跨架构分别构建，先本机验镜像再传至既有主机，不发布镜像到新的云仓库。

## 原预算与启动

迁移预算前停止并确认所有Mac旧producer已结束；先核原请求结果，未决原动作保持UNKNOWN。
`scripts/m4_budget_transfer.py seal`在原共享SQLite事务锁内封存，再导出同一账本。
只有指定主机激活和精确文件hash才可adopt。旧实例每次写入都会查producer标识；HK每次SQLite变更先在不随库恢复的control写WRITE_INTENT，再提交、推进精确全行hash锚点；
账本回退或跨存储未知阶段明确HOLD，不因行数仍大于初始收养值而重开原attempt。
不能重设原attempt、释放UNKNOWN或另起新预算。运行中的旧二进制不支持此迁移，必须先停止。

建立既有主机内的control(0755)、heartbeat/budget(10001)、backups(0700)与私有TLS目录。
`compose.env`锁定已审镜像，启动 `deploy/hk/compose.yaml`：migrate完成后才能启动API/worker。
迁移只执行已提交的追加链；首次预算初始化仅限全空业务库，有原release的重启不会重建已注销namespace。
API和worker都使用独立cj_m1_runtime登录，每次连接校验前后身份、TLS、RESET后scope。
原ACCOUNT-ADMISSION@2在API和worker前台启用，不能重建退休账号。

Caddy仅发布80/443、自动HTTPS并保留流式响应；应用端口不对主机外发布。
`/health/live`仅进程存活；`/health/ready`核有效期、签名release、实际库identity/schema和15秒worker心跳。
未就绪时所有业务读写503。worker按原RUN ID记录failed/unknown告警，并保留注册计量audit；不输出内容、key或URI。
健康不主动调用付费模型，也不声称供应商质量已通过；协议兼容/拒绝沿用原API。

## 每日备份与隔离恢复

安装本目录service/timer到systemd；每天19:00 UTC（北京时间03:00）停止并排空本测试环境writer，
调用operator在同一条已验身份、reset及TLS的源连接内锁定并COPY同快照业务行到全新Unix暂存库；
核逐表UTC完整行集hash及identity sequence的last_value/is_called相同后，仅对暂存库执行native pg_dump，云凭据不交给pg_dump子连接。确认OSS原对象HEAD后重开服务。失败保持停止并告警。
包只含CJ业务数据，迁移ledger和可轮转identity由镜像规范schema在恢复时创建。
`g2c-beta-data-checkpoint.1`是独立的云应用数据包；旧本机归档格式及恢复入口不变。

Ed25519清单覆盖dump、精确schema、逐表行数/hash、同源lineage和全部永久fence。独立control不随数据库恢复，
最新完整检查点绑定旧备份hash；缺少最新状态/可信control/密钥则保持不可读写。
OSS固定香港内部HTTPS端点、私有/AES256、backups/前缀，SDK自动重试关闭；
每个文件先持久INTENT，回执丢失后只HEAD核原对象。缺失/不一致保持UNKNOWN，不重发PUT。
每日阶段持久化，未完成的原检查点先查原制品和数据库identity，不再导出第二份冒充恢复成功。
桶30天生命周期需按已授权能力核实，实际到期删除需经过30天，不以配置截图冒充实际删除。

恢复目标是**同一主机内全新、仅Unix socket的独立PG17集群**，由本次operator进程亲自initdb/启动并绑定system_identifier/data_directory；核服务端listen_addresses为空和仅演练数据库，不接受任意目标URI/旧共享集群，不创建新云项目。
原集群中新空库仍有全局应用角色，会被明确拒绝；不重用角色、不给云角色扩权。
恢复按镜像规范pre-data → 最新检查点DATA（fence先行）→ 原post-data执行单事务，
不禁用trigger/replication-role，不删改原约束或RLS。历史数据不会被误当成新业务动作执行。
核对签名/hash、原schema、永久fence和物理删除后才签发该目标release；安全检查点在首次写入前消费，
不能重复恢复抹去后来删除。恢复前再次锁定当前源完整行集；如备份后发生注销/单条删除或其他写入，旧安全包明确拒绝且不消费、不写目标。
HK运行时每个业务事务在安装LOCAL scope前获取共享release事务锁并重新验证签名release；
独立cleanup事务同样先取共享锁，再由已获准runtime独立登录只读核库identity（cleanup未获schema元数据权限，不新增GRANT或用管理员执行删除）；恢复持独占锁，先关闭并轮换源identity，再签发隔离目标release，保持单一可写侧。
recovery命令在同一进程内创建目标、恢复并验证，结束时先核目标完整行集/sequence均未变化，再关闭并轮换隔离目标，核源未变化后恢复源release。若活跃隔离侧接受了写入、注销或删除，拒绝切回旧源，保持源关闭；中间失败保留原记录待核，不自动重做恢复。
隔离目标不自动替换现有云库或开放公网。

## 验证

```sh
uv run --locked python -B scripts/test.py
CJ_PG_BINDIR=/path/to/pg17/bin CJ_PG17_BINDIR=/path/to/pg17/bin uv run --locked python -B scripts/pg_suites.py
```

新增hk_recovery组复用原注销、单条记忆删除生产者，实际备份/恢复到第二私有PG，
检查物理缺失、其他owner、原费用/UNKNOWN、旧应用/旧包/消费重用拒绝。
镜像内 `python -B -m deploy.hk.runtime_check` 用全新临时合成签名键核验memfd，无网络或真实key读取。
本机、真实云数据库、真实模型/高德、实际OSS下载恢复和App目标网络证据分别在PR/#30/#32记录。
