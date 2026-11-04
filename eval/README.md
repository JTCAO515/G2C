# M4 本机实验与效果评测

仅合成输入、私有 Unix socket PostgreSQL、签名 HTTP 入口与原 worker。
`runtime.py` 复用仓库 PG/登录支架，不读取 ambient DSN 或真实模型凭据。
业务 SQL 经 `cj_m1_runtime`；initializer 只负责全新库迁移。

```sh
uv run --locked python -B eval/invariants.py --output .local/eval/invariants-001
```

每次输出目录必须不存在，以保留历史 FAIL。`report.json` 逐项记录触发、
预期、实际返回/PG 状态、head、脏状态、环境和耗时。复用现有故障操作时
列出实际执行入口；不是源码文字检查。运行日志放 `.local/` 或 PR artifact，
不提交到仓库。PASS 只证明该本机确定性实验，真实模型效果、设备与云仍 UNRUN。

按切片运行（每次使用新的输出目录）：

```sh
uv run --locked python -B eval/invariants.py --suite isolation --output .local/eval/owner-001
uv run --locked python -B eval/invariants.py --suite commit --output .local/eval/commit-001
uv run --locked python -B eval/invariants.py --suite memory --output .local/eval/memory-001
uv run --locked python -B eval/invariants.py --suite external --output .local/eval/external-001
```

| 子票 / 本机实验数 | 真实触发与判据 |
|---|---|
| #501 / 8 | 外账号 API/SQL/worker、commit 后子进程退出、两 worker 竞争、部分失败、UNKNOWN、在途取消、UTF8 缺段/过期与物理事件损坏、注册后台 owner/ACK/共享限额 |
| #502 / 4 | 同字节消息并发、同确认并发、两不同候选争同正式版本、SQL 前回滚与真实 commit 后丢 ACK |
| #503 / 10 | typed 完整当前性、在途撤回、保留聊天三阶段、共享候选/缓存重建、source2/scoped、前台/后台注销、首次 scope 创建竞态 |
| #504 / 6 | 七类禁止 origin、八类混合 DNS、真实本地 TLS 故障、恶意记忆文本、FACT 注入、后台恶意 tool_calls 与限额 |

各实验入口的说明给出触发和预期；实际状态由返回值、真实 PG 查询或原实现
故障程序的完整 stdout/stderr 记录。`implementation_probe` 运行的是签名 API /
受限 PG / 原 worker 的完整故障程序；保留程序内各断言及真实失败位置，不把
普通模块单测当组合证据。initializer 仅作全新库迁移与明确标注的一次性故障注入。

28 项是本机覆盖清单，不是 28 个现实服务场景或全产品验收。真实模型文本
遵循指令的质量、实际供应商结果/费用、目标网络 → #32；云存储、真实备份和
最新撤回 fence 重放 → #30（本机部署/恢复 owner 为 B #496）；真机、实际
VoiceOver 与离线设备 → #29。全部保持 UNRUN，须在目标票登记回链后才可
按 ADR-0007 转记。App 组合复用实时 #23/#26/#27 已合并的 L1 证据（PR487/488），
不把这些后端实验冒称本轮重新执行了 App 或全设备验证。

历史 FAIL 不覆盖：开发首轮短片段未达既有发布缓冲；外部文本实验首轮把
`Ledger` 当作字典读取。两项均属评测程序错误，修正触发/读取后复跑，原报告
仍单独保留。产品历史 FAIL 及 UNKNOWN 不因上述修正被删除或升级。
