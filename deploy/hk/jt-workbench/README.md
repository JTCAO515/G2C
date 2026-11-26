# 香港员工工作台上线（#1886 Part 2）

上线源须为已审合并提交，同时记录 SHA、CI、同机 CJ 就绪证据与现场负责人。将该提交的 `git archive` 和 SHA-256 通过既有验签 SSH 送至只含本次资源的 0700 暂存目录。先核对实际主机文件、现役镜像和维护状态，再在主机用 `bash <源码>/deploy/hk/jt-workbench/install.sh <源码> <提交 SHA>`。使用已有镜像和锁定依赖，在无构建网络的条件下构建独立工作台镜像。脚本持有 CJ 既有部署锁，若备份运行、资源不足或 Caddy 现役不是预期基线则停在公网站点切换之前。

PostgreSQL 沿用服务器上的现有实例。现有套接字权限、CJ 的 HBA 行及角色保持原样。systemd 的 Unix 代理只打开独立的组控套接字。工作台两个登录仅限专用数据库和 SCRAM，应用只能挂运行角色连接文件。迁移角色单独执行，连接文件为各目标容器 UID 600。工作台容器没有网络或公开端口。Caddy 沿用现有 `/config` 绑定，在专用子目录仅具组读与查找权限，只有工作台 UID 能更改目录。服务器原有配置原地追加新域名，Caddy 2.11 SIGUSR1 热重载保留旧监听。接下来从公网用有效证书访问 `/login`，检查 `/queue`、`/cases` 与 `/operations` 未登录重定向，同时复查既有 CJ `/health/ready`。

现有每日备份完成后，systemd 独立启动工作台 PostgreSQL 导出。工作台备份容器只挂专用库连接、私有工作台备份目录和只读备份程序。它没有网络、CJ 凭据或现有 OSS 账本访问权。工作台首轮使用现有服务器上的私有目录，已验证档案与 SHA-256；工作台异地备份待单独落实，不占现有 CJ 的 OSS 日备额度。恢复前关闭入口，验证对应工作台备份清单和 SHA-256，向隔离库恢复。重新开入口前，停工作台容器，将最新有效名单写入仅工作台 UID 可读的 `recovery-roster.json`（员工名映射到当前角色，只列归档中仍启用的人员）。使用下方受控恢复入口清空旧凭据并签发首位恢复管理员的设置码。管理员完成网页重新绑定后，才为名单中的其他员工逐一签发设置码。工作台存储及其离职清理入口在 `backend/storage-registry.json` 的 `staff_stores` 中登记。CJ 注销流程只读取同一文件的 `stores`，员工标识不映射到 CJ 用户。

首次上线后，在不录制的受信交互式终端使用以下命令。通过私有流程仅向 JT 交付一次性码，随后由 JT 在网页登录页的「首次设置或重绑验证器」自行设置密码和 TOTP。

```sh
cd /srv/g2c-beta
docker compose --env-file jt-workbench/images.env -f deploy/hk/jt-workbench/compose.yaml exec app /bin/sh -ec 'export JT_WORKBENCH_DATABASE_URL="$(cat /run/jt-workbench-connection)"; exec python -B -m jt.workbench.production bootstrap-admin-code --username "$1"' jt-workbench jtadmin
```

归档恢复专用入口。在旧工作台实例已停止、当前角色清单核对后，在私有交互终端执行，保管输出同初次引导。

```sh
docker compose --env-file jt-workbench/images.env -f deploy/hk/jt-workbench/compose.yaml --profile operator run --rm --no-deps recover-admin '<获准管理员名>'
```

员工离职时，先在工作台按实际员工记录停用账号，再由部署操作者把下列命令的参数替换为对应员工名。清理事务移除该账户的会话、限速状态、密码、验证器与设置码，保留审计与不可重用的登录标识。

```sh
docker compose --env-file jt-workbench/images.env -f deploy/hk/jt-workbench/compose.yaml --profile operator run --rm --no-deps -T offboard '<username>'
```

## 现场验证和回滚

上线前确认同机 CJ 的维护窗口与快测资格，保留切换前 API/worker 版本、公开健康返回和备份服务状态。切换后先读回工作台 HTTPS 登录页、三条匿名重定向以及 CJ 现役版本和健康返回，再按 [CJ API 快速冒烟](../SERVER-SMOKE.md) 用获准合成会话执行问答、文字翻译、滴滴链接。保留原回执。快测 `FAIL` 即执行回滚，`HOLD` 或 `UNRUN` 保持为待验收。

工作台端由 JT 完成首管理员绑定并登录，再用独立获准的测试员工验证队列、案件和运营台。用可停用的独立测试账号验证错误 TOTP 与连续失败锁定，用复核员会话验证运营写操作拒绝。验收记录只留状态和脱敏截图。备份读回检查同一每日任务的实际工作台 `pg_dump`、归档清单以及哈希。

故障时持既有部署锁，读回当前站点、应用和备份状态。在原 inode 恢复 `jt-workbench/Caddyfile.before` 后发 SIGUSR1，确认 CJ 就绪并复测失败项。停工作台 app、工作台备份与转发 socket，撤下工作台的每日备份 drop-in，重载 systemd 并读回 CJ 原日备配置和工作台路由已下线。保留工作台数据、审计及备份，以便原地恢复。实存数据库、角色和备份的进一步删除另由 JT 授权。

若 JT 批准永久撤下，先停入口、工作台容器与备份接入，验证导出的工作台备份及其 SHA-256，并由 JT 移除 Spaceship 的 `jtadmin` A 记录。只有在导出和审批均确认后，才以数据库管理员在现有 PostgreSQL 的管理库删除 `jt_workbench`，随后删除 `jt_workbench_runtime`、`jt_workbench_owner`，及仅针对二者的 HBA 规则后热重载。此步骤不会删除或修改 CJ 数据库、角色和备份。
