# JT 工作台

工作台在仓库根目录启动。阶段一只使用合成数据，进程监听 `127.0.0.1` 上的 HTTPS。默认的内存适配器在进程退出时清空数据。启用 PostgreSQL 后，员工账号、会话、限速、合成队列、复核和审计在工作台独立库内持久化。

## 本地启动

使用仓库锁定的 Python 环境。准备一个本地验证器条目，使用 32 位 Base32 随机密钥、SHA-1、6 位、30 秒周期。启动时在终端隐式输入该密钥、当前验证码和管理员密码。密码至少 12 位。

用已信任且包含 `127.0.0.1` IP SAN 的本地证书，或者生成一张仅用于本次演练的自签证书。

```sh
jt_tls=$(mktemp -d)
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj '/CN=127.0.0.1' -addext 'subjectAltName=IP:127.0.0.1' \
  -keyout "$jt_tls/key.pem" -out "$jt_tls/cert.pem"
uv run --locked python -m jt.workbench --cert "$jt_tls/cert.pem" --key "$jt_tls/key.pem"
```

启动后打开 `https://127.0.0.1:8443/login`。自签证书只用于本次本地会话。绑定会消耗当前验证码，等验证器刷新后再登录。管理员可以从「账号管理」为员工分配角色、停用账号、解锁或授权重绑。创建和重绑会签发一次性设置码，管理员把它当面交给员工本人，员工通过「首次设置或重绑验证器」输入自己的密码和验证器资料。设置码只在签发时显示，有效期 15 分钟。停用、改角色和重绑都会撤销该员工的现有会话。

本地会话最长 60 分钟，连续 15 分钟未使用则过期。单账号连续失败 5 次锁定 15 分钟。整个工作台每分钟接受最多 20 次登录尝试。退出后服务端撤销当前会话。

## 运行测试

```sh
uv run --locked python -B -m pytest -q -p no:cacheprovider jt
```

