# 香港合成测试后端

只用于 M4 条目5已在 main 生效后的指定 ECS、域名和 OSS；合并前不连接主机或桶。
先核实实例仍在免费试用期、实际到期时间和收费提示。试用结束或出现收费提示即停止并向 JT 报告；
不修改安全组、规格、计费，不购买资源。Supabase 仍是指定新加坡测试项目，只有5432 session模式。

## 配置与构建

`*.env.example` 只有占位符。正式配置在服务器 `/srv/g2c-beta/`，目录0700，所有实际环境文件0600；
从指定钥匙串私下交接，不复制到 Git/镜像/日志，不把值放在命令参数或聊天。
Compose以普通env_file传非秘密common配置（固定JSON、base64公钥和类型化路径，不含需要插值的变量）；兼容该试用机已装Compose2.27。秘密文件以只读bind挂载，由各入口按角色校验0600/UID/字段后读入进程；Docker Config.Env不持久保存密钥。
API仅收到运行角色、确认/history密钥和验签公钥；worker另收模型/高德和对应签名私钥；
operator另收既有数据库初始化凭据和恢复签名私钥；OSS凭据只进backup容器。应用和operator均UID10001；相应实际环境文件由10001拥有，宿主父目录保持0700。
`secret_setup` 仅在固定宿主私有目录由显式root operator执行一次，输入经stdin安全交接。
它生成相互独立的应用签名、恢复签名和确认/history/cleanup随机键，先持久INTENT再写六个0600环境文件；
原配置或中断状态只读核验/HOLD，不覆盖或重生成。入口在读取秘密前核指定实例hostname和/srv/g2c-beta持久绑定，拒绝容器层、tmpfs和错误路径。
common只含正式公钥和两名beta邀请配置。无秘密的compose.env由已审部署版本单独生成，
只锁源码镜像版本；更新应用版本不重新生成或修改既有秘密集合。
DashScope key按既有HTTP Bearer边界接收可见ASCII，不推断供应商key格式；换行、空白和非ASCII拒绝。
纯校验先于初始INTENT。仅经只读核实旧0801版本的精确19字节INTENT、无任何输出文件、
且同输入被旧model key格式误拒绝时，operator可显式使用 `--resume-rejected-validation` 续结。
它保留旧INTENT，以O_EXCL追加当前输入hash/nonce/时间及取证来源后才生成第一套密钥；
该新hash不冒充旧记录的绑定。并发只有一个胜者，任何部分制品、非唯一状态或后续中断仍HOLD。
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

首次OSS调用前，宿主root仅在JT明确答复后一次性安装非秘密授权文件 `/srv/g2c-beta/authorizations/oss.json`（root:0644、目录root:0755），只读绑定到 `/run/authorizations`。
运行时只读验证该root授权，恢复签名私钥不能签发/覆盖它；不随数据库恢复的 `/control/oss-quota` 另存签名零使用记录及空intents目录。
授权选择已确认免费覆盖或仅既有桶的限额付费；没有授权/计数缺失、签名损坏或期限到均保持关闭，不能初始化新额度。
SDK每次HEAD/ACL/PUT/GET先独占持久消耗意图（O_EXCL/0400逐次链和计数必须一致，旧签名计数回退也HOLD），最多300请求、2GiB预留字节；GET按该对象64MiB/1MiB上限预留，PUT按原长度预留，未知不返还。
付费模式另按每请求2分、每GiB2元作保守预留，上限10元；这是运行预留，不是供应商报价或账单，实际费用保持UNKNOWN。
counter必须来自宿主持久control绑定，授权来自独立root只读绑定，不接受容器tmpfs/overlay/子挂载；备份/恢复不复制或重置该计数。
抢锁后、写意图/计数后、最终SDK调用前重查试用与授权期限；失效保留占用，不派发。该机制不授权任何调用，本线须先取得#495对应JT答复，不能把提问当授权。
整套control（含oss-quota）是本轮不参与数据库恢复的连续信任锚；同时回退usage与全部intents的一致旧目录无法自检。
禁止把该目录纳入恢复或更换；若它整体恢复、丢失或连续性不明，先由宿主root撤下OSS政策、人工核对原累计，不得凭旧签名重开额度。

