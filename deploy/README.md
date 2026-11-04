# M4 本机部署与恢复

只用于 `CJ_ENV=local`、合成身份、FakeProvider。没有云入口或生产配置。
API 与 worker 复用原本地签名、邀请、事务 scope、RLS、注册计量和原动作恢复路径；
`scripts/run_worker.py --real` 的拒绝保持。真实模型验收与本容器证据分别记录。

## 从空库启动

依赖 Docker Compose、仓库锁定的 uv 环境。所有步骤从仓库根执行：

```sh
uv sync --locked
CJ_ENV=local PYTHONPATH=scripts uv run --locked python -B -m deploy.local .local/deployment --port 18765 --project g2c-m4-local
uv run --locked python -B -m deploy.build
docker compose --env-file .local/deployment/compose.env -f deploy/compose.yaml up -d
```

配置生成器拒绝已有目录，不覆盖密钥。它只生成两个合成身份及本地专用随机密钥；
正式 operator 使用环境变量和只读密钥文件注入，不复制这些合成凭据到云。
构建器只复制明确的代码目录，排除隐藏目录、测试、运行产物和证据；不把整个工作区作为镜像上下文。
容器非 root 执行，数据库不发布端口，API 仅发布到 loopback。
Unix socket 的本地 trust 与私有 volume 共同构成本地测试边界，不能直接照搬为云数据库配置。

| 环境变量 | 用途 / 缺失行为 |
|---|---|
| `CJ_ENV=local` | 其他环境拒绝启动 |
| `CJ_LOCAL_CONNINFO` | 仅含运行角色、本机 Unix socket 的 JSON 文件；无 DSN/环境回落 |
| `CJ_DEPLOY_MIGRATION_CONNINFO` | 独立本地迁移身份文件，仅 migrator 使用 |
| `CJ_LOCAL_AUTH_DIR` | 现有签名密钥、history key、邀请文件；缺失拒绝 |
| `CJ_LOCAL_RUN_CONTEXT` | 显式有效的 provider_call 配额和输出限制；不代表真实货币 |
| `CJ_DEPLOY_PROVIDER=fake` | 本切片只启用 FakeProvider；真实 adapter 未启用 |
| `CJ_DEPLOY_RECOVERY_KEY_FILE` | 专用 32 字节、0600 的恢复包 HMAC key |
| `CJ_DEPLOY_CONTROL` | 与数据库备份分离的控制目录，不能回滚或从旧备份覆盖 |

Compose 的端口、UID/GID、配置目录、控制目录都必须显式提供，模板使用 `${VAR:?}` 拒绝缺项。
启动先自动迁移；只有空业务库能初始化控制锚；已有控制锚不会被自动重置。
0048 新增一行随机数据库实例标识，并授予运行角色读取标识/迁移版本所需的 schema USAGE/SELECT；运行角色不能改标识，无业务或写权限扩大。
标识随检查点备份，新的空数据库卷生成不同标识；不能用可能重复的数据库 OID 把旧 release 接到新卷上。

## 健康、告警与兼容

- `GET /health/live` 只证明 API 进程存活。
- `GET /health/ready` 检查恢复签名锚、数据库可用、精确 schema、15 秒 worker 心跳与模型适配器状态。
- 未就绪时所有业务读写返回 503；健康响应只含组件原因，不返回连接串、身份或内容。
- worker 输出 `ALERT database_unavailable`、`ALERT model_unavailable` 或 `ALERT deployment_gate_unavailable`；
  进程停止由过期心跳定位。`fake-unavailable` 仅是显式合成模型故障配置，不是真实网络测量。
- 本配置保留 MESSAGE-send.1 的既有兼容行为；未知版本由原协议入口拒绝，不另造“最新版”头。
  schema 与镜像内 manifest 不一致时拒绝就绪和派发，不能把旧 schema 应用与新库拼成可写状态。

## 备份与恢复边界

恢复单元是**完整安全检查点**，包含原域已经提交的物理删除结果及全部永久 fence、版本、任务、费用/UNKNOWN。
不引入另一套删除解释器，也不重新执行用户动作或付费调用。
它比原备份新，签名清单绑定原备份 hash；控制目录里的 `latest.json` 指向最新安全检查点。

准备检查点前必须停止本环境 API、worker 和其他 writer。没有最新完整检查点、独立控制锚或密钥时，
本实现不能证明最后一次删除之后的状态，恢复保持不可用。单独保存几个 fence 的 hash 不足以证明物理副本已经清掉。
这是本机全量检查点方案；连续归档、自动跨故障域备份、30 天滚动留存及供应商恢复另归 #30。

使用 `python -B -m deploy.recovery`，通过 `--conninfo` 指定本地 operator 连接文件，
`--control` 指定独立控制目录，`CJ_DEPLOY_RECOVERY_KEY_FILE` 指定密钥文件：

```text
backup  --package BASE                         # 原备份；不覆盖已有包
safety  --base BASE --package NEW              # 停 writer 后捕获较新完整状态并撤去旧启读许可
restore --base BASE --safety NEW               # 目标必须是新空库；不覆盖原库
```

每个包由 `database.dump` 与签名 `manifest.json` 组成，权限 0700/0600，含合成私有数据，不能入库或公开。
`pg_export_snapshot` 让清单与 dump 属于同一快照。恢复使用较新的完整状态前滚，
通过原生 TOC 顺序先重放永久 fence，再载入普通数据；M45 的 CHECK 依赖这些 proof，默认 pg_dump 顺序不满足。
保留每一条 archive entry、原权限和约束，不使用 `--clean`、禁用 trigger 或 replication-role 绕过完整性。
验证 dump hash、签名、最新锚、全部 fence 和 schema 后，才为这个目标签发本地 release；任一失败撤去 release。
源环境不会因目标恢复被自动重新开放。控制目录和 key 的备份/保管属于可信 operator 边界，不能用同一旧数据库包覆盖。

## 检查

```sh
uv run --locked python -B scripts/test.py
uv run --locked python -B scripts/pg_suites.py
uv run --locked python -B scripts/deploy_recovery_check.py
```

恢复专项复用原 account-retention 和 manual-history-erasure 的真实生产者，先保留两类内容的旧备份，
再执行实际注销与单条删除，包含原未知任务/费用，最后恢复到新的私有 PG 空库。
旧包、篡改、缺失检查点、旧应用 schema、有数据回退及跨 owner 分别拒绝；保留历史失败。
本机容器、私有 PG、真实模型、云 Auth/pooler、真机与发布证据不能互相替代。
