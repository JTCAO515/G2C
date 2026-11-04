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

当前 #501：跨 owner 读取/写入/worker、提交后真实子进程退出、同聊天两 worker
竞争、部分输出后失败与 UNKNOWN 阻塞顺序。其余 #502–#504 和 #497 继续交付；
本目录不声明 #28 已通过或任何质量阈值达标。