恢复目标是**同一主机内全新、仅Unix socket的独立PG17集群**，由本次operator进程亲自initdb/启动并签名绑定system_identifier/data_directory；其PG数据在持久target-control/pg内，失败也保留。核服务端listen_addresses为空和仅演练数据库，不接受任意目标URI/旧共享集群，不创建新云项目。
原集群中新空库仍有全局应用角色，会被明确拒绝；不重用角色、不给云角色扩权。
恢复按镜像规范pre-data → 最新检查点DATA（fence先行）→ 原post-data执行单事务，
不禁用trigger/replication-role，不删改原约束或RLS。历史数据不会被误当成新业务动作执行。
核对签名/hash、原schema、永久fence和物理删除后才签发该目标release；安全检查点在首次写入前消费，
不能重复恢复抹去后来删除。恢复前再次锁定当前源完整行集；如备份后发生注销/单条删除或其他写入，旧安全包明确拒绝且不消费、不写目标。
HK运行时每个业务事务在安装LOCAL scope前获取共享release事务锁并重新验证签名release；
独立cleanup事务同样先取共享锁，再由已获准runtime独立登录只读核库identity（cleanup未获schema元数据权限，不新增GRANT或用管理员执行删除）；恢复持独占锁，先关闭并轮换源identity，再签发隔离目标release，保持单一可写侧。
recovery命令在同一进程内创建目标、恢复并验证，结束时先核目标完整行集/sequence均未变化，再关闭并轮换隔离目标，核源未变化后恢复源release。若活跃隔离侧接受了写入、注销或删除，拒绝切回旧源，保持源关闭；中间失败保留原PG数据、birth签名、release和控制记录；`--resume`只启动/核对该同一system ID并续结原演练，不重新initdb、COPY或恢复。临时COPY暂存库仍只供生成备份，从未获得release。
隔离目标不自动替换现有云库或开放公网。

## 可选的手动 NEEDS

在已授权测试实例的 `common.env` 显式设置 `CJ_LOCAL_NEEDS_PROFILE=manual-v1` 后，
香港 API 复用已冻结的手动 NEEDS producer：`POST /v1/needs-actions`、
`GET /v1/needs-action-receipts?action_id=...`、`GET /v1/needs?needs_id=...` 与
`GET /v1/needs-revisions?needs_id=...&version=...`。仍用原签名身份与 owner scope，
提交原字节和 action_id；结果未知只查询原 action，不重发提交。
未配置时接口保持关闭，未知值使应用启动失败。该配置不启用模型抽取、正式 Trip、Memory 或 cleanup。
原 RUN@2 数据库入口已绑定 NEEDS scope，权限与迁移不变。

回退先移除该配置，再用已审镜像重建 API；保留原 NEEDS 数据和全部动作回执。
旧镜像没有该 API 时查询明确不可用，不能重建动作或改写原记录。
私有 PG、真实云回执与 App 验收分别记录在 #577/#30，不以本说明或本机结果代称云端通过。

## 可选的 typed 手动 Memory

仅在 API 的原 `api.env`（UID10001、0600）添加
`CJ_BETA_TYPED_MEMORY_POLICY_B64`，值为现有 `local-memory-typed.1` policy 的 Base64 JSON。
缺省且无 Memory 命名空间时保持关闭；格式错误、未知或未邀请的主体、错误文件权限明确拒绝。
policy 不进入镜像或 Docker Config.Env，也不放进 worker 的凭据文件。
字段与既有 wire 见 [C canonical host](../../backend/memory/HOST.md)，不另定义管理/撤回接口。