鉴权测试使用合成账号、固定时间和 [RFC 6238 附录 B](https://www.rfc-editor.org/rfc/rfc6238.html#appendix-B) 的公开向量。审计接口支持追加登录、失败、查看、标注、揭示事件。工作人员查看信号与复核员提交标注、导出评测样本均写入追加审计。字段揭示功能属于后续阶段。

## 使用队列与导出

管理员创建值班处理员或复核员账号后，使用该员工账号登录，在导航中打开「待办队列」。默认加载 `jt.synthetic.generate_dataset(seed=1706)` 的合成信号。队列按级别、响应截止、发现时间和内部顺序字段排列，筛选与详情由服务器渲染。队列时间显示为北京时间。

P0 横幅在打开队列时可见。页面每两秒刷新本机的告警数量，轮询不会延长会话。点击「开启提醒」可启用本地声音和已获权限的浏览器通知，权限不足时仍可看到横幅。

复核员可标注真实级别、误报、漏报与备注，并查看历史。误报样本的真实级别为空。导出按钮下载 `jt-review-samples.json`，使用 `jt-workbench-review-export.v1`。每个已复核信号取最后一条标注，包含信号类型、识别级别、脱敏证据与版本，以及 `review.actual_severity`、`review.false_positive`、`review.missed`、`review.note` 和 UTC 时间。Case 关联只使用 `case_id`，源事件引用、员工账号和内部信号编号均不进入导出。

引擎联调通过 `jt.common.SignalSink` 调用 `MemoryQueue.publish(signal)`。同 ID 同内容的重复交付只入队一次，同 ID 不同内容会拒绝。阶段一的默认种子未建单。


## 本地 PostgreSQL

使用工作台专用的 `jt_workbench` 数据库，迁移角色为 `jt_workbench_owner`，应用角色为 `jt_workbench_runtime`。两个角色分别由部署侧预设，均为非超级用户，运行角色不加入迁移角色。连接串 `JT_WORKBENCH_DATABASE_URL` 显式指定 `host`、`dbname` 和 `user`。连接可以使用专用 Unix 套接字。

- 启动迁移进程使用所有者的连接串，执行 `uv run --locked python -m jt.workbench.postgres up`。空库本地验证可运行同一命令的 `down`，已有业务数据时会拒绝。
- 常驻应用用运行角色的连接串执行前面的启动命令。应用检查数据库、角色和审计权限，再加载确定性合成信号。已有管理员时可直接启动。迁移和常驻应用使用同一变量名，各进程只接收自己的连接串。
- 运行角色对审计表仅有 SELECT 和 INSERT。身份、限速、会话和队列动作通过同一数据库级事务锁串行化，复核和审计使用同一事务提交。会话与限速时间使用数据库时钟，让多个进程共享同一时基。

可通过 `JT_WORKBENCH_TEST_PG_BINDIR="$(pg_config --bindir)" uv run --locked python -B -m pytest -q -p no:cacheprovider jt/workbench` 运行工作台测试。集成测试自行建立临时 Unix 套接字数据库，禁止 TCP 监听，测试完成后清理临时集群。常规测试继续使用内存适配器。

## 容器入口与 S 线接入

从仓库根目录构建。传入由同一 `pyproject.toml` / `uv.lock` 构建的、S 线已批准的 G2C Python 运行镜像。工作台镜像仅新增 JT 源码与迁移，运行入口和 UID 与 CJ 运行容器分开。

```sh
docker build --pull=false --network=none \
  --build-arg JT_WORKBENCH_RUNTIME_IMAGE="$JT_APPROVED_RUNTIME_IMAGE" \
  -f jt/workbench/Dockerfile -t jt-workbench:local .
```

| 入口命令 | 配置 | 用途 |
| --- | --- | --- |
| `migrate` | 所有者的 `JT_WORKBENCH_DATABASE_URL` | 一次性启动任务，应用工作台迁移，成功后才启动常驻应用 |
| `bootstrap-admin` | 运行角色的 `JT_WORKBENCH_DATABASE_URL` | 在受控终端首次引导，重复执行拒绝 |
| `serve`（默认） | 运行角色的 `JT_WORKBENCH_DATABASE_URL`、`JT_WORKBENCH_PUBLIC_HOST=jtadmin.go2china.space`、`JT_WORKBENCH_HTTP_SOCKET=/run/jt-workbench/http.sock` | 通过 Unix socket 处理工作台 HTTP |
| `healthcheck` | `JT_WORKBENCH_HTTP_SOCKET` | 走同一 socket 上的内部 Host 检查数据库，不托管公开健康路由 |

迁移任务和常驻应用各接收自己的 600 环境文件，连接串显式包含 `host`、`dbname=jt_workbench` 与角色名。迁移用 `jt_workbench_owner`，常驻和受控引导用 `jt_workbench_runtime`。现有 PostgreSQL 的角色、库、认证规则、备份和恢复由 S 线接入。应用连接只授独立库 CONNECT、工作台 schema USAGE 和迁移列出的表权限。运行角色对审计仅有 SELECT/INSERT，不加入所有者或 CJ 角色。数据库认证应按库与角色限定，保留 CJ 的 peer 映射并阻断工作台使用它。Docker 默认工作台 UID/GID 为 10031，接入时核对与 CJ peer 映射无冲突。

将独立 HTTP socket 目录挂给这两个服务。工作台写入、Caddy 只读，目录归工作台 UID 所有，建议 0750，Caddy 用共享 GID 访问；socket 为 0660。Caddy 的 HTTPS 站点将 `unix//run/jt-workbench/http.sock` 作为上游，显式传送规范 Host，并用 HTTPS 站点的单个 `X-Forwarded-Proto: https` 覆盖来路同名值。常驻应用仅在 Unix socket 接收 HTTP，无 TCP 监听及端口映射。数据库使用另一条专用 Unix socket 挂载。

本机单进程导入与 scrypt 峰值约 186 MiB。ARM64 的离线容器启动与健康检查峰值约 192–200 MiB，建议在 S 线部署验证时以 256 MiB 单容器上限作为起点，按现有主机监控和并发验收调整。此值为本地估算。首个管理员引导由 S 线在目标库私有环境完成。生产访问的公网负例和同机 CJ 回归属于 #1886 Part 2。

## 演练案件

值班处理员登录后可从「案件」认领一个未分配的合成案件。详情、动作与已认领列表都按当前员工隔离。管理员通过只读审计查看操作，复核员继续使用信号队列。

案件详情由 `jt.playbook.CaseWorkflow` 计算当前步骤与版本。员工可以推进、生成合成草稿、确认或驳回。涉及改行程或付费的步骤显示独立客户同意门槛，员工页面没有录入客户同意的接口。客户同意只由可信本地演练入口录入。动作审计记录案件、员工、步骤、版本、结果和固定拒绝原因，未授权请求也不会进入 playbook。

演练案件与认领状态沿用 JT1 的进程内模型，重启后生成新的一套合成案件。启用 PostgreSQL 后，历史审计独立保留。审计写入失败后停止展示本实例演练案件，避免返回未登记的步骤变化。迁移 002 追加案件审计字段并保留原有基础 schema 标记，原入口可继续读取原字段。

## 演示运营台与首个管理员

值班处理员从「运营台」进入服务请求和官网线索。Part 0 的数据源仅包含合成记录，演示动作在当前进程内保留，启用 PostgreSQL 时操作审计独立保留。状态与凭据按 SERVICE-REQUEST@1 渲染，对客状态历史和员工凭据分别放在两个区域。每个相关页面标注「演示数据」。种子信号使用 JT1 合成 playbook 建单，处理员可从信号详情认领并进入案件。

S 线可在禁用录制的私有交互式终端，用运行角色的连接串执行 `bootstrap-admin-code --username <JT员工账号>` 签发首个管理员设置码。在私下安全交接中仅交给 JT 使用。JT 自己打开 HTTPS 登录页的「首次设置或重绑验证器」，输入账号和设置码，并在自己的设备上设置密码及验证器。设置码有效 15 分钟，只能使用一次。首个账号绑定前可以对同一账号签发新码，原码失效；绑定后命令拒绝。既有 `bootstrap-admin` 终端入口保留，演示部署优先用设置码。两种方式都不使用聊天、PR、仓库或日志传递任何凭据。

迁移 003 追加演示操作的动作和引用，原有基础 schema 标记不变。提交的演示操作先追加审计，再更新内存快照。应用重启会恢复演示内容，审计按 PostgreSQL 存储配置保留。
