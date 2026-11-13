# 香港合成测试后端

只用于 M4 条目5已在 main 生效后的指定 ECS、域名和 OSS；合并前不连接主机或桶。
先核实实例仍在免费试用期、实际到期时间和收费提示。试用结束或出现收费提示即停止并向 JT 报告；
不修改安全组、规格、计费，不购买资源。现役应用使用香港本机 PG17／Unix socket，组合为
`compose.yaml` + `compose.local-pg.yaml`。后文的新加坡 Supabase／5432 session 资料是历史兼容路径，
不能作为日常 L 发布的数据库目标。

## #762 私有宿主组合（B-only）

源码提供 `worker --runtime-manifest <B 的 0600 文件>` 的显式组合；默认 `worker` 保留原路径。
这不是对公众新增的 App API，也不因源码合并而打开真实实验。B 按独审、精确 CI、实际镜像/导入源码、
原账/全部在途及固定日窗核对后，才可配置 `compose.runtime.yaml`。L 不启用/编辑此覆盖层。

- 原签名、AUTH、MESSAGE/RUN、注册出口、Meter 和唯一费用账本均复用；RPC 不接受账号、模型、账本或路径选择。
  原 bearer 只定位其已绑定的原会话/子额度。call/propose/query 在原 worker 的私有 Unix socket 中组合，
  provider 仍由同一个现役 worker 执行，RPC 线程不派第二个模型/工具出口。
- B 的只读配置目录与可写合成原件目录分开挂载。身份文件 0600，原件/映射/claim 目录 0700；
  canonical、reference、mapping 目录的 device/inode 由 B 固定。缺失/替换不自动重建，
  不将非恢复 claim 控制目录用旧应用备份覆盖，也不清空映射绕 UNKNOWN。
- `national.2` 是显式新增的三槽基线；旧默认 `national.1` 不变。
  全国追问槽只含原 `reply is concise and useful`，后续规划/保存 authority 文本不属于槽。
  源配置/fixture 的 UNRUN 和 `runtime_eligible=false` 不代表部署或训练资格。
- v4 取证只接原 canonical claim、原 MESSAGE/RUN 与当前读取资格匹配的既有合成主体；
  不逐次修改消息白名单。旧 v1/v2/v3 窗口不被扩大；并行的诊断窗口必须与 runtime 主体不重叠。
- `python -m cj_api.runtime_client` 只连接固定私有 socket，读 0600 token/params 文件，
  先写 UNKNOWN 回执再发送，结果保存在 0600 文件；不将 bearer 放 argv/日志，不自动重试。
  丢 ACK 后以同一 logical attempt 查询。读原件仅解析 B 发出的 opaque ref，不支持任意路径或 URL。
- 合法 task setup 未齐时 E/F 的 call/propose 在写 G intent 和付费前返回 UNRUN；
  额度、健康检查、源 C0 或局部本地 PASS 都不能替代完整 setup、实际新 pins、独立判定及正式使用通知。

## 日常 API/worker 发布（B/L 标准流程）

职责以 [JT 的 B/L 决定](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6814548220) 为准。
L 拥有 Lio 业务源码及对应测试；其他线未实际占用时，可随时按标准流程自行部署可回退的 API/worker 应用镜像。
B 拥有香港调度、账本与额度、运行配置、基础设施及发布入口；协调文件仍按 PR 文件锁使用。
以下流程不授权新账号、延长邀请资格、改变预算、数据库迁移或新增云资源。

### 1. B 签发部署包；L 固定构建源