API 用原 `SupabaseTestDatabase`、RUN context 与 `runtime_transaction`，在构造时显式启用
travel capability，并将同一个对象交给 C 的 `register_typed_routes`。
Travel ID 必须来自原 `/v1/travel-context-actions` 回执，不从聊天、RUN 或客户端配置猜测。
应用配置中的选项不是 owner、collection 或当前版本的授权，最终 guard/lease 仍由原 producer 检查。

这是 API-only 的手动保存/管理/读取配置，不安装 worker 的 `TypedRuntimeConfiguration`，
不激活 MESSAGE 或正式 Trip profile，不宣称模型召回已配置。
policy 覆盖的主体在 canonical MESSAGE resolver 建行/入队前保持不可用；
其他主体保留原 MESSAGE 路径，Travel/NEEDS/一般 Feedback 的独立边界不变。
后续只有在相同主体的真实 worker 配置和原 MESSAGE reference/profile 组合交付后，才解除该消息门禁。

已有受邀主体的 Memory 命名空间时，缺少覆盖它的 policy 会拒绝 API 启动。
不能移除字段、删除数据或恢复旧账本来使旧镜像可写；旧镜像不识别该 API 私有字段时应保持不可用。
回退须使用支持同一 policy/数据的已审镜像或向前修复，保留全部原动作、财务及删除 fence。
真实 withdraw/stop-use/物理清理如超出旧授权演练范围，仍先按 #495 取得具体授权。
实际已验范围与尚未运行的 worker/正式 Trip/真实用户部分记录在 #586/#30，不能据配置或私有 PG 提升。

## 可选的 typed Memory worker 准备

worker 的原 `worker.env`（UID10001、0600）可单独配置
`CJ_BETA_MEMORY_RUN_POLICY_B64`，内容是 C 既有 `local-memory-run.2` JSON 的 Base64。
其中 `collection` 是上述 `local-memory-typed.1`，`selections` 对每个明确配置的邀请主体
指定 `subject`、`slots`、`max_bytes`；collection 与 selection 主体集合必须相等。
该字段只进 worker 文件，API 私有 policy 字段只进 API 文件；错误角色、未知格式或超出邀请名单均拒绝启动。

同一个 worker 按原邀请 scope 选择配置，经原 `TypedRuntimeMemory`、MESSAGE reference/lease、
RUN、Meter 与真实出口执行。未选择的主体仍用原路径；已有 Memory 却无配置仍拒绝，
不能用缺省配置绕过。全局、按 scope 及正式 Memory 配置不得混用。
内存选择的 `max_bytes` 也须满足原 RUN context 的 memory/output 限额，配置不会扩大额度。

这只准备 worker 配置入口，不改变云端 MESSAGE/travel profile，也不解除 API-only 主体的消息门禁。
实际激活前须核对原主体、原 Travel/版本和执行身份，按 #495 处理授权范围外的操作；
真实模型续答、回执与质量仍分别在 #30/#32 验证。移除 worker 配置不能恢复已有 Memory 主体的旧派发。

## 已有 Memory 主体的 MESSAGE 激活

先交付匹配主体的原 typed worker。对已有 Memory 的主体，旧 `activate-travel` 仍明确拒绝；
本机 operator 可显式传 `--typed-memory-run-policy` 与原 `--auth-dir`，由 C 的
`TypedRuntimeConfiguration.bind_readonly` 核原邀请/当前账号/同 owner 和已有 Memory 命名空间。
该验证不创建或修改 Memory。元数据仍只由原本机表 owner 写入，原 pending RUN/delivery trigger 不变；
运行角色无 profile INSERT/UPDATE，不通过 GRANT、换身份、删除数据或伪造 lease 解锁。

API 原 0600 `api.env` 可增加 `CJ_BETA_TYPED_MESSAGE_SUBJECTS_JSON`，值为明确选择的主体 JSON 数组。
该集合必须非空、无重复、被同文件 typed policy 和原邀请覆盖；worker 文件不接受。
API 启动还必须读到该主体已激活的原 `message-travel.1` profile。
未选择主体保留 API-only 拒绝；A 原无 Memory 主体的消息路径不变。

