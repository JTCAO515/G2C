# 香港员工工作台上线（#1886 Part 2）

上线源须为已审合并提交，同时记录 SHA、CI、同机 CJ 就绪证据与现场负责人。将该提交的 `git archive` 和 SHA-256 通过既有验签 SSH 送至只含本次资源的 0700 暂存目录。归档只需 `jt/`、本工作台部署目录、`deploy/hk/Caddyfile` 和存储登记。验证 SHA-256 后，在该私有目录中用 `tar --extract --gzip --file=source.tar.gz --same-permissions --no-same-owner` 解包，保留 Git 文件读取权限。这样构建时的容器 UID 10031 才能读取 `jt/`。先核对实际主机文件、现役镜像和维护状态，再在主机用 `bash <源码>/deploy/hk/jt-workbench/install.sh <源码> <提交 SHA>`。使用已有镜像和锁定依赖，在无构建网络的条件下构建独立工作台镜像。脚本持有 CJ 既有部署锁，若备份运行、资源不足或 Caddy 现役不是预期基线则停在公网站点切换之前。

PostgreSQL 沿用服务器上的现有实例。现有套接字权限、CJ 的 HBA 行及角色保持原样。systemd 的 Unix 代理只打开独立的组控套接字。工作台两个登录仅限专用数据库和 SCRAM，应用只能挂运行角色连接文件。迁移角色单独执行，连接文件为各目标容器 UID 600。工作台容器没有网络或公开端口。Caddy 沿用现有 `/config` 绑定，在专用子目录仅具组读与查找权限，只有工作台 UID 能更改目录。服务器原有配置原地追加新域名，Caddy 2.11 SIGUSR1 热重载保留旧监听。接下来从公网用有效证书访问 `/login`，检查 `/queue`、`/cases` 与 `/operations` 未登录重定向，同时复查既有 CJ `/health/ready`。

现有每日备份完成后，systemd 独立启动工作台 PostgreSQL 导出。工作台备份容器只挂专用库连接、私有工作台备份目录和只读备份程序。它没有网络、CJ 凭据或现有 OSS 账本访问权。工作台首轮使用现有服务器上的私有目录，已验证档案与 SHA-256；工作台异地备份待单独落实，不占现有 CJ 的 OSS 日备额度。恢复前关闭入口，验证对应工作台备份清单和 SHA-256，向隔离库恢复。重新开入口前，停工作台容器，将最新有效名单写入仅工作台 UID 可读的 `recovery-roster.json`（员工名映射到当前角色，只列归档中仍启用的人员）。使用下方受控恢复入口清空归档里的全部旧密码和会话，并由被指定的恢复管理员本人在终端输入新密码。管理员登录后，在「用户管理」页为名单中的其他员工逐一重设密码。工作台存储及其离职清理入口在 `backend/storage-registry.json` 的 `staff_stores` 中登记。CJ 注销流程只读取同一文件的 `stores`，员工标识不映射到 CJ 用户。

## 登录方式与首个管理员（2026-11-27 起）

