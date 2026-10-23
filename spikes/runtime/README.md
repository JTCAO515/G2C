# CJ-002：AgentScope + DBOS 本地选型段

2026-10-23 真实验收续作入口见 [REAL-ACCEPTANCE.md](REAL-ACCEPTANCE.md)：JT 已授权百炼测试费用由余额控制；当前仍缺 CJ 专用资源元数据和新 key 的安全注入。新增独立 `provider_acceptance.py`，原 17+3 证据保留并复用，真实 provider 仍 UNRUN。

本段建议继续 **AgentScope 2.0.10 + DBOS 3.3.0** 作为唯一主候选，进入后续获准的真实 provider 验证。已证明本地持久边界可实现；没有发现必须切换 Pydantic AI 的硬语义失败，因此不引入第二套主框架。

这不是 CJ-002 整票通过：模型、真实工具、真实 SSE、PostgreSQL、账号隔离、实际用量/费用结果和产品 RUN/USAGE 集成均未验收。原 13 文档和共享工程文件未修改；这些未运行层不据此新增为原票前置。

## 复现

环境为 macOS arm64，Python 3.12.14。以下从本目录执行；工具、Python、缓存、虚拟环境和测试数据库全部位于本目录。需要下载依赖时使用本轮已授权网络范围，不使用旧凭据。

```sh
export UV_CACHE_DIR="$PWD/.cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.python"
export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
uv python install 3.12.14 --no-bin
uv sync --frozen --python .python/cpython-3.12.14-macos-aarch64-none/bin/python3
.venv/bin/python validate.py
.venv/bin/python sdk_probe.py
```

脚本不启动 HTTP listener，不连数据库服务或 provider。worker 禁止 socket 连接，测试控制器只传最小环境，不继承模型/DBOS/OTEL 凭据。每轮创建新的 `.runs/validation-*`；不自动清除旧失败。全量验证约两分钟，逐项打印结果，产物落在 `evidence/`。定向验证支持：

```sh
.venv/bin/python validate.py --group cancel --case cancel-before_publish
```

## 可复用边界

先读 [BOUNDARY.md](BOUNDARY.md)。`runtime.py` 使用真正安装的 AgentScope Agent、FunctionTool、事件解析和 DBOS async workflow/step；只有 provider 为脚本 fixture。`ledger.py` 是本地原子回执样例，不能直接当正式数据服务或认证层。

| 标识/状态 | 本段验证 |
|---|---|
| workflow ID | 同 workflow 读原结果，完成步骤在新进程恢复时不再执行 |
| attempt ID | 与 workflow ID 分离；同业务请求换 workflow 仍绑定原 attempt；不同输入/归属冲突 |
| business action key | principal + operation + action_id；同输入返回原回执，不同输入冲突；与工作流和调用重试无关 |
| UNKNOWN | intent 后崩溃、发送中断、响应未落回执、模型超时；不派第二次请求，也不写业务结果 |
| 已提交业务 | 提交后进程死亡，读原事务回执；取消仍可查询，不宣称回滚 |
| FAILED | 工具失败、结构不合法；保留已提交效果，不能当完整成功 |

本地脚本每次流程最多两次 fixture 模型请求，步骤与模型重试关闭。SDK 探针验证底层客户端也必须 `max_retries=0`。AgentScope 原生 structured-output 默认可尝试多种策略；离线探针用显式单一 tool_choice 使结构失败只发送一次。生产还需用 USAGE 控制每一次出站请求与费用状态，不能把框架次数上限当金额上限。

fixture 请求 hash 仅覆盖显式测试参数；正式 adapter 要绑定完整、精确出站请求。此样例没有可切换到真实 provider 的执行分支。最终 JSON 的 Pydantic 校验是本地输出校验；`sdk_probe.py` 另验原生结构失败和 HTTP 解析。fixture 文本 deltas 在响应回执保存后才释放，是缓冲事件，不是实时 provider streaming / 产品 SSE 的证明。

## 自测结果及限制

候选验证索引见 [REPORT.md](REPORT.md)。有效范围共 **17 个本地场景 + 3 个 SDK 探针 PASS**。首次矩阵中的两个取消读回 FAIL 原样保留，修复 DBOSClient 查询接口后仅重验取消范围；新增发布前取消反例也通过。单看 DBOS `SUCCESS` 不代表业务成功：超时样例 workflow 为 SUCCESS，业务 outcome 明确为 UNKNOWN；输出失败同样独立记录 FAILED。

DBOS checkpoint 与本地回执使用两个独立 SQLite 文件；attempt 和业务回执有不同的表与身份约束。SQLite 不能替代 PostgreSQL、跨节点恢复、备份恢复、RLS 或真实用户验证。这里的持久化只证明正常本地文件系统上的进程死亡恢复，不证明掉电/磁盘损坏容灾。生产版本升级/重放、晚到版本 fence、撤回/清理与授权/预算计量仍需领域 owner 落实。

官方模型 ID、地域及文档矛盾见 [SOURCES.md](SOURCES.md)。真实中英模型质量、工具调用、流式、超时/取消计费、地域和费用均 **UNRUN**。建议是有边界的本地选型建议，不能据此关 Issue #2、部署或改已接受架构。