字段不是客户端权限或已安装 worker 的证明，只有受控部署确认同一配置/镜像后才可设置。
云端需使用表 owner 的 metadata 激活属于单独运维操作，必须核实 #495 的原执行身份/操作授权后执行；
此本机入口不接纳云 DSN。不得只改 API allow-list 提前开放队列。
激活后保留原 profile/数据。停止时先停止原 worker，核原在途动作，再移除 API 消息 allow-list
并重启 API 保持 API-only；仅移除 allow-list 不会撤销已入队的原动作。
不能删除 profile 回退旧 writer，实际未知原动作仍只读核对。

## 验证

```sh
uv run --locked python -B scripts/test.py
CJ_PG_BINDIR=/path/to/pg17/bin CJ_PG17_BINDIR=/path/to/pg17/bin uv run --locked python -B scripts/pg_suites.py
```

新增hk_recovery组复用原注销、单条记忆删除生产者，实际备份/恢复到第二私有PG，
检查物理缺失、其他owner、原费用/UNKNOWN、旧应用/旧包/消费重用拒绝。
镜像内 `python -B -m deploy.hk.runtime_check` 用全新临时合成签名键核验memfd，无网络或真实key读取。
本机、真实云数据库、真实模型/高德、实际OSS下载恢复和App目标网络证据分别在PR/#30/#32记录。

`rehearsal` operator只接纳本次密钥设置生成的两名随机合成恢复主体；另两名beta邀请不进入其worker。
演练名单和RSA签名对单独保存在rehearsal.env，不分发给正式worker；cleanup凭据也只给该入口。
seed经原签名MESSAGE/RUN/Meter写入、显式FakeProvider产生一条已完成和一条原UNKNOWN；不计真实模型验证。
seed后实际导出原base并核制品/hash、同源lineage、当前完整行与sequence和两主体数据后，
erase经原账号注销API和单条MEMORY-ERASURE服务、独立已批准cleanup角色执行。
验证注销账号消息与指定记忆物理消失、另一个账号保留、指定原operation和item的专属fence存在后才写DELETED；重复seed/erase只检查原阶段。
任意中断INTENT保持原主体/原动作待核，不新建身份重试。该工具不开放公网、不操作真实账号、不改权限。
`resume-seed --original-run-id ORIGINAL_UUID --original-input-sha256 ORIGINAL_SHA256` 仅适用于已只读核实A的唯一原未确认消息、RUN/注册出口均零、B尚无消息/记忆的SEED_INTENT。
参数必须来自原只读取证，并核固定演练消息的重建bytes、数据库原bytes/hash及已有签名记录一致。
它在release守卫下固定同一run ID及message hash，写SEED_RESUME_INTENT后由原worker接续该delivery；
不再次send A、不初始化账号或预算、不重开出口。任何可能已派发或再次中断的状态保持HOLD/只读。
worker脏会话审计在受信scope binder之前执行，保留零初始advisory锁检查；binder安装的事务级release共享锁不再误报脏会话。
`hk_cloud_rehearsal` PG组验证这套生产者组合，实际生成native checkpoint；另以签名hash-only假包验证删除前拒绝，不冒充真实云备份。

恢复operator仅接受32位十六进制 `--rehearsal-id`，目标固定在已核持久bind卷 `/rehearsals/ID`（宿主 `/srv/g2c-beta/rehearsals`，UID10001/0700）；拒绝tmpfs、容器overlay、缺挂载和符号链接逃逸。示例：

```sh
docker compose --env-file /srv/g2c-beta/compose.env -f /srv/g2c-beta/deploy/hk/compose.yaml run --rm --entrypoint python backup -B -m deploy.hk.recovery --base /backups/BASE_ID --safety /backups/SAFETY_ID --rehearsal-id ORIGINAL_32_HEX_ID
```

续结在同命令追加 `--resume`，仍用原ID；先由PG17 `pg_controldata`只读核system ID，wrong/unknown集群不得启停。失败不销毁目标。