后台只用「用户名 + 密码」登录，没有第二因素：这是 JT 2026-11-27 的决定，风险记录在 [#1886 的评论](https://github.com/JTCAO515/G2C/issues/1886)。其余防护不变：服务端限速（全站每分钟 20 次尝试）、单账号连续失败 5 次锁定 15 分钟、仅 HTTPS、会话最长 60 分钟且闲置 15 分钟失效、安全响应头和 noindex。密码至少 12 位，用加盐 scrypt 存储，永远不进日志、审计或命令行参数。

库里没有可用管理员时，由 JT 在自己的终端运行下面的一次性命令，建首个管理员 `jtcao01`。密码由 JT 在隐藏输入提示里自己输入两次，部署者和 Claude 都不经手。库里已经有一个启用的管理员时，命令直接拒绝执行。

```sh
# 先用 ssh -t 登录香港主机（必须有 TTY），然后：
cd /srv/g2c-beta
docker compose --env-file jt-workbench/images.env -f deploy/hk/jt-workbench/compose.yaml exec app /bin/sh -ec 'export JT_WORKBENCH_DATABASE_URL="$(cat /run/jt-workbench-connection)"; exec python -B -m jt.workbench.production bootstrap-admin --username "$1"' jt-workbench jtcao01
```

终端要有 TTY（`ssh -t`，不要加 `-T`，不要用管道或重定向喂入密码）。命令只输出「管理员 jtcao01 已创建。」。之后用该账号登录 `https://jtadmin.go2china.space/login`，在顶部「用户管理」添加其他员工：填账号、角色和密码（两次），交接密码走私下渠道，不进聊天、PR、仓库或日志。现阶段不要求员工首次登录改密码。

管理员可在「用户管理」页：添加账号；重设任何启用账号的密码（含自己，重设后该账号所有会话立即失效，需重新登录）；改角色；解除锁定；停用；启用已停用的账号；删除已停用的账号（清除密码、撤销会话，用户名保留以维持审计引用，不可恢复）。管理员不能停用、删除或降级自己。所有操作都写审计（时间、操作者、动作、目标、结果），审计和页面不含密码；表单有 CSRF 令牌和同源检查；非管理员访问这些页面一律 403。

归档恢复专用入口。在旧工作台实例已停止、当前角色清单核对后，在私有交互终端（需要 TTY）执行；恢复管理员本人在隐藏提示里输入新密码，不出现在参数或日志里。

```sh
docker compose --env-file jt-workbench/images.env -f deploy/hk/jt-workbench/compose.yaml --profile operator run --rm --no-deps recover-admin '<获准管理员名>'
```

员工离职时，管理员先在「用户管理」页停用该账号（会话立即失效），再点「删除账号」清除密码并保留审计与不可重用的登录标识。网页删除已经够用；下面的命令是兜底，由部署操作者在数据库所有者层面对已停用的账号再清一遍会话、限速状态和任何残留凭据，参数替换为对应员工名。

```sh
docker compose --env-file jt-workbench/images.env -f deploy/hk/jt-workbench/compose.yaml --profile operator run --rm --no-deps -T offboard '<username>'
```

## 现场验证和回滚

上线前确认同机 CJ 的维护窗口与快测资格，保留切换前 API/worker 版本、公开健康返回和备份服务状态。切换后先读回工作台 HTTPS 登录页（只有账号和密码两项）、三条匿名重定向以及 CJ 现役版本和健康返回，再按 [CJ API 快速冒烟](../SERVER-SMOKE.md) 用获准合成会话执行问答、文字翻译、滴滴链接。保留原回执。快测 `FAIL` 即执行回滚，`HOLD` 或 `UNRUN` 保持为待验收。

工作台端由 JT 运行上面的首管理员命令并登录，再在「用户管理」建一个独立的测试员工，验证队列、案件和运营台。用该可停用的测试账号验证错误密码与连续失败锁定，用复核员会话验证运营写操作拒绝，用非管理员会话验证「用户管理」被拒绝。验收记录只留状态和脱敏截图。备份读回检查同一每日任务的实际工作台 `pg_dump`、归档清单以及哈希。

故障时持既有部署锁，读回当前站点、应用和备份状态。在原 inode 恢复 `jt-workbench/Caddyfile.before` 后发 SIGUSR1，确认 CJ 就绪并复测失败项。停工作台 app、工作台备份与转发 socket，撤下工作台的每日备份 drop-in，重载 systemd 并读回 CJ 原日备配置和工作台路由已下线。保留工作台数据、审计及备份，以便原地恢复。实存数据库、角色和备份的进一步删除另由 JT 授权。

若 JT 批准永久撤下，先停入口、工作台容器与备份接入，验证导出的工作台备份及其 SHA-256，并由 JT 移除 Spaceship 的 `jtadmin` A 记录。只有在导出和审批均确认后，才以数据库管理员在现有 PostgreSQL 的管理库删除 `jt_workbench`，随后删除 `jt_workbench_runtime`、`jt_workbench_owner`，及仅针对二者的 HBA 规则后热重载。此步骤不会删除或修改 CJ 数据库、角色和备份。

## 升级到「仅密码登录」（迁移 004）与回滚

- 迁移 `004`（schema 版本 4）由现有 `migrate` 一次性任务应用，已经是 4 时什么都不做，可重复运行；整个迁移在一个事务内，失败会整体回滚。内容：放宽审计动作取值（新增启用、删除、重设密码；历史的 TOTP 动作仍可读）；清掉没有设置完密码的半成品账号（没有任何审计或复核记录引用的整行删除，有引用的保留为停用且无凭据的占位，用户名不再可用）；清空所有残留的验证器密钥、设置码和重放计数；新增只读版本标记表 `password_auth_version`。不碰 CJ 的库、角色和 Caddy。现网只有一个没设置完的 `jtadmin`，会按上面规则被清掉。
- 升级前先确认当日日备成功，并再做一次迁移前备份：用既有备份服务单元跑一次，读回备份清单和 SHA-256；记下 `jtadmin` 账号当前状态（只读 `SELECT username, role, enabled, password_digest IS NOT NULL FROM jt_workbench.accounts`）。
- 回滚应用：用上一版镜像（`images.env` 里改回上一个 `JT_WORKBENCH_IMAGE`）重建 app。上一版忽略新增的版本标记表，数据库不用动，能照常启动。注意：上一版要求验证器，升级后创建的账号没有验证器，回滚后需要用上一版的恢复入口重新设置；回滚期间如已写入「启用、删除、重设密码」审计，上一版的审计页会无法渲染这些行，需先升回新版。
- 回滚数据库结构（只在需要时，与应用回滚配合）：`python -m jt.workbench.postgres down --steps 1`（所有者连接串）。它只撤销 004：还原审计动作取值、删除版本标记表；若审计表已有「启用、删除、重设密码」记录则拒绝执行（审计只追加，不为回滚改写）。被清掉的验证器密钥和半成品账号不会恢复，需从迁移前备份取回。不带 `--steps` 的 `down` 会一路回退到空库，已有业务数据时本来就会拒绝。
