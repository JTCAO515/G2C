# 香港员工工作台上线（#1886 Part 2）

上线源须为已审合并提交，同时记录 SHA、CI、同机 CJ 就绪证据与现场负责人。将该提交的 `git archive` 和 SHA-256 通过既有验签 SSH 送至只含本次资源的 0700 暂存目录。先核对实际主机文件、现役镜像和维护状态，再在主机用 `bash <源码>/deploy/hk/jt-workbench/install.sh <源码> <提交 SHA>`。使用已有镜像和锁定依赖，在无构建网络的条件下构建独立工作台镜像。脚本持有 CJ 既有部署锁，若备份运行、资源不足或 Caddy 现役不是预期基线则停在公网站点切换之前。

PostgreSQL 沿用服务器上的现有实例。现有套接字权限、CJ 的 HBA 行及角色保持原样。systemd 的 Unix 代理只打开独立的组控套接字。工作台两个登录仅限专用数据库和 SCRAM，应用只能挂运行角色连接文件。迁移角色单独执行，连接文件为各目标容器 UID 600。工作台容器没有网络或公开端口。Caddy 沿用现有 `/config` 绑定，在专用子目录仅具组读与查找权限，只有工作台 UID 能更改目录。服务器原有配置原地追加新域名，Caddy 2.11 SIGUSR1 热重载保留旧监听。接下来从公网用有效证书访问 `/login`，检查 `/queue`、`/cases` 与 `/operations` 未登录重定向，同时复查既有 CJ `/health/ready`。

工作台专用每日定时器创建私有备份，复用现有私有 OSS 前缀、30 天政策和值班用量额度。上传承接既有 INTENT、精确哈希与 HEAD 读回，出现不明确回执先对原对象核验。临时本机文件只供本次受控读回。恢复前关闭入口，使用对应工作台的清单和 SHA-256，向隔离库恢复。重新开入口前清掉还原的会话、密码和验证器凭据，核对当前员工名单，重新签发有效员工的设置码。工作台数据库不纳入 CJ 用户清理目标。

首次上线后，在不录制的受信交互式终端使用以下命令。通过私有流程仅向 JT 交付一次性码，随后由 JT 在网页登录页的「首次设置或重绑验证器」自行设置密码和 TOTP。

```sh
cd /srv/g2c-beta
docker compose --env-file jt-workbench/images.env -f deploy/hk/jt-workbench/compose.yaml exec app /bin/sh -ec 'export JT_WORKBENCH_DATABASE_URL="$(cat /run/jt-workbench-connection)"; exec python -B -m jt.workbench.production bootstrap-admin-code --username "$1"' jt-workbench jtadmin
```

员工离职时，先在工作台按实际员工记录停用账号，再由部署操作者把下列命令的参数替换为对应员工名。清理事务移除该账户的会话、限速状态、密码、验证器与设置码，保留审计与不可重用的登录标识。

```sh
docker compose --env-file jt-workbench/images.env -f deploy/hk/jt-workbench/compose.yaml --profile operator run --rm --no-deps -T offboard '<username>'
```

故障时持现有部署锁，先在原 inode 恢复 `jt-workbench/Caddyfile.before` 后发 SIGUSR1，确认 CJ 就绪。可停止工作台 app 和每日定时器，保留已产生的工作台数据、审计及备份，以便原地恢复。成员已开始使用后从备份恢复须先走员工状态核对。实存数据库、角色和备份的进一步删除另由 JT 授权。