B 在 #759、#702 给出固定日窗或临时变更、执行人和允许操作。已交付的固定日窗、独立身份、
原账子额度及现役固定发布模板可在原范围内重复使用，不逐次等待 B 再发 ACTIVE。
L 闲时部署规则见 [JT 11-13 调整](https://github.com/JTCAO515/G2C/issues/759#issuecomment-6840048978)；原表保留其他线合成时段。今天 11-13 09:00–11:00 优先保障 L 发布已合 main，未合功能不阻挡已合修复上线。
原合成日窗和实际资源交付分别见 [原窗口表](https://github.com/JTCAO515/G2C/issues/759#issuecomment-6818911393)
及 [身份/子额度](https://github.com/JTCAO515/G2C/issues/759#issuecomment-6820312748)。条件预留不是 ACTIVE；
部署窗也不是模型／工具／MESSAGE 验收窗。包中固定：

- 精确已审 head、合并提交与树／改动文件等价证据、精确 CI 和适用审查链接、main CI 状态；
- 源提交、目标平台、目标实际镜像摘要、上一兼容镜像摘要，以及源码／依赖核对材料；
- B 维护的固定发布脚本、gate、回退脚本／gate 的路径与摘要，以及当前配置和采集覆盖层；
- 实时原账行数／锚、排空证明、账号资格与原限额，以及必要的 0600 合成凭据文件路径。

L 只用 B 交接的既有访问入口与指定文件；不复制私钥、凭据或 `.env` 到仓库、镜像或聊天。
不输出完整 `docker inspect`、`Config.Env`、`docker compose config`、Authorization header 或环境文件。
如果包、许可、摘要、资格或窗口已失效，停止新操作，由 B 核同；不换身份、ID、端点或预算续跑。
临时变更及配置/额度/基础设施仍只由 B 操作；用完按 #759 的原账锚、实际用量/占用、增额用途和预计调用量申请，
不互借其他线身份或额度、不每日自动重置余额。

在独立、干净、已提交的工作树构建。`G2C_RELEASE_SOURCE` 和以下路径由 B 的部署包确定，
不能取浮动 `main`／`latest` 或模型生成的命令。当前香港平台为 `linux/amd64`：

```bash
: "${G2C_RELEASE_SOURCE:?B-issued exact source required}"
test "$(git rev-parse HEAD)" = "$G2C_RELEASE_SOURCE"
test -z "$(git status --porcelain)"
# 先读 PR 的原门禁结果；以下命令不会为你豁免尚未通过的检查。
: "${CJ_PG_BINDIR:?explicit PG17 bindir required}"
"$CJ_PG_BINDIR/postgres" --version
uv sync --locked --group dev
CJ_ENV=local PYTHONPATH=.:scripts uv run --locked python -B -m deploy.hk.build --platform linux/amd64
docker image inspect "g2c-beta:$G2C_RELEASE_SOURCE" \
  --format '{{.Architecture}} {{index .Config.Labels "org.opencontainers.image.revision"}}'
```

现有 builder 同时生成应用和 operator 镜像；日常 L 发布只传应用镜像，不启动／替换 operator、
postgres、migrate、backup、rehearsal 或 caddy。构建／依赖失败不是许可跳过门禁的理由。
B 若提供已审缓存构建配方，须证明锁文件／pyproject／Dockerfile 与其适用基线相符、
源码完整覆盖且没有删除文件残留，并核依赖 Name/version/RECORD；不能自行拼接旧层冒充新源。

### 2. 传输与现场核对

只传到既有香港主机，不新建镜像仓库。`G2C_HK_SSH_KEY_FILE` 是安全文件路径，不能是私钥值；
保留已有主机验签，不更改网络、代理、安全组或 SSH 校验设置：

```bash
set -o pipefail
docker image save "g2c-beta:$G2C_RELEASE_SOURCE" | \
  ssh -i "$G2C_HK_SSH_KEY_FILE" -o BatchMode=yes -o StrictHostKeyChecking=yes \
  "$G2C_HK_HOST" 'docker image load'
```

加载 ACK 不明先只读查原镜像，不直接重复加载／切换。B 核服务端目标平台、实际 image ID 与 OCI revision，
并在无网络、无秘密挂载的目标镜像中核已提交源码清单和实际 import 文件字节。
标签、构建退出码或 Vercel 结果不能替代此证明。多平台索引摘要和服务器单平台配置摘要可能不同，
记录各自真实值，不能把其中一个手填成另一个。依赖变更须对应已审锁文件／构建输入。
新增运行资源必须进入已提交构建白名单；不能依赖开发工作树中的额外文件。

B 用受保护只读入口核当前签名 release、数据库／schema 兼容性、运行角色与 owner 隔离、
原账及全部在途。包括 MESSAGE 投递、queued/running RUN、queued/running/publishing 后台任务、
pending/inflight Memory 任务；历史 UNKNOWN 原件和占用保留，不能为“排空”清数据、结算或重放。
有在途先核原动作，不在运行途中切换源、模型、提示词、工具、候选或参数。
需要迁移、配置／凭据／权限变更或新资源时，交 B 按其相应授权与红线流程处理。

### 3. L 执行 B 的固定应用切换

发布前核 #759/#702 无其他 ACTIVE 批次，公告本次开始/结束；活动轨迹未归还时不穿插。B 的版本化入口 `deploy.hk.application_release` 去掉固定小时限制，仍要求最长两小时的明确 gate 时段，保留部署互斥锁和全部在途检查。
B 的发布脚本负责：互斥锁、窗口和精确源／镜像／门禁检查；关闭 API 入口后再次检查排空；
停止旧 worker；应用 B 已批准的唯一镜像选择；只重建 API/worker；核同实际镜像和源码、
API readiness 与 worker 存活。L 不手改 `compose.env`、任何秘密文件、Compose 或采集清单。
镜像选择及临时覆盖层也由 B 预置，不允许 L 把任意参数传成另一套配置。

```bash
# 这两个路径及脚本摘要来自 B 当前部署包；只接受其批准的固定路径。
ssh -i "$G2C_HK_SSH_KEY_FILE" -o BatchMode=yes -o StrictHostKeyChecking=yes \
  "$G2C_HK_HOST" "python3 '$G2C_HK_RELEASE_SCRIPT' '$G2C_HK_RELEASE_GATE'"
# 预检明确通过、仍在同一有效窗口后，执行一次：
ssh -i "$G2C_HK_SSH_KEY_FILE" -o BatchMode=yes -o StrictHostKeyChecking=yes \
  "$G2C_HK_HOST" "python3 '$G2C_HK_RELEASE_SCRIPT' '$G2C_HK_RELEASE_GATE' --apply"
```

只用部署包中已经存在且由 B 核同的入口，不能自行创建同名脚本／gate。
宿主 Python 和镜像 Python 可能不同，B 须验证实际执行环境；不要在现场安装工具修环境。
健康检查不调用付费模型。API/worker 必须同源；`/health/ready` 200 还需结合 worker、
实际源码／镜像、资格、原账与身份回读判断。模型、工具、保存／修改／撤销和质量仍各自标注
PASS / FAIL / UNKNOWN / UNRUN，不能从健康或本地 fixture 推导真实端到端 PASS。

切换后由 B 只读核原账前后锚、运行角色、拥有的 Trip/Memory 行集和全局在途，交回可复核结果。
L 在对应票和 #702 记录 source/image、检查层级、未跑项及 B 的账锚引用。
同源 source 未经通知变化，旧评测包和剩余 ID 不得直接续用。

### 4. 回退与未知结果

新源启动／健康失败时，固定发布脚本先按原阶段记录恢复上一兼容应用镜像，保留所有业务数据、
版本、回执、删除 fence、账本及未知 hold。旧采集窗口已经关闭／到期时，不能用其过期清单重启 worker；
由 B 提供默认同源 worker 或当前合法覆盖层。已存在新数据／配置时先评估旧镜像兼容性，
不能删字段、数据、凭据或放宽校验来让旧镜像起服务。不兼容时交 B 向前修复或保持安全关闭。

SSH／启动 ACK 不明只读查原容器、脚本阶段记录与原回执；不再次执行 `--apply`、不换 ID 试第二次。
需要后续回退时，L 只能在 B 批准的回退范围和入口执行已交付的回退脚本／gate，不能手工回滚数据库或账本。
回退后同样核 API/worker 同源、ready、原账与在途；未核到的结果明确 UNKNOWN。

### 5. 业务窗口由 B 另行开放

正式业务按 **A → L/C → D/E** 串行，B 在 #759、#702 公布当前占用、下一时段、开始／停止新派发／结束时间。
不能用 A agent 的零请求推断 JT 手机已暂停；部署前和窗口交接前均读实际在途。
同一身份和行程不同时交两线修改；源／模型／提示词／工具 profile 和 C0/pin 在窗口内固定。
仅在合法 setup、身份资格、原限额及用途子额均已到位后开放；D/E 还须满足其题集／独审等前置。
E/F 登记预算或 source-only C0 不是可执行子额／实呼资格，也不能重置余额、释放未知占用或新建影子费用账。

原件采集默认关闭。需要合成原件时由 B 给现役 worker 配置确切 source、主体、新 MESSAGE ID、
0600 清单和 0700 输出目录；L 不改采集身份／范围／期限，不覆盖旧原件。
结束时先停止新派发、核原动作／费用／在途，由 B 关闭租约并处理采集配置。
发生 FAIL/UNKNOWN 立即 STOP_NEW，只读核原 attempt；不能把旧结果带入新分母或用新 ID 补跑。

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

### #32 投影前工具原件的受控采集

现有共享账的 `response_sha256` 对应规范工具结果，Lio 后续模型输入只含其投影。
旧结果没有另存完整原件时，不能从投影还原。新合成窗口可在同一个现役 worker
增加 `--tool-evidence-manifest /run/tool-evidence/window.json`。API 与迁移入口拒绝此参数。
默认启动不采集。仅 B 在独占窗口配置已有受邀 Demo 主体及新 MESSAGE ID。

清单由 worker UID 持有，普通文件、0600、无符号链接，格式如下。
`source_commit` 固定为实际已审构建源，`expires_at` 为该窗口的明确结束时间，最多一天。
输出目录为独立挂载、同 UID 持有的 0700 目录。运行清单、原件和凭据均不入 Git。

```json
{
  "version": "G2C-tool-evidence-window.1",
  "directory": "/tool-evidence",
  "messages": [{"subject": "m4-synthetic-demo-0123456789ab", "message_id": "new-synthetic-original"}],
  "expires_at": "2026-11-11T04:00:00+00:00",
  "source_commit": "REPLACE_WITH_EXACT_REVIEWED_SOURCE_COMMIT"
}
```

采集只观察原注册工具出口已经得到的规范结果。供应商原回执持久保存后、结果投影前，
将同一原操作的输入、完整规范结果、摘要、Meter attempt、RUN、实现摘要写为
`G2C-tool-evidence.1` 的独立 0600 文件。没有第二次工具调用，不能覆盖已存在文件。
选中消息的采集过期或写入不确定时保留 UNKNOWN，不盲重放原请求。

C 只读取得自己这六条原件后，逐条核对三段。

1. `SHA256(result_utf8)` 与唯一共享账原工具回执的 `response_sha256` 相等。
2. 原件内的 RUN、operation、attempt、`input_sha256` 和实际注册输入一致，Meter 原回执已结算。
3. 同 RUN 的实际后续模型输入包含由该原件形成的 Lio 投影，并与原工具调用绑定一致。

文件本身不证明 RUN 已完成、模型已续接或产品通过。缺失、不完整原件及原 INTENT
继续保留原状态。B 在每格前核 A/JT 无在途，遇 FAIL/UNKNOWN 停止新派发。
窗口结束移除该启动参数和挂载，重建同源 worker，保留原件与唯一账。

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

`CJ_BETA_DB_POOL_SIZE=4` 可在香港合成环境启用每进程有界的运行角色连接池，允许 1–8 条。
省略时逐次新建连接。每次借用仍在 5432 session 模式核实际 TLS 与身份，执行 DISCARD ALL，
并确认 scope 已清空。事务入口重新绑定 LOCAL scope，原签名 release 与撤权查询每次重新核对。
跨事务持有的 worker advisory lock 使用独立物理连接。operator、cleanup 及备份角色不入运行连接池。
失败事务和结果不明的写入沿原恢复规则，连接池不重放业务 SQL。移除设置并重启即可回到逐次连接。
启用时日志记录物理连接 TLS 时长和 checkout 校验时长，记录不含 scope、凭据或业务内容。

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

`worker.env` 可另设 `CJ_BETA_MODEL_STREAM_SUBJECT` 为一个原已邀请合成主体，
仅选择 [MODEL-TOOL-TURN-STREAM@1](../../contracts/run/MODEL-TOOL-TURN-STREAM-V1.md)。
默认不设，其他主体继续使用原 v2。先暂停测试提交、核对原 delivery 已清空，
再切换或移除该选项；同一原 UNKNOWN 只读核对。
另获组装流式授权时，在同一个 0600 worker 文件设置
`CJ_BETA_ASSEMBLY_MODEL_STREAM_SUBJECTS_JSON` 为与现有组装完全相同的中英主体数组。
两主体的同一原模型轮按既有 profile 增量输出最后正文；单主体配置和默认 v2 选择继续生效。

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

## 可选的 #660 内测组装

只给同一批 `m4-synthetic-660-<12位十六进制>-zh` 和 `-en` 开启。将两份可分别注销的合成主体加入
原邀请、API Typed policy 和 MESSAGE allow-list，以及 worker 的同一 Typed policy/selection。
`CJ_BETA_ASSEMBLY_SUBJECTS_JSON` 明确选择两份主体，`CJ_LOCAL_NEEDS_PROFILE` 沿用 `manual-v1`。
在 API 0600 文件增加原受限 cleanup URI 和 32 字节 cleanup HMAC。worker 无需这两项。
规划沿同一原 MESSAGE、Needs/Travel、RUN 和 Meter；Trip 采用、修改和正式读回仅对组装主体开放。
仅在该组装对另获内部凭据授权后，在 0600 的 `worker.env` 配置
`CJ_BETA_ASSEMBLY_RUN_CREDENTIAL_SUBJECTS_JSON`，值为同一对主体的 JSON 数组。
默认关闭。启用要求现有 600 秒 Meter，每个原 RUN 最多一枚 11 分钟内部凭据，仍逐次检查撤权。
暂停提交并确认无在途后，从 worker 文件移除该字段并重建 worker 可恢复原 5 分钟组装范围。
Typed 保存、管理及既有 `/v1/memory-erasures` 不安装 V1 记忆写入。device-v4 使用同一认证身份，
注销采用既有 cleanup 登录和原登记内容域，离线与客户端控制记录按原清理协议验收。

在原 A/C 无在途且 API、worker 暂停的维护窗口，用同版镜像执行
`python -m deploy.hk.assembly_profiles bootstrap|insert|inspect <subject>`。
使用当前签名 release 和原 0600 operator/worker 配置，挂已有 release、CA、以及持久私有 `/operation`。
先以原初始化入口建新合成主体的预算及 Typed 命名空间。`insert` 要求 canonical Typed 只读预检，
原 profile 缺失才以已有 `postgres` 写一次。持久 intent 存在或结果不明时只能 `inspect`。
配置切换前保留当前镜像与环境版本。回退先停提交并核原动作。已写的 profile、账本及 fence 保留。
用原签名 API 预建每个主体的空会话、合成 Needs 和 Travel，再向 A 交 0600 范围和两小时凭据。

## 验证

### 香港本机 PG17

仅在已批准的 (b2) 切换使用 `CJ_BETA_DB_TARGET=hk-local` 和 `compose.local-pg.yaml`。PG 服务使用
已审 operator 镜像，禁用网络，只在受控挂载的 Unix socket 接收 SCRAM 登录。API、worker、cleanup
和 operator 各按原角色边界加载 0600 文件，原 Supabase TLS 配置作为归档保留。

暂停 API/worker、确认 A/C 无在途及原账本锚点、暂停日备。原配置下以新 operator 镜像挂载空的私有
`/local-pg` 并执行 `python -B -m deploy.hk.local_postgres stage`。它从已签名日备取基准，
再取完整安全点、按原恢复顺序加载 fence，验证目标状态后冻结源的应用登录和默认读写。
保留归档状态；任何不确定结果先核原件。只将新连接值分别安装到原 0600 角色文件，签名密钥与
唯一 SQLite 挂载路径继续复用。切换到本机配置后启动 `postgres` 服务，再用同一 operator 运行
`activate`、一次现有 OSS backup 和 `allow-writes`。前置 backup 要求当前 UTC 日尚未成功备份；
只有新签名备份完整上送并核对行、序列和 fence 后，才启动 API/worker。

发布前可撤掉目标 release 并核原 Supabase 快照，恢复源写入仍须另批。放行业务后只允许香港前滚，
使用同一 lineage 最新签名安全点并重放 fence，无法核实最新 fence 时保留不可用状态。
旧 `suspended.json` 和 `latest.json` 归档，保持原 Supabase 只读。

### Demo 邀请码

按 #685 指定的代号配置 `CJ_BETA_DEMO_SUBJECTS_JSON`，至多 205 个
`m4-synthetic-demo-<12位代号>`，同时纳入原邀请、Typed API 策略和 worker 记忆选择。
创建 UID10001 所有的 0700 `/srv/g2c-beta/demo-auth-socket`，worker 保留原签名私钥，
API 只读挂载 Unix socket 目录。公网 `POST /v1/demo-invite-sessions` 的接口见 #685。

迁移前暂停 API/worker 并核对原队列及签名 release。原 operator 用新镜像运行
`python -B -m deploy.hk.demo_schema`，一次追加 0049 并保留原 fence，建立新的本地签名备份基准。
已在 0049 的 Demo v2 主机只追加 0050，使用 `python -B -m deploy.hk.demo_schema --target 50`。
Lio 的本机追加迁移使用 `python -B -m deploy.hk.demo_schema --target 51`，沿用相同的原队列、
签名基准和删除 fence 检查。香港 worker 在获准接入现有 Trip 签名凭据后启用 Lio 规划保存。
该配置只从 worker 的 0600 秘密文件读取 `CJ_BETA_CONFIRMATION_B64`。缺少配置时，现役 Demo
和 Lio 纯问答及时间线读取继续提供服务，规划保存保持关闭。
发布前在主机内核对两份受限秘密文件中的 Trip 签名凭据一致，只记录核对结果。
日备在新签名基准核实后续接。发现原升级标记时先只读核同，不能重复执行。
用已挂载原 operator 和 worker 0600 文件的 operator 容器运行
`python -B -m deploy.hk.demo_accounts bootstrap <subject> --digest <sha256> --expires-at <RFC3339>`，
再运行 `insert <subject>` 做原 canonical Typed 预检和单次 profile 激活。
邀请码原文只在开发 Mac 的 0600 文件，服务端仅保存摘要。
长码 `D1-<12位账号代号>.<22位凭据>` 保持兼容。短码仅接受区分大小写的
`G2C@<两位数字>` 和 `CJ_Tester@<两位数字>`（两组各 `01`–`99`，不含 `00`）；账号代号取完整短码 ASCII
SHA-256 的前十二位十六进制。只有已配置主体且原数据库中的完整邀请码摘要、
资格期限和撤销状态全部匹配时才签发会话；短码格式本身不创建账号或授予资格。

批量账号的 API typed Memory 策略可显式使用 `CJ_BETA_TYPED_MEMORY_POLICY_GZIP_B64`：
对原完整策略 JSON 做单个 gzip member 后 base64 编码，仍只放在 API 的原 0600 环境文件。
它与旧 `CJ_BETA_TYPED_MEMORY_POLICY_B64` 互斥，旧格式继续支持；解压后仍逐项验证原策略和主体名单，
不生成默认权限。环境文件仍限制 65,536 字节，解压策略仍限制 262,144 字节；
截断、CRC 错误、额外 gzip member 或尾随数据均拒绝，worker 不接受该 API 配置。
worker 的双层运行策略可单独显式使用 `CJ_BETA_MEMORY_RUN_POLICY_GZIP_B64`，与原
`CJ_BETA_MEMORY_RUN_POLICY_B64` 互斥，仅进入原 worker 0600 文件；API 不接受该字段。
它复用相同限长解压，结果仍经原 TypedRuntimeConfiguration 和全部主体/selection 校验，
不会从 API 策略推断 worker 权限。批量配置必须同时核对两个角色的完整策略及原有身份不变。
实际增加名单前先预检完整环境文件及原策略边界，不能仅凭 205 的名单容量宣布账号已开通。
先以原名单和原配置发布兼容新表示的应用，再由 B 在独立维护阶段备份并启用批量名单和策略。
启用新表示后，退到不识别该字段的旧镜像前，须先恢复其兼容配置；不能只用应用镜像切换入口回退。
配置回退保留账号原件、资格/撤销记录、业务数据和唯一费用账，不恢复旧账或删除新账号来过门禁。
新增手工测试主体的费用归属用 B-only `python -B -m deploy.hk.manual_test_allocations MANIFEST` 先只读核对，
明确核同后才加 `--apply`。原 0600 清单格式为 `G2C-manual-test-allocation.1` 加 `subjects` 数组，
只接受已配置 Demo 主体、每批最多 198 个；只向现有 A 组追加，不允许改绑已有其他线身份。
该入口使用原账本事务和非恢复控制锚，不调用首次 `activate`、不改任何限额或费用/占用记录。
结果不明先读取同一原账与控制状态，不重复初始化或建立另一账本。

`revoke <subject>` 立即拒绝原邀请码和会话；确认原 scope 无在途后，`rotate <subject>` 可登记
新摘要与有效期，旧会话继续拒绝，每日计数保留。结果不明先 `inspect <subject>` 和原动作日志。

#### 七天滚动会话

JT 的 [#495 决定](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6783256928)
适用于现有香港内测 Demo 主体。新增入口如下，响应均为 `Cache-Control: no-store`。

| 入口 | 请求与结果 |
|---|---|
| `POST /v2/demo-invite-sessions` | JSON 为 `{version:"DEMO-invite-session.2",invite_code,consent:true}`。成功返回 `{version:"DEMO-invite-session.2",access_token,subject,expires_at}`。 |
| `POST /v2/demo-session-renewals` | 当前仍有效的 Bearer JWT，JSON 仅 `{version:"DEMO-session-renewal.1"}`。成功返回相同 `.2` grant，保持原 subject、issuer、audience。 |

新凭据从签发时刻滚动最多七天，截止不超过原邀请资格。续期不延长资格，不更改业务
composition 或计量。有效旧两小时凭据可升级；过期、撤销、轮换前或不属于 Demo 的
凭据拒绝续期。签名仍由原 worker 的私密 Unix socket 提供，API 不持私钥。
签发事务对资格行加共享锁，撤销/轮换与之串行；撤销后新旧凭据的业务与续期均拒绝。

错误沿用 `{request_id,error:{code,category,message_en,message_zh,outcome,recovery}}`。
续期 400 为 `INVALID_INPUT/input/failed/do_not_retry`，401 为
`DEMO_SESSION_DENIED/access/failed/do_not_retry`，503 为
`DEMO_SESSION_UNAVAILABLE/dependency/unknown/do_not_retry`。
邀请码 401/503 沿用 `DEMO_INVITE_DENIED`、`DEMO_LOGIN_UNAVAILABLE`。
客户端在有效会话回前台且余期不超过一天时续期，未知时保留仍有效旧凭据。

`/v1` 和 `.1` 为旧内部构建保留原两小时上限，退出条件为旧构建退场。
部署先核原资格、撤销与 session floor，原私钥和资格期限沿用。
回退到原镜像会恢复 v1 签发，A 需配套使用 v1 入口/构建；已经签发的凭据仍受原
资格与撤销检查约束。回退不自动轮换 JT 的邀请或清除其原数据。

MESSAGE 只对实际新接受的原件计数。0052 将北京时间每日上限从 40 提至 400。
同原件回查和幂等重入沿用原回执。香港额度迁移已经提交，或任一合成账号单日已受理超过 40 条时，0052 拒绝降级。
已应用 0051 的香港内测主机可在原 API/worker 暂停后，用新 operator 镜像运行
`python -B -m deploy.hk.demo_schema --target 52`。该操作读取原 80 次配置，
在同一事务中提升现有香港合成名单的当期账本和 Demo 次期账本至 800 次，
并追加 0052。原尝试、保留、回执及周期边界保留。只有签名备份基准完成后，
才将暂存的 `CJ_BETA_RUN_CONTEXT_JSON.current.meter.budget=800` 和同源 API/worker 切入。
共享费用、调用次数和外部服务停点沿用现有门禁。事务前失败可恢复旧服务。
已提交 0052 时，用新 operator 运行
`python -B -m deploy.hk.demo_schema --resume-quota` 续结原签名备份，保留未发布的备份尝试。
已轮换 identity 时，先核对原签名备份与活库行集、序列和 fence，再补发同一 release。
API/worker 只在签名标记完成且运行配置为 800 后就绪。
Demo 及已启用流式的组装两主体使用 [STREAM@2](../../contracts/run/MODEL-TOOL-TURN-STREAM-V2.md)，
可调用工具的轮次先收齐原回执。混合响应仅执行通过原门禁的工具，丢弃未核实的同轮正文。
过旧服务期限后，实际模型和工具仅允许显式 Demo scope。首次开户同时在原 PG Meter 中准备
12 月非重叠期间，保留原期间和唯一对外费用账本。北京时间 12 月 1 日确认无在途后重建
API 与 worker；两者从同一原配置选到新期间。旧的非 Demo 待处理原件保持原状。

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
